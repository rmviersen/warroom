"""
Load ``player_batting_seasons`` (SCHEMA.md) from 1990 through the current year
(unless ``--season`` is set to process one year only).

**Source:** MLB Stats API season hitting stats (counting stats, slash lines, BABIP).

**Derived:** ``iso``, ``bb_pct``, ``k_pct``, ``woba``, ``ops_plus``, ``wrc_plus``, and ``war``
from ``batting_calcs`` / ``get_league_averages`` / ``get_park_factor`` (see ``merge_derived_advanced()``).
Park for ``ops_plus`` uses batched ``park_factors``; ``wrc_plus`` / ``batting_war`` use ``get_park_factor``.
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
from calculations.batting_calcs import (
    calc_batting_war,
    calc_bb_pct,
    calc_iso,
    calc_k_pct,
    calc_ops_plus,
    calc_singles,
    calc_woba,
    calc_wrc_plus,
)
from calculations.constants import get_park_factor
from calculations.fetch_league_averages import get_league_averages
from db import get_client

START_SEASON = 1990
MLB_STATS_URL = (
    "https://statsapi.mlb.com/api/v1/stats"
    "?stats=season&group=hitting&season={season}&sportId=1&playerPool=all&limit={limit}&offset={offset}"
)
_BATCH_SIZE = 500
_DELAY_SEC = 2
_PARK_FACTORS_PAGE = 1000

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
    "avg",
    "obp",
    "slg",
    "ops",
    "babip",
    "iso",
    "bb_pct",
    "k_pct",
    "ops_plus",
    "woba",
    "wrc_plus",
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


def load_park_factors_by_team_season(client: Any) -> dict[tuple[int, int], float]:
    """``(team_id, season) -> runs_factor`` from ``park_factors`` (paginated)."""

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
                f"seed_player_batting_seasons: park_factors page at offset {offset} failed: {exc}",
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


def warm_league_averages_for_seasons(seasons: Iterable[int]) -> list[int]:
    """Load ``league_averages.json`` once (first ``get_league_averages`` call) and note gaps."""

    missing: list[int] = []
    for year in seasons:
        if get_league_averages(year) is None:
            missing.append(year)
    return missing


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

    pp = player.get("primaryPosition")
    prim_pos = pp if isinstance(pp, dict) else {}
    pos_abbrev = prim_pos.get("abbreviation")
    _position = pos_abbrev if isinstance(pos_abbrev, str) else None

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
        "avg": to_float(stat.get("avg")),
        "obp": to_float(stat.get("obp")),
        "slg": to_float(stat.get("slg")),
        "ops": to_float(stat.get("ops")),
        "babip": to_float(stat.get("babip")),
        "_hbp": to_int(stat.get("hitByPitch")),
        "_ibb": to_int(stat.get("intentionalWalks")),
        "_position": _position,
        "iso": None,
        "bb_pct": None,
        "k_pct": None,
        "ops_plus": None,
        "woba": None,
        "wrc_plus": None,
        "war": None,
    }


def merge_derived_advanced(
    row: dict[str, Any],
    park_by_team_season: dict[tuple[int, int], float],
) -> None:
    """Fill rate stats from ``batting_calcs``; pop internal ``_hbp`` / ``_ibb`` / ``_position``."""

    season = row["season"]
    hbp_i = row.pop("_hbp", None)
    position_s = row.pop("_position", None)
    row.pop("_ibb", None)  # from ``intentionalWalks``; reserved for future uBB / wOBA tweaks
    hbp_f = float(hbp_i) if hbp_i is not None else None

    row["iso"] = calc_iso(row.get("slg"), row.get("avg"))
    _bb_pct = calc_bb_pct(
        float(row["bb"]) if row.get("bb") is not None else None,
        float(row["pa"]) if row.get("pa") is not None else None,
    )
    _k_pct = calc_k_pct(
        float(row["so"]) if row.get("so") is not None else None,
        float(row["pa"]) if row.get("pa") is not None else None,
    )
    row["bb_pct"] = round(_bb_pct * 100.0, 1) if _bb_pct is not None else None
    row["k_pct"] = round(_k_pct * 100.0, 1) if _k_pct is not None else None

    singles = calc_singles(
        float(row["h"]) if row.get("h") is not None else None,
        float(row["doubles"]) if row.get("doubles") is not None else None,
        float(row["triples"]) if row.get("triples") is not None else None,
        float(row["hr"]) if row.get("hr") is not None else None,
    )
    # MLB API: ``baseOnBalls`` is walks (including IBB); ``hitByPitch`` is separate.
    row["woba"] = calc_woba(
        float(row["bb"]) if row.get("bb") is not None else None,
        hbp_f,
        singles,
        float(row["doubles"]) if row.get("doubles") is not None else None,
        float(row["triples"]) if row.get("triples") is not None else None,
        float(row["hr"]) if row.get("hr") is not None else None,
        float(row["pa"]) if row.get("pa") is not None else None,
        int(season),
    )

    tid = row.get("team_id")
    pf = 1.0
    if tid is not None:
        pf = park_by_team_season.get((int(tid), int(season)), 1.0)

    raw_ops_plus = calc_ops_plus(row.get("obp"), row.get("slg"), int(season), park_factor=pf)
    row["ops_plus"] = int(round(raw_ops_plus)) if raw_ops_plus is not None else None

    lg_row = get_league_averages(int(season))
    if lg_row is None:
        row["wrc_plus"] = None
        row["war"] = None
    else:
        lg_woba = to_float(lg_row.get("lgwOBA"))
        lg_r = to_float(lg_row.get("lgR"))
        lg_pa = to_float(lg_row.get("lgPA"))
        if lg_r is not None and lg_pa is not None and float(lg_pa) != 0:
            lg_rperpa = float(lg_r) / float(lg_pa)
        else:
            lg_rperpa = None
        lg_ip = to_float(lg_row.get("lgIP"))
        pf_wrc = get_park_factor(row.get("team_id"), int(season))
        pa_f = float(row["pa"]) if row.get("pa") is not None else None
        g_f = float(row["g"]) if row.get("g") is not None else None
        row["wrc_plus"] = calc_wrc_plus(
            row.get("woba"),
            pa_f,
            int(season),
            lg_woba,
            lg_rperpa,
            park_factor=pf_wrc,
        )
        row["war"] = calc_batting_war(
            row.get("woba"),
            pa_f,
            g_f,
            position_s,
            int(season),
            lg_woba,
            lg_r,
            lg_pa,
            lg_ip,
            park_factor=pf_wrc,
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
            client.table("player_batting_seasons").upsert(
                batch,
                on_conflict="player_id,season,team_id",
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
        f"seed_player_batting_seasons: MLB {range_desc}; "
        f"derived advanced from calculations + park_factors; "
        f"delay between seasons={_DELAY_SEC}s.",
        flush=True,
    )

    client = get_client()
    park_by_team_season = load_park_factors_by_team_season(client)
    print(
        f"seed_player_batting_seasons: loaded {len(park_by_team_season)} "
        f"park_factors (team_id, season) keys.",
        flush=True,
    )

    missing_lg = warm_league_averages_for_seasons(years)
    if missing_lg:
        print(
            f"seed_player_batting_seasons: [warn] league averages missing for "
            f"{len(missing_lg)} season(s) (ops+/woba may be null): "
            f"{missing_lg[:25]}{'…' if len(missing_lg) > 25 else ''}",
            flush=True,
        )

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
            merge_derived_advanced(base, park_by_team_season)
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
