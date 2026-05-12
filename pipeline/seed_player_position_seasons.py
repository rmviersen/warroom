"""
Load ``player_position_seasons`` (SCHEMA.md) from MLB hitting splits **by defensive position**.

**Source:** MLB Stats API ``/api/v1/stats`` with ``stats=season&group=hitting&sportId=1&playerPool=all&gameType=R``,
plus one request per tracked position using the ``position`` query parameter (MLB ``/positions`` numeric
``code``: 2=C, 3=1B, …, 10=DH). The Stats API documents ``sitCodes`` for *situation* splits (see team_stats),
not fielding position; positional filters use ``position``.

**Derived:** ``woba`` via ``calc_woba``, ``ops_plus`` via ``calc_ops_plus``, ``wrc_plus`` via ``calc_wrc_plus``
(league ``lgR``/``lgPA`` for runs/PA; wOBA scale from ``get_woba_scale`` inside ``calc_wrc_plus``).

Park: batched ``park_factors`` for ``ops_plus``; ``get_park_factor`` for ``wrc_plus`` (same as ``seed_player_batting_seasons``).
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable

import config  # noqa: F401
from calculations.batting_calcs import calc_ops_plus, calc_singles, calc_woba, calc_wrc_plus
from calculations.constants import get_park_factor
from calculations.fetch_league_averages import get_league_averages
from db import get_client

MIN_SEASON = 1990
_BATCH_SIZE = 500
_DELAY_SEC = 2
_DELAY_POSITION_SEC = 0.5
_PARK_FACTORS_PAGE = 1000

# MLB ``/positions`` ``code`` values for seasonal hitting while playing each defensive spot (exclude P / PH etc.).
# Stored ``position`` uses our abbreviations for SCHEMA / app consistency (C, 1B, …, DH).
_POSITION_SPECS: tuple[tuple[str, str], ...] = (
    ("2", "C"),
    ("3", "1B"),
    ("4", "2B"),
    ("5", "3B"),
    ("6", "SS"),
    ("7", "LF"),
    ("8", "CF"),
    ("9", "RF"),
    ("10", "DH"),
)

_UPSERT_COLUMNS = (
    "player_id",
    "player_name",
    "season",
    "team_id",
    "team",
    "position",
    "g",
    "pa",
    "ab",
    "h",
    "doubles",
    "triples",
    "hr",
    "bb",
    "so",
    "hbp",
    "avg",
    "obp",
    "slg",
    "ops",
    "woba",
    "ops_plus",
    "wrc_plus",
    "updated_at",
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
                f"seed_player_position_seasons: park_factors page at offset {offset} failed: {exc}",
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
    """Prime ``get_league_averages`` for each season and report missing JSON rows."""

    missing: list[int] = []
    for year in seasons:
        if get_league_averages(year) is None:
            missing.append(year)
    return missing


def _stats_url(season: int, position_code: str, limit: int, offset: int) -> str:
    q = urllib.parse.urlencode(
        {
            "stats": "season",
            "group": "hitting",
            "season": season,
            "sportId": "1",
            "playerPool": "all",
            "gameType": "R",
            "position": position_code,
            "limit": limit,
            "offset": offset,
        }
    )
    return f"https://statsapi.mlb.com/api/v1/stats?{q}"


def fetch_mlb_position_splits(season: int, position_code: str, limit: int = 1000) -> list[dict[str, Any]]:
    all_splits: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = _stats_url(season, position_code, limit, offset)
        req = urllib.request.Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"MLB stats failed season={season} position={position_code}: {exc}"
            ) from exc

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
    position_abbrev: str,
) -> dict[str, Any] | None:
    player = split.get("player") or {}
    team = split.get("team") or {}
    stat = split.get("stat") or {}

    pid = player.get("id")
    if pid is None:
        return None
    tid = team.get("id")
    hbp_val = to_int(stat.get("hitByPitch"))

    return {
        "player_id": int(pid),
        "player_name": player.get("fullName"),
        "season": season,
        "team_id": int(tid) if tid is not None else None,
        "team": team.get("name"),
        "position": position_abbrev,
        "g": to_int(stat.get("gamesPlayed")),
        "ab": to_int(stat.get("atBats")),
        "pa": to_int(stat.get("plateAppearances")),
        "h": to_int(stat.get("hits")),
        "doubles": to_int(stat.get("doubles")),
        "triples": to_int(stat.get("triples")),
        "hr": to_int(stat.get("homeRuns")),
        "bb": to_int(stat.get("baseOnBalls")),
        "so": to_int(stat.get("strikeOuts")),
        "hbp": hbp_val,
        "avg": to_float(stat.get("avg")),
        "obp": to_float(stat.get("obp")),
        "slg": to_float(stat.get("slg")),
        "ops": to_float(stat.get("ops")),
        "_hbp": hbp_val,
        "woba": None,
        "ops_plus": None,
        "wrc_plus": None,
    }


def merge_derived(
    row: dict[str, Any],
    park_by_team_season: dict[tuple[int, int], float],
) -> None:
    """Fill ``woba``, ``ops_plus``, ``wrc_plus``; pop internal keys."""

    season = row["season"]
    hbp_i = row.pop("_hbp", None)
    hbp_f = float(hbp_i) if hbp_i is not None else None

    singles = calc_singles(
        float(row["h"]) if row.get("h") is not None else None,
        float(row["doubles"]) if row.get("doubles") is not None else None,
        float(row["triples"]) if row.get("triples") is not None else None,
        float(row["hr"]) if row.get("hr") is not None else None,
    )
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
    pf_ops = 1.0
    if tid is not None:
        pf_ops = park_by_team_season.get((int(tid), int(season)), 1.0)

    raw_ops_plus = calc_ops_plus(
        row.get("obp"), row.get("slg"), int(season), park_factor=pf_ops
    )
    row["ops_plus"] = int(round(raw_ops_plus)) if raw_ops_plus is not None else None

    lg_row = get_league_averages(int(season))
    if lg_row is None:
        row["wrc_plus"] = None
    else:
        lg_woba = to_float(lg_row.get("lgwOBA"))
        lg_r = to_float(lg_row.get("lgR"))
        lg_pa = to_float(lg_row.get("lgPA"))
        if lg_r is not None and lg_pa is not None and float(lg_pa) != 0:
            lg_rperpa = float(lg_r) / float(lg_pa)
        else:
            lg_rperpa = None
        pf_wrc = get_park_factor(row.get("team_id"), int(season))
        pa_f = float(row["pa"]) if row.get("pa") is not None else None
        row["wrc_plus"] = calc_wrc_plus(
            row.get("woba"),
            pa_f,
            int(season),
            lg_woba,
            lg_rperpa,
            park_factor=pf_wrc,
        )


def row_for_upsert(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r[k] for k in _UPSERT_COLUMNS if k != "updated_at"}
    out["updated_at"] = datetime.now(timezone.utc).isoformat()
    return out


def upsert_batches(client: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    ok = 0
    failed = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = [row_for_upsert(r) for r in rows[i : i + _BATCH_SIZE]]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("player_position_seasons").upsert(
                batch,
                on_conflict="player_id,season,team_id,position",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_player_position_seasons: upsert batch {batch_no} failed: {exc}")
            failed += len(batch)
    return ok, failed


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Backfill player_position_seasons from MLB positional hitting splits "
            "(see SCHEMA.md)."
        ),
    )
    p.add_argument(
        "--season",
        type=int,
        default=None,
        metavar="YEAR",
        help=f"Process only this season (must be >= {MIN_SEASON}).",
    )
    p.add_argument(
        "--start",
        type=int,
        default=None,
        metavar="YEAR",
        help=(
            "Backfill from this season through the current calendar year "
            f"(must be >= {MIN_SEASON}). Ignored if --season is set."
        ),
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    end_year = datetime.now().year

    if args.season is not None and args.start is not None:
        raise SystemExit(
            "seed_player_position_seasons: use at most one of --season or --start."
        )

    if args.season is not None:
        if args.season < MIN_SEASON:
            raise SystemExit(
                f"seed_player_position_seasons: --season must be >= {MIN_SEASON} "
                f"(got {args.season})."
            )
        years = [args.season]
        range_desc = f"season {args.season} only"
    elif args.start is not None:
        if args.start < MIN_SEASON:
            raise SystemExit(
                f"seed_player_position_seasons: --start must be >= {MIN_SEASON} "
                f"(got {args.start})."
            )
        years = list(range(args.start, end_year + 1))
        range_desc = f"{args.start}..{end_year}"
    else:
        years = [end_year]
        range_desc = f"season {end_year} only (default)"

    print(
        f"seed_player_position_seasons: MLB {range_desc}; "
        f"{len(_POSITION_SPECS)} defensive positions per season; "
        f"delay between seasons={_DELAY_SEC}s, between position requests={_DELAY_POSITION_SEC}s.",
        flush=True,
    )

    client = get_client()
    park_by_team_season = load_park_factors_by_team_season(client)
    print(
        f"seed_player_position_seasons: loaded {len(park_by_team_season)} "
        f"park_factors (team_id, season) keys.",
        flush=True,
    )

    missing_lg = warm_league_averages_for_seasons(years)
    if missing_lg:
        print(
            f"seed_player_position_seasons: [warn] league averages missing for "
            f"{len(missing_lg)} season(s) (wrc+/ops+ may be null): "
            f"{missing_lg[:25]}{'…' if len(missing_lg) > 25 else ''}",
            flush=True,
        )

    total_ok = 0
    total_fail = 0
    seasons_run = 0
    n_years = len(years)

    for idx, year in enumerate(years):
        merged: list[dict[str, Any]] = []
        total_splits = 0

        for pos_i, (pos_code, pos_abbrev) in enumerate(_POSITION_SPECS):
            splits = fetch_mlb_position_splits(year, pos_code)
            total_splits += len(splits)
            for sp in splits:
                base = split_to_base_row(sp, year, pos_abbrev)
                if base is None:
                    continue
                merge_derived(base, park_by_team_season)
                merged.append(base)

            if pos_i < len(_POSITION_SPECS) - 1:
                time.sleep(_DELAY_POSITION_SEC)

        ok, fail = upsert_batches(client, merged)
        total_ok += ok
        total_fail += fail
        seasons_run += 1

        print(
            f"seed_player_position_seasons: season {year} — "
            f"MLB splits={total_splits}, rows={len(merged)}, "
            f"upsert_ok_batch={ok}, upsert_fail_batch={fail}",
            flush=True,
        )

        if idx < n_years - 1:
            time.sleep(_DELAY_SEC)

    print(
        f"seed_player_position_seasons: finished — seasons={seasons_run}, "
        f"rows upsert accepted={total_ok}, rows in failed batches={total_fail}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
