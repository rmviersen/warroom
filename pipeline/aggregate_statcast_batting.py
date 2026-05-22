"""
Aggregate pitch-level ``statcast_pitches`` into ``statcast_batting`` via RPC
``upsert_statcast_batting_aggregates``.

NOTE: ``xba``, ``xslg``, ``xwoba``, ``sprint_speed``, ``player_name``, and
``team_id`` are **not** populated by this script. Those columns are owned by
``seed_statcast_batting.py`` (pybaseball leaderboards). ``cqi`` is **not** written
here; it is owned by ``calc_batting_metrics.py``. This script only writes: ``pa``,
``avg_exit_velocity``, ``max_exit_velocity``, ``avg_launch_angle``,
``barrel_rate``, ``hard_hit_rate`` (plus the RPC's ``updated_at``).
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime
from typing import Any

import pandas as pd

import config  # noqa: F401 — loads pipeline/.env before db access
from db import get_client

_DEFAULT_START_SEASON = 2015
# PostgREST default max is 1000 rows; explicit .limit() makes the page size intent clear.
_PAGE_SIZE = 1_000
_RPC_BATCH = 500

_EXCLUDED_BBE_EVENTS = frozenset(
    {
        "walk",
        "hit_by_pitch",
        "strikeout",
        "strikeout_double_play",
        "intent_walk",
    }
)

_STATCAST_SELECT = (
    "batter_id,game_pk,at_bat_number,events,launch_speed,launch_angle"
)


def is_barrel(launch_speed: float | None, launch_angle: float | None) -> bool:
    """
    Baseball Savant barrel envelope (matches their published barrel definition).

    Requires ``launch_speed >= 98`` mph. Returns ``False`` if ``launch_speed`` or
    ``launch_angle`` is missing or non-numeric.

    Between 98 and 116 mph: lower LA bound is ``26°`` at 98 mph, decreasing by ``1°``
    per mph to ``8°`` at 116 mph (not below ``8°``). Upper LA bound is ``30°`` at 98 mph,
    increasing by ``(20 / 18)°`` per mph to ``50°`` at 116 mph (not above ``50°``).

    At ``116`` mph and above: fixed launch-angle window ``8°`` to ``50°``.
    """
    if launch_speed is None or launch_angle is None:
        return False
    try:
        ev = float(launch_speed)
        angle = float(launch_angle)
    except (TypeError, ValueError):
        return False
    if ev < 98:
        return False
    if ev >= 116:
        return 8.0 <= angle <= 50.0
    lower = 26.0 - (ev - 98.0)
    upper = 30.0 + (ev - 98.0) * (20.0 / 18.0)
    return lower <= angle <= upper


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Aggregate Statcast pitches into statcast_batting using "
            "upsert_statcast_batting_aggregates."
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


def _load_season_pitches(client: Any, year: int) -> pd.DataFrame:
    """Paginated read of ``statcast_pitches`` for ``year`` (calendar bounds)."""
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        q = (
            client.table("statcast_pitches")
            .select(_STATCAST_SELECT)
            .gte("game_date", start)
            .lte("game_date", end)
            .range(offset, offset + _PAGE_SIZE - 1)
            .limit(_PAGE_SIZE)
        )
        res = q.execute()
        page = res.data or []
        if not page:
            break
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return pd.DataFrame(rows)


def _bbe_mask(df: pd.DataFrame) -> pd.Series:
    ev = df["events"]
    return (
        ev.notna()
        & (~ev.astype(str).isin(_EXCLUDED_BBE_EVENTS))
        & df["launch_speed"].notna()
    )


def _num_or_none(val: Any, *, ndigits: int | None = 4) -> float | None:
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except TypeError:
        pass
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    if ndigits is not None:
        return round(x, ndigits)
    return x


def aggregate_to_records(df: pd.DataFrame, season: int) -> list[dict[str, Any]]:
    """Build RPC payloads (``player_id`` = ``batter_id``)."""
    if df.empty:
        return []

    working = df[df["batter_id"].notna()].copy()
    working["batter_id"] = pd.to_numeric(working["batter_id"], errors="coerce")
    working = working[working["batter_id"].notna()]
    if working.empty:
        return []

    pa_series = (
        working[["batter_id", "game_pk", "at_bat_number"]]
        .drop_duplicates()
        .groupby("batter_id", sort=True)
        .size()
        .astype("int64")
    )

    bbe_full = working[_bbe_mask(working)].copy()
    if not bbe_full.empty:
        evs = bbe_full["launch_speed"].to_numpy()
        las = bbe_full["launch_angle"].to_numpy()
        flags = [
            is_barrel(
                None if pd.isna(ev) else float(ev),
                None if pd.isna(la) else float(la),
            )
            for ev, la in zip(evs, las)
        ]
        bbe_full["_barrel"] = flags

    bbe_counts = (
        bbe_full.groupby("batter_id").size() if not bbe_full.empty else pd.Series(dtype=int)
    )
    barrels = (
        bbe_full.groupby("batter_id")["_barrel"].sum()
        if not bbe_full.empty
        else pd.Series(dtype=float)
    )
    hard95 = (
        bbe_full.assign(_hh=bbe_full["launch_speed"] >= 95)
        .groupby("batter_id")["_hh"]
        .sum()
        .astype("int64")
        if not bbe_full.empty
        else pd.Series(dtype="int64")
    )
    avg_ev_s = (
        bbe_full.groupby("batter_id")["launch_speed"].mean()
        if not bbe_full.empty
        else pd.Series(dtype=float)
    )
    max_ev_s = (
        bbe_full.groupby("batter_id")["launch_speed"].max()
        if not bbe_full.empty
        else pd.Series(dtype=float)
    )
    avg_la_s = (
        bbe_full.groupby("batter_id")["launch_angle"].mean()
        if not bbe_full.empty
        else pd.Series(dtype=float)
    )

    records: list[dict[str, Any]] = []
    for batter_id, pa in pa_series.items():
        pid = int(batter_id)
        pa_i = int(pa)
        if pa_i <= 0:
            continue

        bbe_n = int(bbe_counts[batter_id]) if batter_id in bbe_counts.index else 0
        if bbe_n <= 0:
            avg_exit_velocity = None
            max_exit_velocity = None
            avg_launch_angle = None
            barrel_rate = None
            hard_hit_rate = None
        else:
            avg_exit_velocity = _num_or_none(avg_ev_s.get(batter_id))
            max_exit_velocity = _num_or_none(max_ev_s.get(batter_id))
            avg_launch_angle = _num_or_none(avg_la_s.get(batter_id))
            br_ct = int(barrels[batter_id]) if batter_id in barrels.index else 0
            hh_ct = int(hard95[batter_id]) if batter_id in hard95.index else 0
            barrel_rate = round(100.0 * br_ct / bbe_n, 4)
            hard_hit_rate = round(100.0 * hh_ct / bbe_n, 4)

        records.append(
            {
                "player_id": pid,
                "season": season,
                "pa": pa_i,
                "avg_exit_velocity": avg_exit_velocity,
                "max_exit_velocity": max_exit_velocity,
                "avg_launch_angle": avg_launch_angle,
                "barrel_rate": barrel_rate,
                "hard_hit_rate": hard_hit_rate,
            }
        )

    return records


def _upsert_batches(
    client: Any, rows: list[dict[str, Any]]
) -> tuple[int, int, int]:
    """Returns ``(ok_rows, failed_rows, failed_batches)``."""
    ok = 0
    failed_rows = 0
    failed_batches = 0
    n_batches = (len(rows) + _RPC_BATCH - 1) // _RPC_BATCH if rows else 0
    for i in range(0, len(rows), _RPC_BATCH):
        batch = rows[i : i + _RPC_BATCH]
        batch_no = i // _RPC_BATCH + 1
        try:
            client.rpc(
                "upsert_statcast_batting_aggregates",
                {"rows": batch},
            ).execute()
            ok += len(batch)
            print(
                f"aggregate_statcast_batting: batch {batch_no}/{n_batches}: "
                f"success {len(batch)} row(s)",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            failed_rows += len(batch)
            failed_batches += 1
            print(
                f"aggregate_statcast_batting: batch {batch_no}/{n_batches}: "
                f"failure {len(batch)} row(s) — {exc}",
                flush=True,
            )
    return ok, failed_rows, failed_batches


def run_season(client: Any, year: int) -> tuple[int, int, int, int, int]:
    """
    Load ``year``, aggregate, upsert.

    Returns ``(batters, total_pa, ok_rows, failed_rows, failed_batches)``.
    """
    print(
        f"aggregate_statcast_batting: loading statcast_pitches for {year}…",
        flush=True,
    )
    df = _load_season_pitches(client, year)
    print(
        f"aggregate_statcast_batting: {len(df)} pitch row(s) loaded; aggregating…",
        flush=True,
    )
    records = aggregate_to_records(df, year)
    batters = len(records)
    total_pa = sum(int(r["pa"]) for r in records) if records else 0

    ok, failed_rows, failed_batches = _upsert_batches(client, records)
    return batters, total_pa, ok, failed_rows, failed_batches


def main() -> None:
    args = _parse_args()
    start_s = int(args.start_season)
    end_s = int(args.end_season)
    if start_s > end_s:
        raise SystemExit(
            "[aggregate_statcast_batting] --start-season must be <= --end-season."
        )

    client = get_client()
    total_batters = 0
    total_fail_rows = 0

    for year in range(start_s, end_s + 1):
        batters, total_pa, ok, fail_r, fail_b = run_season(client, year)
        total_batters += batters
        total_fail_rows += fail_r
        print(
            f"aggregate_statcast_batting: season {year} summary — "
            f"batters={batters}, total_pa={total_pa}, ok_rows={ok}, "
            f"failed_rows={fail_r}, failed_batches={fail_b}",
            flush=True,
        )

    print(
        f"aggregate_statcast_batting: final summary — "
        f"total_batters_processed={total_batters}, total_failed_rows={total_fail_rows}",
        flush=True,
    )


if __name__ == "__main__":
    main()
