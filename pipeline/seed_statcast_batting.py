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


def upsert_statcast_batting(rows: list[dict[str, Any]]) -> tuple[int, int]:
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


def main() -> None:
    season = datetime.now().year
    print(f"seed_statcast_batting: fetching Statcast leaderboards for season={season}…")

    exit_df, exp_df, spr_df = _fetch_frames(season)
    merged = _merge_leaderboards(exit_df, exp_df, spr_df, season)
    merged = _fill_team_id_from_players(merged)

    records: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        mapped = _row_to_supabase(row.to_dict())
        if mapped is not None:
            records.append(mapped)

    print(
        f"seed_statcast_batting: merged {len(records)} rows "
        f"(exit/barrel rows={len(exit_df)}, expected={len(exp_df)}, sprint={len(spr_df)}); upserting…",
    )

    ok, failed = upsert_statcast_batting(records)
    print(
        f"seed_statcast_batting: done — upserted {ok} rows, "
        f"{failed} row(s) in failed batches.",
    )


if __name__ == "__main__":
    main()
