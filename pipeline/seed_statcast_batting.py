"""
Seed ``statcast_batting`` (SCHEMA.md) from pybaseball Savant leaderboards.

Merges season-level exit velocity / barrels, sprint speed, and expected stats
on ``player_id`` (MLBAM). ``pa`` is coalesced from the exit-velo leaderboard
``attempts`` (qualifying batted-ball events) and expected-stats ``pa`` for
PA-weighted team aggregates in the app.

Requires a unique constraint on ``(player_id, season)`` for PostgREST upsert, e.g.::

    CREATE UNIQUE INDEX IF NOT EXISTS statcast_batting_player_id_season_key
      ON statcast_batting (player_id, season);
"""

from __future__ import annotations

import math
import sys
import time
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from pybaseball import statcast_batter_exitvelo_barrels, statcast_batter_expected_stats
from pybaseball.statcast_running import statcast_sprint_speed

import config  # noqa: F401 — load .env via side effect
from db import get_client

_NAME_COL = "last_name, first_name"
_BATCH_SIZE = 500
STATCAST_FIRST_SEASON = 2015
_DELAY_BETWEEN_SEASONS_SEC = 5.0


def _fetch_frames(season: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Pull the three Statcast leaderboards for ``season``."""

    exit_barrel = statcast_batter_exitvelo_barrels(season, minBBE="q")
    expected = statcast_batter_expected_stats(season, minPA="q")
    sprint = statcast_sprint_speed(season, min_opp=10)
    return exit_barrel, expected, sprint


def _exit_velo_pa_column(df: pd.DataFrame) -> str | None:
    """
    Savant exit-velo / barrels leaderboard uses ``attempts`` (qualifying BBE);
    some seasons may expose ``pa``. Prefer attempts for weights.
    """

    if "attempts" in df.columns:
        return "attempts"
    if "pa" in df.columns:
        return "pa"
    return None


def _merge_leaderboards(
    exit_barrel: pd.DataFrame,
    expected: pd.DataFrame,
    sprint: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    """Outer-merge on ``player_id`` and map to SCHEMA column names."""

    pa_ev_col = _exit_velo_pa_column(exit_barrel)
    ev_cols: list[str] = [
        "player_id",
        _NAME_COL,
        "avg_hit_speed",
        "max_hit_speed",
        "avg_hit_angle",
        "brl_percent",
        "ev95percent",
    ]
    if pa_ev_col:
        ev_cols.insert(2, pa_ev_col)

    ev = exit_barrel[ev_cols].rename(
        columns={
            _NAME_COL: "player_name",
            "avg_hit_speed": "avg_exit_velocity",
            "max_hit_speed": "max_exit_velocity",
            "avg_hit_angle": "avg_launch_angle",
            "brl_percent": "barrel_rate",
            "ev95percent": "hard_hit_rate",
        },
    )
    if pa_ev_col:
        ev = ev.rename(columns={pa_ev_col: "pa_exit"})
    else:
        ev["pa_exit"] = np.nan

    ex = expected[
        [
            "player_id",
            "pa",
            "est_ba",
            "est_slg",
            "est_woba",
        ]
    ].rename(
        columns={
            "pa": "pa_expected",
            "est_ba": "xba",
            "est_slg": "xslg",
            "est_woba": "xwoba",
        },
    )

    sp = sprint[["player_id", "team_id", "sprint_speed"]]

    m = ev.merge(ex, on="player_id", how="outer")
    m = m.merge(sp, on="player_id", how="outer")
    m["season"] = season
    m = m.drop_duplicates(subset=["player_id"], keep="first")

    pe = pd.to_numeric(m["pa_exit"], errors="coerce")
    px = pd.to_numeric(m["pa_expected"], errors="coerce")
    m["pa"] = pe.where(pe.notna(), px)
    m["pa"] = pd.to_numeric(m["pa"], errors="coerce").round()
    m["pa"] = m["pa"].astype("Int64")
    m = m.drop(columns=["pa_exit", "pa_expected"], errors="ignore")

    # Normalize player_id to nullable int (outer merge can introduce NaN)
    m["player_id"] = pd.to_numeric(m["player_id"], errors="coerce").astype("Int64")
    m = m[m["player_id"].notna()]
    m["player_id"] = m["player_id"].astype(int)

    return m


def _fill_team_id_from_players(df: pd.DataFrame) -> pd.DataFrame:
    """
    Coalesce ``team_id`` with ``players.team_id`` for rows missing MLB team id.

    Sprint leaderboard supplies ``team_id`` for many batters; exit / expected
    merges leave others null until filled from Seed ``players``.
    """

    df = df.copy()
    client = get_client()
    pids = df["player_id"].dropna().astype(int).unique().tolist()
    id_to_tid: dict[int, int | None] = {}

    chunk = 500
    for i in range(0, len(pids), chunk):
        batch = pids[i : i + chunk]
        resp = client.table("players").select("id, team_id").in_("id", batch).execute()
        for r in resp.data or []:
            pid = r.get("id")
            if pid is None:
                continue
            tid = r.get("team_id")
            id_to_tid[int(pid)] = int(tid) if tid is not None else None

    current = pd.to_numeric(df["team_id"], errors="coerce")
    fallback = df["player_id"].map(
        lambda x: id_to_tid.get(int(x)) if pd.notna(x) else None,
    )
    coalesced = current.where(~current.isna(), fallback)
    df["team_id"] = coalesced.map(lambda x: int(x) if pd.notna(x) else None)
    return df


def _row_to_supabase(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Build one insert row; skip if ``player_id`` missing."""

    pid = rec.get("player_id")
    if pid is None or (isinstance(pid, float) and math.isnan(pid)):
        return None

    def num(v: Any) -> float | None:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        if isinstance(v, (np.floating, np.integer)):
            return float(v)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    name = rec.get("player_name")
    if name is not None and pd.isna(name):
        name = None
    elif name is not None:
        name = str(name).strip() or None

    team_id = rec.get("team_id")
    if team_id is not None and pd.notna(team_id):
        try:
            team_id = int(team_id)
        except (TypeError, ValueError):
            team_id = None
    else:
        team_id = None

    season = rec.get("season")
    try:
        season_i = int(season) if season is not None and pd.notna(season) else None
    except (TypeError, ValueError):
        season_i = None
    if season_i is None:
        return None

    def as_int(v: Any) -> int | None:
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(v, (float, np.floating)) and math.isnan(float(v)):
            return None
        try:
            n = int(round(float(v)))
            return n if n >= 0 else None
        except (TypeError, ValueError):
            return None

    return {
        "player_id": int(pid),
        "player_name": name,
        "team_id": team_id,
        "season": season_i,
        "pa": as_int(rec.get("pa")),
        "avg_exit_velocity": num(rec.get("avg_exit_velocity")),
        "max_exit_velocity": num(rec.get("max_exit_velocity")),
        "avg_launch_angle": num(rec.get("avg_launch_angle")),
        "barrel_rate": num(rec.get("barrel_rate")),
        "hard_hit_rate": num(rec.get("hard_hit_rate")),
        "xba": num(rec.get("xba")),
        "xslg": num(rec.get("xslg")),
        "xwoba": num(rec.get("xwoba")),
        "sprint_speed": num(rec.get("sprint_speed")),
    }


def upsert_statcast_batting(
    rows: list[dict[str, Any]], client: Any | None = None
) -> tuple[int, int]:
    if client is None:
        client = get_client()
    ok = 0
    failed = 0

    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("statcast_batting").upsert(
                batch,
                on_conflict="player_id,season",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_statcast_batting: batch {batch_no} failed: {exc}")
            failed += len(batch)

    return ok, failed


def _parse_season_range() -> tuple[int, int]:
    argv = sys.argv[1:]
    now_y = datetime.now().year
    try:
        if len(argv) == 0:
            return now_y, now_y
        if len(argv) == 1:
            return int(argv[0]), now_y
        if len(argv) == 2:
            return int(argv[0]), int(argv[1])
    except ValueError:
        print("Invalid season argument(s); integers required.", file=sys.stderr)
        sys.exit(2)
    print(
        "Usage: python seed_statcast_batting.py [start_season [end_season]]\n"
        "  (no args)     current year only\n"
        "  2015            2015 through current year\n"
        "  2015 2020      2015 through 2020 inclusive",
        file=sys.stderr,
    )
    sys.exit(2)


def seed_season(year: int, client: Any) -> tuple[int, bool]:
    """
    Fetch Savant leaderboards for ``year``, merge, upsert.

    Returns ``(rows_upserted_ok, success)``. ``success`` is False if the season
    fails entirely (exception); partial batch failures still return success True
    with reduced ``ok`` count.
    """
    print(
        f"seed_statcast_batting: fetching Statcast leaderboards for season={year}…",
        flush=True,
    )
    try:
        exit_df, exp_df, spr_df = _fetch_frames(year)
        merged = _merge_leaderboards(exit_df, exp_df, spr_df, year)
        merged = _fill_team_id_from_players(merged)

        records: list[dict[str, Any]] = []
        for _, row in merged.iterrows():
            mapped = _row_to_supabase(row.to_dict())
            if mapped is not None:
                records.append(mapped)

        print(
            f"seed_statcast_batting: merged {len(records)} rows "
            f"(exit/barrel rows={len(exit_df)}, expected={len(exp_df)}, sprint={len(spr_df)}); "
            f"upserting…",
            flush=True,
        )

        ok, batch_failed = upsert_statcast_batting(records, client=client)
        if batch_failed:
            print(
                f"[warn] seed_statcast_batting season {year}: {batch_failed} row(s) "
                f"in failed batch(es); {ok} row(s) reported OK by client.",
                flush=True,
            )
        return ok, True
    except Exception as exc:  # noqa: BLE001
        print(
            f"[warn] seed_statcast_batting season {year} failed: {exc}",
            flush=True,
        )
        return 0, False


def main() -> None:
    start_season, end_season = _parse_season_range()
    if start_season > end_season:
        print(
            f"start_season ({start_season}) must be <= end_season ({end_season})",
            file=sys.stderr,
        )
        sys.exit(2)

    client = get_client()
    seasons = list(range(start_season, end_season + 1))
    skipped = [y for y in seasons if y < STATCAST_FIRST_SEASON]
    for y in skipped:
        print(
            f"[warn] seed_statcast_batting: season {y} skipped "
            f"(Statcast batting leaderboards available from {STATCAST_FIRST_SEASON}+)",
            flush=True,
        )

    to_run = [y for y in seasons if y >= STATCAST_FIRST_SEASON]
    total_run = len(to_run)
    total_rows = 0
    failed_seasons = 0

    for i, year in enumerate(to_run, start=1):
        ok, ok_season = seed_season(year, client)
        if not ok_season:
            failed_seasons += 1
        else:
            total_rows += ok
        print(
            f"[seed_statcast_batting] season {year} ({i}/{total_run}): "
            f"upserted {ok} rows",
            flush=True,
        )
        if i < total_run:
            time.sleep(_DELAY_BETWEEN_SEASONS_SEC)

    print(
        f"seed_statcast_batting: summary — "
        f"Total seasons: {total_run}, "
        f"Total rows upserted: {total_rows}, "
        f"Failed seasons: {failed_seasons}",
        flush=True,
    )
    if skipped:
        print(
            f"seed_statcast_batting: Skipped (pre-{STATCAST_FIRST_SEASON}): {len(skipped)}",
            flush=True,
        )


if __name__ == "__main__":
    main()
