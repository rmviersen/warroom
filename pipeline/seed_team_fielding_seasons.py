"""
Load ``team_fielding_seasons`` (SCHEMA.md) from 1990 through the current year
(unless ``--season`` is set to process one year only).

**Source:** MLB Stats API ``/teams/stats`` season fielding (regular ``gameType=R``),
one row per franchise season.

**Context:** ``league`` from Supabase ``teams`` (``division`` is not stored on this table).

**``drs``** is left ``NULL`` (not available from this endpoint).
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

import config  # noqa: F401
from db import get_client

START_SEASON = 1990
MLB_TEAM_STATS_URL = (
    "https://statsapi.mlb.com/api/v1/teams/stats"
    "?season={season}&sportId=1&stats=season&group=fielding&gameType=R"
    "&limit={limit}&offset={offset}"
)
_BATCH_SIZE = 100
_DELAY_SEC = 2
_TEAM_META_PAGE = 1000

_UPSERT_COLUMNS = (
    "team_id",
    "team",
    "season",
    "league",
    "g",
    "po",
    "a",
    "e",
    "dp",
    "fld_pct",
    "drs",
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


def load_team_league_by_id(client: Any) -> dict[int, str | None]:
    """``team_id -> league`` from Supabase ``teams``."""

    out: dict[int, str | None] = {}
    offset = 0
    while True:
        try:
            resp = (
                client.table("teams")
                .select("id,league")
                .range(offset, offset + _TEAM_META_PAGE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"seed_team_fielding_seasons: teams page at offset {offset} failed: {exc}",
                flush=True,
            )
            break
        rows = resp.data or []
        for row in rows:
            tid = row.get("id")
            if tid is None:
                continue
            try:
                out[int(tid)] = row.get("league")
            except (TypeError, ValueError):
                continue
        if len(rows) < _TEAM_META_PAGE:
            break
        offset += _TEAM_META_PAGE
    return out


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill team_fielding_seasons from the MLB Stats API.",
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


def fetch_mlb_team_fielding_splits(season: int, limit: int = 1000) -> list[dict[str, Any]]:
    all_splits: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = MLB_TEAM_STATS_URL.format(season=season, limit=limit, offset=offset)
        req = urllib.request.Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MLB teams/stats fielding failed season={season}: {exc}") from exc

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
    team_league: dict[int, str | None],
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

    fpct = to_float(stat.get("fielding"))
    if fpct is not None:
        fpct = round(fpct, 3)

    return {
        "team_id": team_id,
        "team": team.get("name"),
        "season": season,
        "league": team_league.get(team_id),
        "g": to_int(stat.get("gamesPlayed")),
        "po": to_int(stat.get("putOuts")),
        "a": to_int(stat.get("assists")),
        "e": to_int(stat.get("errors")),
        "dp": to_int(stat.get("doublePlays")),
        "fld_pct": fpct,
        "drs": None,
    }


def row_for_upsert(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in _UPSERT_COLUMNS}


def upsert_batches(client: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    ok = 0
    failed = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = [row_for_upsert(r) for r in rows[i : i + _BATCH_SIZE]]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("team_fielding_seasons").upsert(
                batch,
                on_conflict="team_id,season",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_team_fielding_seasons: upsert batch {batch_no} failed: {exc}")
            failed += len(batch)
    return ok, failed


def main() -> None:
    args = _parse_args()
    end_year = datetime.now().year

    if args.season is not None:
        if args.season < START_SEASON:
            raise SystemExit(
                f"seed_team_fielding_seasons: --season must be >= {START_SEASON} "
                f"(got {args.season})."
            )
        years = [args.season]
        range_desc = f"season {args.season} only"
    else:
        years = list(range(START_SEASON, end_year + 1))
        range_desc = f"{START_SEASON}..{end_year}"

    print(
        f"seed_team_fielding_seasons: MLB teams/stats fielding {range_desc}; "
        f"delay between seasons={_DELAY_SEC}s.",
        flush=True,
    )

    client = get_client()
    team_league = load_team_league_by_id(client)
    print(
        f"seed_team_fielding_seasons: loaded {len(team_league)} teams (league).",
        flush=True,
    )

    total_ok = 0
    total_fail = 0
    seasons_run = 0
    n_years = len(years)

    for idx, year in enumerate(years):
        splits = fetch_mlb_team_fielding_splits(year)
        merged: list[dict[str, Any]] = []
        for sp in splits:
            base = split_to_base_row(sp, year, team_league)
            if base is None:
                continue
            merged.append(base)

        ok, fail = upsert_batches(client, merged)
        total_ok += ok
        total_fail += fail
        seasons_run += 1

        print(
            f"seed_team_fielding_seasons: season {year} — "
            f"MLB splits={len(splits)}, rows={len(merged)}, "
            f"upsert_ok_batch={ok}, upsert_fail_batch={fail}",
            flush=True,
        )

        if idx < n_years - 1:
            time.sleep(_DELAY_SEC)

    print(
        f"seed_team_fielding_seasons: finished — seasons={seasons_run}, "
        f"rows upsert accepted={total_ok}, rows in failed batches={total_fail}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
