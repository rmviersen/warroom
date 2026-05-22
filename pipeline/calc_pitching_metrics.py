"""
Recompute Stuff+ metrics on pitching warehouse tables using stored aggregates —
**never** reads ``statcast_pitches``.

Writes ``stuff_plus_pitch`` via ``upsert_statcast_pitching_arsenal`` and pitcher-level
``stuff_plus`` via ``upsert_statcast_pitching_aggregates``.

Apply migration ``supabase/migrations/20260522110000_partial_upsert_statcast_pitching_rpc.sql``
so payloads with only Stuff+ fields plus keys do not null out other columns.

DB column names ``avg_h_movement`` / ``avg_v_movement`` / ``pitches`` correspond to Savant-style
movement and pitch totals (often labeled horz./vert. break / pitch_count in spreadsheets).
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime
from typing import Any

import config  # noqa: F401 — loads pipeline/.env before db access
from calculations.pitching_calcs import calc_stuff_plus
from db import get_client

_DEFAULT_START_SEASON = 2015
_PAGE_SIZE = 1_000
_RPC_BATCH = 500

_ALLOWED_P_THROWS: frozenset[str] = frozenset({"L", "R"})

STUFF_PLUS_ELIGIBLE: frozenset[str] = frozenset(
    {
        "FF",
        "SI",
        "FC",
        "FA",
        "SL",
        "ST",
        "SV",
        "CU",
        "KC",
        "CS",
        "CH",
        "FS",
        "FO",
        "KN",
    }
)

PITCH_TYPE_TO_CATEGORY: dict[str, str] = {
    "FF": "Fastball",
    "SI": "Fastball",
    "FC": "Fastball",
    "FA": "Fastball",
    "SL": "Breaking",
    "ST": "Breaking",
    "SV": "Breaking",
    "CU": "Breaking",
    "KC": "Breaking",
    "CS": "Breaking",
    "CH": "Offspeed",
    "FS": "Offspeed",
    "FO": "Offspeed",
    "KN": "Knuckleball",
    "EP": "Other",
    "SC": "Other",
    "FT": "Other",
}

_ARSENAL_SELECT = (
    "pitcher_id,season,pitch_type,p_throws,"
    "avg_velo,avg_spin_rate,avg_h_movement,avg_v_movement,pitches"
)


def _normalize_p_throws(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip().upper()
    return s if s in _ALLOWED_P_THROWS else None


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Recompute Stuff+ on statcast_pitching_arsenal and weighted "
            "statcast_pitching.stuff_plus from league_pitch_type_averages."
        ),
    )
    p.add_argument(
        "--start-season",
        type=int,
        default=_DEFAULT_START_SEASON,
        help=f"First season (default {_DEFAULT_START_SEASON}).",
    )
    p.add_argument(
        "--end-season",
        type=int,
        default=datetime.now().year,
        help="Last season (default: current calendar year).",
    )
    return p.parse_args()


def _to_float_optional(val: Any) -> float | None:
    if val is None:
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(x):
        return None
    return x


def _to_int_optional(val: Any) -> int | None:
    if val is None:
        return None
    try:
        i = int(val)
    except (TypeError, ValueError):
        return None
    return i


def _load_league_baselines(client: Any, season: int) -> dict[str, dict[str, dict[str, Any]]]:
    """
    ``[pitch_type][p_throws]`` → avg_velo, avg_spin_rate, avg_h_movement, avg_v_movement.
    """

    out: dict[str, dict[str, dict[str, Any]]] = {}
    offset = 0
    rows_read = 0
    while True:
        try:
            res = (
                client.table("league_pitch_type_averages")
                .select(
                    "season,pitch_type,p_throws,avg_velo,avg_spin_rate,"
                    "avg_h_movement,avg_v_movement"
                )
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_pitching_metrics: league_pitch_type_averages page offset={offset} "
                f"season={season} failed: {exc}",
                flush=True,
            )
            break
        page = res.data or []
        for row in page:
            rows_read += 1
            pt = str(row.get("pitch_type") or "").strip()
            ph = _normalize_p_throws(row.get("p_throws"))
            if not pt or ph is None:
                continue
            out.setdefault(pt, {})[ph] = {
                "avg_velo": _to_float_optional(row.get("avg_velo")),
                "avg_spin_rate": _to_float_optional(row.get("avg_spin_rate")),
                "avg_h_movement": _to_float_optional(row.get("avg_h_movement")),
                "avg_v_movement": _to_float_optional(row.get("avg_v_movement")),
            }
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    print(
        f"calc_pitching_metrics: loaded {rows_read} league_pitch_type_average row(s) "
        f"for season {season} ({len(out)} pitch type key(s))",
        flush=True,
    )
    return out


def _load_statcast_pitching_arsenal_season(
    client: Any, season: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        q = (
            client.table("statcast_pitching_arsenal")
            .select(_ARSENAL_SELECT)
            .eq("season", season)
            .order("pitcher_id")
            .range(offset, offset + _PAGE_SIZE - 1)
            .limit(_PAGE_SIZE)
        )
        try:
            res = q.execute()
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_pitching_metrics: statcast_pitching_arsenal page offset={offset} "
                f"season={season} failed: {exc}",
                flush=True,
            )
            break
        page = res.data or []
        if not page:
            break
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


def _weighted_mean(
    pairs: list[tuple[float | None, int]],
) -> float | None:
    num = 0.0
    den = 0.0
    for val, w in pairs:
        if val is None or w <= 0:
            continue
        num += float(val) * float(w)
        den += float(w)
    if den == 0:
        return None
    return round(num / den, 4)


def _build_payloads_and_rollup(
    loaded: list[dict[str, Any]],
    season: int,
    baselines: dict[str, dict[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    arsenal_payloads: list[dict[str, Any]] = []
    skipped = 0
    rollup_bins: dict[int, list[tuple[float | None, int]]] = {}

    for row in loaded:
        pid = row.get("pitcher_id")
        pt = row.get("pitch_type")
        if pid is None or pt is None:
            skipped += 1
            continue
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            skipped += 1
            continue
        ptype_s = str(pt).strip()
        pthr_raw = row.get("p_throws")
        pthr = _normalize_p_throws(pthr_raw)

        pitches_i = _to_int_optional(row.get("pitches"))
        if pitches_i is None or pitches_i <= 0:
            skipped += 1
            continue

        if pthr is None:
            skipped += 1
            continue

        bl_pt = baselines.get(ptype_s)
        if not bl_pt:
            skipped += 1
            continue
        bl = bl_pt.get(pthr)
        if not bl:
            skipped += 1
            continue

        av = _to_float_optional(row.get("avg_velo"))
        sp = _to_float_optional(row.get("avg_spin_rate"))
        hx = _to_float_optional(row.get("avg_h_movement"))
        vz = _to_float_optional(row.get("avg_v_movement"))

        stuff_p = calc_stuff_plus(
            av,
            sp,
            hx,
            vz,
            bl.get("avg_velo"),
            bl.get("avg_spin_rate"),
            bl.get("avg_h_movement"),
            bl.get("avg_v_movement"),
        )
        if stuff_p is None:
            skipped += 1
            continue

        stuff_rounded = round(float(stuff_p), 4)

        arsenal_payloads.append(
            {
                "pitcher_id": pid_i,
                "season": int(season),
                "pitch_type": ptype_s,
                "pitch_category": PITCH_TYPE_TO_CATEGORY.get(ptype_s, "Other"),
                "p_throws": pthr,
                "stuff_plus_pitch": stuff_rounded,
            }
        )

        if ptype_s in STUFF_PLUS_ELIGIBLE:
            rollup_bins.setdefault(pid_i, []).append((stuff_rounded, pitches_i))

    rollup_payloads = []
    for rid, pairs in rollup_bins.items():
        wmean = _weighted_mean(pairs)
        if wmean is None:
            continue
        rollup_payloads.append(
            {
                "pitcher_id": rid,
                "season": int(season),
                "stuff_plus": wmean,
            }
        )

    return arsenal_payloads, rollup_payloads, skipped


def _upsert_batches(
    client: Any, rpc_name: str, rows: list[dict[str, Any]]
) -> tuple[int, int]:
    ok = 0
    failed_rows = 0
    n_batches = (len(rows) + _RPC_BATCH - 1) // _RPC_BATCH if rows else 0

    for i in range(0, len(rows), _RPC_BATCH):
        batch = rows[i : i + _RPC_BATCH]
        batch_no = i // _RPC_BATCH + 1
        try:
            client.rpc(rpc_name, {"rows": batch}).execute()
            ok += len(batch)
            print(
                f"calc_pitching_metrics: {rpc_name} batch {batch_no}/{n_batches}: "
                f"success {len(batch)} row(s)",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            failed_rows += len(batch)
            print(
                f"calc_pitching_metrics: {rpc_name} batch {batch_no}/{n_batches}: "
                f"failure {len(batch)} row(s) — {exc}",
                flush=True,
            )

    return ok, failed_rows


def run_season(
    client: Any, season: int
) -> tuple[int, int, int, int, int]:
    """
    ``(arsenal_read, arsenal_ok, rollup_ok, total_fail_rows, skipped_build)``.
    """

    baselines = _load_league_baselines(client, season)

    arsenal_rows = _load_statcast_pitching_arsenal_season(client, season)
    arsenal_read = len(arsenal_rows)

    arsenal_payloads, rollup_payloads, skipped = _build_payloads_and_rollup(
        arsenal_rows, season, baselines
    )

    a_ok, a_fail = _upsert_batches(client, "upsert_statcast_pitching_arsenal", arsenal_payloads)
    r_ok, r_fail = _upsert_batches(client, "upsert_statcast_pitching_aggregates", rollup_payloads)

    total_fail = a_fail + r_fail
    return arsenal_read, a_ok, r_ok, total_fail, skipped


def main() -> None:
    args = _parse_args()
    start_s = int(args.start_season)
    end_s = int(args.end_season)
    if start_s > end_s:
        raise SystemExit(
            "[calc_pitching_metrics] --start-season must be <= --end-season."
        )

    client = get_client()
    grand_a_ok = 0
    grand_r_ok = 0
    grand_fail = 0

    for season in range(start_s, end_s + 1):
        print(
            f"calc_pitching_metrics: processing season {season}…",
            flush=True,
        )
        arsenal_read, a_ok, r_ok, fail_rows, skipped = run_season(client, season)
        grand_a_ok += a_ok
        grand_r_ok += r_ok
        grand_fail += fail_rows

        print(
            f"calc_pitching_metrics: season {season} summary — "
            f"arsenal_rows_read={arsenal_read}, arsenal_rows_updated={a_ok}, "
            f"rollup_rows_written={r_ok}, rows_skipped_no_stuff={skipped}, "
            f"fail_rows_total={fail_rows}",
            flush=True,
        )

    print(
        f"calc_pitching_metrics: final summary — "
        f"total_arsenal_rows_updated={grand_a_ok}, "
        f"total_rollup_rows_written={grand_r_ok}, "
        f"total_failures={grand_fail}",
        flush=True,
    )


if __name__ == "__main__":
    main()
