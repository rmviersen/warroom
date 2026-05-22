"""
Load ``team_pitching_seasons`` (SCHEMA.md) from 1990 through the current year
(unless ``--season`` is set to process one year only).

**Source:** MLB Stats API ``/teams/stats`` season pitching (regular ``gameType=R``),
one row per franchise season.

**Context:** ``league`` / ``division`` from Supabase ``teams``; ``runs_factor`` from
``park_factors`` for ``era_plus``; league JSON for FIP constant / league ERA.

**Derived:** ``k_per_9``, ``bb_per_9``, ``hr_per_9``, ``fip``, ``era_plus``. ``whip`` from
the API when present, else ``calc_whip``. ``war`` is left ``NULL``.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Iterable

import config  # noqa: F401
from calculations.fetch_league_averages import get_league_averages, ip_to_outs
from calculations.pitching_calcs import (
    calc_bb_per_9,
    calc_era_plus,
    calc_fip,
    calc_hr_per_9,
    calc_k_per_9,
    calc_whip,
)
from db import get_client

START_SEASON = 1990
MLB_TEAM_STATS_URL = (
    "https://statsapi.mlb.com/api/v1/teams/stats"
    "?season={season}&sportId=1&stats=season&group=pitching&gameType=R"
    "&limit={limit}&offset={offset}"
)
_BATCH_SIZE = 100
_DELAY_SEC = 2
_PARK_FACTORS_PAGE = 1000
_TEAM_META_PAGE = 1000

_UPSERT_COLUMNS = (
    "team_id",
    "team",
    "season",
    "league",
    "division",
    "w",
    "l",
    "era",
    "g",
    "gs",
    "cg",
    "sho",
    "sv",
    "ip",
    "h",
    "r",
    "er",
    "hr",
    "bb",
    "so",
    "whip",
    "fip",
    "k_per_9",
    "bb_per_9",
    "hr_per_9",
    "era_plus",
    "war",
)


def to_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, bool):
        return int(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def mlb_ip_to_db_ip(value: Any) -> float | None:
    """MLB ``inningsPitched`` text -> decimal innings for ``NUMERIC(6,1)``."""

    if value is None:
        return None
    s = str(value).strip()
    if not s or s == "-":
        return None
    outs = ip_to_outs(value)
    return float(round(outs / 3.0, 1))


def load_park_factors_by_team_season(client: Any) -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], float] = {}
    offset = 0
    while True:
        try:
            resp = (
                client.table("park_factors")
                .select("team_id,season,runs_factor")
                .range(offset, offset + _PARK_FACTORS_PAGE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"seed_team_pitching_seasons: park_factors page at offset {offset} failed: {exc}",
                flush=True,
            )
            break
        rows = resp.data or []
        for row in rows:
            tid = row.get("team_id")
            season = row.get("season")
            rf = row.get("runs_factor")
            if tid is None or season is None or rf is None:
                continue
            try:
                out[(int(tid), int(season))] = float(rf)
            except (TypeError, ValueError):
                continue
        if len(rows) < _PARK_FACTORS_PAGE:
            break
        offset += _PARK_FACTORS_PAGE
    return out


def load_team_metadata(client: Any) -> dict[int, dict[str, str | None]]:
    out: dict[int, dict[str, str | None]] = {}
    offset = 0
    while True:
        try:
            resp = (
                client.table("teams")
                .select("id,league,division")
                .range(offset, offset + _TEAM_META_PAGE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"seed_team_pitching_seasons: teams page at offset {offset} failed: {exc}",
                flush=True,
            )
            break
        rows = resp.data or []
        for row in rows:
            tid = row.get("id")
            if tid is None:
                continue
            try:
                out[int(tid)] = {
                    "league": row.get("league"),
                    "division": row.get("division"),
                }
            except (TypeError, ValueError):
                continue
        if len(rows) < _TEAM_META_PAGE:
            break
        offset += _TEAM_META_PAGE
    return out


def warm_league_averages_for_seasons(seasons: Iterable[int]) -> list[int]:
    missing: list[int] = []
    for year in seasons:
        if get_league_averages(year) is None:
            missing.append(year)
    return missing


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill team_pitching_seasons from the MLB Stats API.",
    )
    p.add_argument(
        "--season",
        type=int,
        default=None,
        metavar="YEAR",
        help=(
            "Process only this season. "
            f"Default: full range {START_SEASON} through the current calendar year."
        ),
    )
    return p.parse_args()


def fetch_mlb_team_pitching_splits(season: int, limit: int = 1000) -> list[dict[str, Any]]:
    all_splits: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = MLB_TEAM_STATS_URL.format(season=season, limit=limit, offset=offset)
        req = urllib.request.Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MLB teams/stats pitching failed season={season}: {exc}") from exc

        stats_blocks = payload.get("stats") or []
        if not stats_blocks:
            break
        splits = stats_blocks[0].get("splits") or []
        all_splits.extend(splits)
        if len(splits) < limit:
            break
        offset += limit
    return all_splits


def split_to_base_row(
    split: dict[str, Any],
    season: int,
    team_meta: dict[int, dict[str, str | None]],
) -> dict[str, Any] | None:
    team = split.get("team") or {}
    stat = split.get("stat") or {}
    tid = team.get("id")
    if tid is None:
        return None
    try:
        team_id = int(tid)
    except (TypeError, ValueError):
        return None

    meta = team_meta.get(team_id, {})

    return {
        "team_id": team_id,
        "team": team.get("name"),
        "season": season,
        "league": meta.get("league"),
        "division": meta.get("division"),
        "w": to_int(stat.get("wins")),
        "l": to_int(stat.get("losses")),
        "era": to_float(stat.get("era")),
        "g": to_int(stat.get("gamesPlayed")),
        "gs": to_int(stat.get("gamesStarted")),
        "cg": to_int(stat.get("completeGames")),
        "sho": to_int(stat.get("shutouts")),
        "sv": to_int(stat.get("saves")),
        "ip": mlb_ip_to_db_ip(stat.get("inningsPitched")),
        "h": to_int(stat.get("hits")),
        "r": to_int(stat.get("runs")),
        "er": to_int(stat.get("earnedRuns")),
        "hr": to_int(stat.get("homeRuns")),
        "bb": to_int(stat.get("baseOnBalls")),
        "so": to_int(stat.get("strikeOuts")),
        "whip": to_float(stat.get("whip")),
        "fip": None,
        "k_per_9": None,
        "bb_per_9": None,
        "hr_per_9": None,
        "era_plus": None,
        "war": None,
    }


def merge_derived_team_pitching(
    row: dict[str, Any],
    park_by_team_season: dict[tuple[int, int], float],
) -> None:
    season = int(row["season"])
    ip_f = float(row["ip"]) if row.get("ip") is not None else None
    h_f = float(row["h"]) if row.get("h") is not None else None
    bb_f = float(row["bb"]) if row.get("bb") is not None else None
    hr_f = float(row["hr"]) if row.get("hr") is not None else None
    so_f = float(row["so"]) if row.get("so") is not None else None

    k9 = calc_k_per_9(so_f, ip_f)
    bb9 = calc_bb_per_9(bb_f, ip_f)
    hr9 = calc_hr_per_9(hr_f, ip_f)
    row["k_per_9"] = round(k9, 2) if k9 is not None else None
    row["bb_per_9"] = round(bb9, 2) if bb9 is not None else None
    row["hr_per_9"] = round(hr9, 2) if hr9 is not None else None

    if row.get("whip") is None:
        cw = calc_whip(h_f, bb_f, ip_f)
        row["whip"] = round(cw, 3) if cw is not None else None

    row["fip"] = (
        round(cf, 2)
        if (cf := calc_fip(hr_f, bb_f, so_f, ip_f, season)) is not None
        else None
    )

    tid = row.get("team_id")
    pf = 1.0
    if tid is not None:
        pf = park_by_team_season.get((int(tid), season), 1.0)

    erap = calc_era_plus(row.get("era"), season, park_factor=pf)
    row["era_plus"] = int(round(erap)) if erap is not None else None
    row["war"] = None


def row_for_upsert(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in _UPSERT_COLUMNS}


def upsert_batches(client: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    ok = 0
    failed = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = [row_for_upsert(r) for r in rows[i : i + _BATCH_SIZE]]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("team_pitching_seasons").upsert(
                batch,
                on_conflict="team_id,season",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_team_pitching_seasons: upsert batch {batch_no} failed: {exc}")
            failed += len(batch)
    return ok, failed


def main() -> None:
    args = _parse_args()
    end_year = datetime.now().year

    if args.season is not None:
        if args.season < START_SEASON:
            raise SystemExit(
                f"seed_team_pitching_seasons: --season must be >= {START_SEASON} "
                f"(got {args.season})."
            )
        years = [args.season]
        range_desc = f"season {args.season} only"
    else:
        years = list(range(START_SEASON, end_year + 1))
        range_desc = f"{START_SEASON}..{end_year}"

    print(
        f"seed_team_pitching_seasons: MLB teams/stats pitching {range_desc}; "
        f"derived from pitching_calcs + park_factors + league averages; "
        f"delay between seasons={_DELAY_SEC}s.",
        flush=True,
    )

    client = get_client()
    park_by_team_season = load_park_factors_by_team_season(client)
    print(
        f"seed_team_pitching_seasons: loaded {len(park_by_team_season)} "
        f"park_factors (team_id, season) keys.",
        flush=True,
    )
    team_meta = load_team_metadata(client)
    print(
        f"seed_team_pitching_seasons: loaded {len(team_meta)} teams (league/division).",
        flush=True,
    )

    missing_lg = warm_league_averages_for_seasons(years)
    if missing_lg:
        print(
            f"seed_team_pitching_seasons: [warn] league averages missing for "
            f"{len(missing_lg)} season(s) (fip / era_plus may be null): "
            f"{missing_lg[:25]}{'…' if len(missing_lg) > 25 else ''}",
            flush=True,
        )

    total_ok = 0
    total_fail = 0
    seasons_run = 0
    n_years = len(years)

    for idx, year in enumerate(years):
        splits = fetch_mlb_team_pitching_splits(year)
        merged: list[dict[str, Any]] = []
        for sp in splits:
            base = split_to_base_row(sp, year, team_meta)
            if base is None:
                continue
            merge_derived_team_pitching(base, park_by_team_season)
            merged.append(base)

        ok, fail = upsert_batches(client, merged)
        total_ok += ok
        total_fail += fail
        seasons_run += 1

        print(
            f"seed_team_pitching_seasons: season {year} — "
            f"MLB splits={len(splits)}, rows={len(merged)}, "
            f"upsert_ok_batch={ok}, upsert_fail_batch={fail}",
            flush=True,
        )

        if idx < n_years - 1:
            time.sleep(_DELAY_SEC)

    print(
        f"seed_team_pitching_seasons: finished — seasons={seasons_run}, "
        f"rows upsert accepted={total_ok}, rows in failed batches={total_fail}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
