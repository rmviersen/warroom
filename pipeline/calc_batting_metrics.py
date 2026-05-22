"""
Recompute Contact Quality Index (``cqi``) on ``statcast_batting`` from stored
Savant aggregates (avg exit velo, barrel rate, hard-hit rate). Reads only
pre-aggregated table rows --- **never** scans ``statcast_pitches``.

Apply Supabase migration ``20260522100000_partial_upsert_statcast_batting_aggregates.sql``
(or equivalent RPC) so payloads that contain only ``player_id``, ``season``, and
``cqi`` do not null out existing stat columns via ``upsert_statcast_batting_aggregates``.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

import config  # noqa: F401 — loads pipeline/.env before db access
from calculations.batting_calcs import calc_cqi
from db import get_client

_DEFAULT_START_SEASON = 2015
_PAGE_SIZE = 1_000
_RPC_BATCH = 500

_STATCAST_SELECT = (
    "player_id,season,avg_exit_velocity,barrel_rate,hard_hit_rate"
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Recompute CQI on statcast_batting from stored contact-quality "
            "components (via calc_cqi)."
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
    if x != x:  # NaN
        return None
    return x


def _load_statcast_batting_season(client: Any, season: int) -> list[dict[str, Any]]:
    """Paginated read of ``statcast_batting`` for ``season``."""

    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        q = (
            client.table("statcast_batting")
            .select(_STATCAST_SELECT)
            .eq("season", season)
            .order("player_id")
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
    return rows


def _records_for_cqi_upserts(
    loaded: list[dict[str, Any]], season: int
) -> tuple[list[dict[str, Any]], int]:
    """Build minimal RPC payloads; ``skipped`` counts rows with no usable CQI."""

    payloads: list[dict[str, Any]] = []
    skipped = 0

    for row in loaded:
        pid = row.get("player_id")
        if pid is None:
            skipped += 1
            continue
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            skipped += 1
            continue

        avg_ev = _to_float_optional(row.get("avg_exit_velocity"))
        brate = _to_float_optional(row.get("barrel_rate"))
        hh = _to_float_optional(row.get("hard_hit_rate"))

        cqi_val = calc_cqi(avg_ev, brate, hh, int(season))
        if cqi_val is None:
            skipped += 1
            continue

        payloads.append(
            {
                "player_id": pid_i,
                "season": int(season),
                "cqi": round(cqi_val, 2),
            }
        )

    return payloads, skipped


def _upsert_batches(client: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Returns ``(ok_rows, failed_rows)``."""

    ok = 0
    failed_rows = 0
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
                f"calc_batting_metrics: batch {batch_no}/{n_batches}: "
                f"success {len(batch)} row(s)",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            failed_rows += len(batch)
            print(
                f"calc_batting_metrics: batch {batch_no}/{n_batches}: "
                f"failure {len(batch)} row(s) — {exc}",
                flush=True,
            )

    return ok, failed_rows


def run_season(client: Any, season: int) -> tuple[int, int, int, int]:
    """
    Returns ``(rows_read, rows_written, skipped, failed_rows)``.
    """

    print(
        f"calc_batting_metrics: loading statcast_batting for season {season}…",
        flush=True,
    )
    loaded = _load_statcast_batting_season(client, season)
    rows_read = len(loaded)
    payloads, skipped = _records_for_cqi_upserts(loaded, season)

    ok, failed = _upsert_batches(client, payloads)
    rows_written = ok

    return rows_read, rows_written, skipped, failed


def main() -> None:
    args = _parse_args()
    start_s = int(args.start_season)
    end_s = int(args.end_season)

    if start_s > end_s:
        raise SystemExit(
            "[calc_batting_metrics] --start-season must be <= --end-season."
        )

    client = get_client()
    grand_ok = 0
    grand_fail = 0

    for season in range(start_s, end_s + 1):
        rows_read, rows_written, skipped, failed = run_season(client, season)
        grand_ok += rows_written
        grand_fail += failed

        print(
            f"calc_batting_metrics: season {season} summary — "
            f"rows_read={rows_read}, rows_written={rows_written}, "
            f"skipped_calc={skipped}, failed_rows_batch={failed}",
            flush=True,
        )

    print(
        f"calc_batting_metrics: final summary — "
        f"total_rows_updated={grand_ok}, total_failures={grand_fail}",
        flush=True,
    )


if __name__ == "__main__":
    main()
