"""
Load ``player_fielding_seasons`` (SCHEMA.md) from 1990 through the current year
(unless ``--season`` is set to process one year only).

**Source:** MLB Stats API season fielding stats (regular season ``gameType=R``), one row per
player / team / defensive position.

**Derived:** ``rf_per_9`` via ``calc_rf_per_9(po, a, inn)`` and ``rf_per_g`` via
``calc_rf_per_g(po, a, g)``. ``drs`` and ``oaa`` are left ``NULL`` (Statcast).
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
from calculations.fetch_league_averages import ip_to_outs
from calculations.fielding_calcs import calc_rf_per_9, calc_rf_per_g
from db import get_client

START_SEASON = 1990
MLB_STATS_URL = (
    "https://statsapi.mlb.com/api/v1/stats"
    "?stats=season&group=fielding&season={season}&sportId=1&playerPool=all"
    "&gameType=R&limit={limit}&offset={offset}"
)
_BATCH_SIZE = 500
_DELAY_SEC = 2


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


def mlb_innings_to_db_inn(value: Any) -> float | None:
    """MLB fielding ``innings`` text (e.g. ``138.0``, ``78.1``) -> ``NUMERIC(7,1)`` decimal innings."""

    if value is None:
        return None
    s = str(value).strip()
    if not s or s == "-":
        return None
    outs = ip_to_outs(value)
    return float(round(outs / 3.0, 1))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill player_fielding_seasons from the MLB Stats API.",
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


def fetch_mlb_fielding_splits(season: int, limit: int = 1000) -> list[dict[str, Any]]:
    all_splits: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = MLB_STATS_URL.format(season=season, limit=limit, offset=offset)
        req = urllib.request.Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MLB fielding stats failed season={season}: {exc}") from exc

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
    pos = split.get("position") if isinstance(split.get("position"), dict) else {}

    pid = player.get("id")
    if pid is None:
        return None
    pos_abbrev = pos.get("abbreviation")
    if not isinstance(pos_abbrev, str) or not pos_abbrev.strip():
        return None
    tid = team.get("id")

    fpct = to_float(stat.get("fielding"))
    if fpct is not None:
        fpct = round(fpct, 3)

    return {
        "player_id": int(pid),
        "player_name": player.get("fullName"),
        "season": season,
        "team_id": int(tid) if tid is not None else None,
        "team": team.get("name"),
        "position": pos_abbrev.strip(),
        "g": to_int(stat.get("gamesPlayed")),
        "gs": to_int(stat.get("gamesStarted")),
        "inn": mlb_innings_to_db_inn(stat.get("innings")),
        "po": to_int(stat.get("putOuts")),
        "a": to_int(stat.get("assists")),
        "e": to_int(stat.get("errors")),
        "dp": to_int(stat.get("doublePlays")),
        "fld_pct": fpct,
        "rf_per_9": None,
        "rf_per_g": None,
        "drs": None,
        "oaa": None,
    }


def merge_derived_fielding(row: dict[str, Any]) -> None:
    inn_f = float(row["inn"]) if row.get("inn") is not None else None
    po_f = float(row["po"]) if row.get("po") is not None else None
    a_f = float(row["a"]) if row.get("a") is not None else None
    g_f = float(row["g"]) if row.get("g") is not None else None
    rf9 = calc_rf_per_9(po_f, a_f, inn_f)
    row["rf_per_9"] = round(rf9, 2) if rf9 is not None else None
    rfg = calc_rf_per_g(po_f, a_f, g_f)
    row["rf_per_g"] = round(rfg, 2) if rfg is not None else None


_UPSERT_COLUMNS = (
    "player_id",
    "player_name",
    "season",
    "team_id",
    "team",
    "position",
    "g",
    "gs",
    "inn",
    "po",
    "a",
    "e",
    "dp",
    "fld_pct",
    "rf_per_9",
    "rf_per_g",
    "drs",
    "oaa",
)


def row_for_upsert(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in _UPSERT_COLUMNS}


def upsert_batches(client: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    ok = 0
    failed = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = [row_for_upsert(r) for r in rows[i : i + _BATCH_SIZE]]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("player_fielding_seasons").upsert(
                batch,
                on_conflict="player_id,season,team_id,position",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_player_fielding_seasons: upsert batch {batch_no} failed: {exc}")
            failed += len(batch)
    return ok, failed


def main() -> None:
    args = _parse_args()
    end_year = datetime.now().year

    if args.season is not None:
        if args.season < START_SEASON:
            raise SystemExit(
                f"seed_player_fielding_seasons: --season must be >= {START_SEASON} "
                f"(got {args.season})."
            )
        years = [args.season]
        range_desc = f"season {args.season} only"
    else:
        years = list(range(START_SEASON, end_year + 1))
        range_desc = f"{START_SEASON}..{end_year}"

    print(
        f"seed_player_fielding_seasons: MLB {range_desc}; "
        f"derived rf_per_9, rf_per_g from fielding_calcs; delay between seasons={_DELAY_SEC}s.",
        flush=True,
    )

    client = get_client()
    total_ok = 0
    total_fail = 0
    seasons_run = 0
    n_years = len(years)

    for idx, year in enumerate(years):
        splits = fetch_mlb_fielding_splits(year)
        merged: list[dict[str, Any]] = []
        for sp in splits:
            base = split_to_base_row(sp, year)
            if base is None:
                continue
            merge_derived_fielding(base)
            merged.append(base)

        ok, fail = upsert_batches(client, merged)
        total_ok += ok
        total_fail += fail
        seasons_run += 1

        print(
            f"seed_player_fielding_seasons: season {year} — "
            f"MLB splits={len(splits)}, rows={len(merged)}, "
            f"upsert_ok_batch={ok}, upsert_fail_batch={fail}",
            flush=True,
        )

        if idx < n_years - 1:
            time.sleep(_DELAY_SEC)

    print(
        f"seed_player_fielding_seasons: finished — seasons={seasons_run}, "
        f"rows upsert accepted={total_ok}, rows in failed batches={total_fail}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
