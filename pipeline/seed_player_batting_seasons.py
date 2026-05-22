"""
Load ``player_batting_seasons`` (SCHEMA.md) from 1990 through the current year
(unless ``--season`` is set to process one year only).

**Source:** MLB Stats API season hitting stats (counting stats only).

**Derived metrics** (rates, linear weights, Run environment stats, Statcast overlays, etc.) are owned by
``calc_batting_season_metrics.py`` and are intentionally **not** written by this script.
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
MLB_STATS_URL = (
    "https://statsapi.mlb.com/api/v1/stats"
    "?stats=season&group=hitting&season={season}&sportId=1&playerPool=all&limit={limit}&offset={offset}"
)
_RPC_BATCH = 500
_DELAY_SEC = 2

_UPSERT_COLUMNS = (
    "player_id",
    "player_name",
    "season",
    "team_id",
    "team",
    "league",
    "g",
    "ab",
    "pa",
    "r",
    "h",
    "doubles",
    "triples",
    "hr",
    "rbi",
    "sb",
    "cs",
    "bb",
    "so",
    "hbp",
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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill player_batting_seasons from the MLB Stats API.",
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


def fetch_mlb_hitting_splits(season: int, limit: int = 1000) -> list[dict[str, Any]]:
    all_splits: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = MLB_STATS_URL.format(season=season, limit=limit, offset=offset)
        req = urllib.request.Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MLB stats failed season={season}: {exc}") from exc

        stats_blocks = payload.get("stats") or []
        if not stats_blocks:
            break
        splits = stats_blocks[0].get("splits") or []
        all_splits.extend(splits)
        if len(splits) < limit:
            break
        offset += limit
    return all_splits


def split_to_base_row(split: dict[str, Any], season: int) -> dict[str, Any] | None:
    player = split.get("player") or {}
    team = split.get("team") or {}
    stat = split.get("stat") or {}
    league = split.get("league") or {}

    pid = player.get("id")
    if pid is None:
        return None
    tid = team.get("id")

    return {
        "player_id": int(pid),
        "player_name": player.get("fullName"),
        "season": season,
        "team_id": int(tid) if tid is not None else None,
        "team": team.get("name"),
        "league": league.get("name") if isinstance(league, dict) else None,
        "g": to_int(stat.get("gamesPlayed")),
        "ab": to_int(stat.get("atBats")),
        "pa": to_int(stat.get("plateAppearances")),
        "r": to_int(stat.get("runs")),
        "h": to_int(stat.get("hits")),
        "doubles": to_int(stat.get("doubles")),
        "triples": to_int(stat.get("triples")),
        "hr": to_int(stat.get("homeRuns")),
        "rbi": to_int(stat.get("rbi")),
        "sb": to_int(stat.get("stolenBases")),
        "cs": to_int(stat.get("caughtStealing")),
        "bb": to_int(stat.get("baseOnBalls")),
        "so": to_int(stat.get("strikeOuts")),
        "hbp": to_int(stat.get("hitByPitch")),
    }


def row_for_upsert(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in _UPSERT_COLUMNS}


def upsert_batches(client: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    ok = 0
    failed = 0
    for i in range(0, len(rows), _RPC_BATCH):
        batch = [row_for_upsert(r) for r in rows[i : i + _RPC_BATCH]]
        batch_no = i // _RPC_BATCH + 1
        try:
            client.rpc(
                "upsert_player_batting_seasons",
                {"rows": batch},
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_player_batting_seasons: upsert batch {batch_no} failed: {exc}")
            failed += len(batch)
    return ok, failed


def main() -> None:
    args = _parse_args()
    end_year = datetime.now().year

    if args.season is not None:
        if args.season < START_SEASON:
            raise SystemExit(
                f"seed_player_batting_seasons: --season must be >= {START_SEASON} "
                f"(got {args.season})."
            )
        years = [args.season]
        range_desc = f"season {args.season} only"
    else:
        years = list(range(START_SEASON, end_year + 1))
        range_desc = f"{START_SEASON}..{end_year}"

    print(
        f"seed_player_batting_seasons: MLB {range_desc}; counting stats only "
        f"(delay between seasons={_DELAY_SEC}s).",
        flush=True,
    )

    client = get_client()

    total_ok = 0
    total_fail = 0
    seasons_run = 0

    n_years = len(years)
    for idx, year in enumerate(years):
        splits = fetch_mlb_hitting_splits(year)
        merged: list[dict[str, Any]] = []
        for sp in splits:
            base = split_to_base_row(sp, year)
            if base is None:
                continue
            merged.append(base)

        ok, fail = upsert_batches(client, merged)
        total_ok += ok
        total_fail += fail
        seasons_run += 1

        print(
            f"seed_player_batting_seasons: season {year} — "
            f"MLB splits={len(splits)}, rows={len(merged)}, "
            f"upsert_ok_batch={ok}, upsert_fail_batch={fail}",
            flush=True,
        )

        if idx < n_years - 1:
            time.sleep(_DELAY_SEC)

    print(
        f"seed_player_batting_seasons: finished — seasons={seasons_run}, "
        f"rows upsert accepted={total_ok}, rows in failed batches={total_fail}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
