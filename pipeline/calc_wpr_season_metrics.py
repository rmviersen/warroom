"""
Compute total WPR (Wins above Replacement, WARroom) per player batting season.

Total WPR is the sum of the three position-player components:

    wpr = bwpr + fwpr + brwpr

All three components use the same RPW formula (``9 × (lgR/lgIP) × 1.5 + 3``),
so they add directly.  ``None`` components are treated as 0 — a player with
sprint-speed data but no OAA fielding data still gets a valid total.

Rows where ALL three components are ``None`` are skipped (league data not yet
available for that season).

Two-way players (e.g. Ohtani): ``wpr`` here covers only their batting/fielding/
baserunning value from ``player_batting_seasons``.  Their pitching value
(``pwpr``) lives on ``player_pitching_seasons`` and is displayed separately.

Writes ``wpr`` via ``upsert_player_batting_seasons`` (partial upsert — never
overwrites ``bwpr``, ``fwpr``, ``brwpr``, or counting stats).

Usage::

    python calc_wpr_season_metrics.py --start-season 1990 --end-season 2026
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

import config  # noqa: F401 — load pipeline/.env
from db import get_client

_PAGE_SIZE = 1000
_RPC_BATCH = 500


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.strip())
    p.add_argument(
        "--start-season", type=int, default=datetime.now().year,
        help="First season inclusive (default: current year).",
    )
    p.add_argument(
        "--end-season", type=int, default=datetime.now().year,
        help="Last season inclusive (default: current year).",
    )
    return p.parse_args()


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _to_int(val: Any) -> int | None:
    f = _to_float(val)
    return None if f is None else int(f)


def flush_wpr(client: Any, payloads: list[dict[str, Any]]) -> tuple[int, int]:
    ok = failed = 0
    n_batches = (len(payloads) + _RPC_BATCH - 1) // _RPC_BATCH if payloads else 0
    for i in range(0, len(payloads), _RPC_BATCH):
        batch = payloads[i : i + _RPC_BATCH]
        batch_idx = i // _RPC_BATCH + 1
        try:
            client.rpc("upsert_player_batting_seasons", {"rows": batch}).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            failed += len(batch)
            print(
                f"calc_wpr_season_metrics: RPC batch {batch_idx}/{n_batches} "
                f"failed ({len(batch)} rows) — {exc}",
                flush=True,
            )
    return ok, failed


def run_season(client: Any, season: int) -> dict[str, int]:
    stats: dict[str, int] = defaultdict(int)
    payloads: list[dict[str, Any]] = []
    offset = 0

    while True:
        try:
            resp = (
                client.table("player_batting_seasons")
                .select("player_id,season,team_id,bwpr,fwpr,brwpr")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_wpr_season_metrics: player_batting_seasons read "
                f"season={season} offset={offset} failed: {exc}",
                flush=True,
            )
            break

        page = resp.data or []
        if not page:
            break

        stats["batting_rows"] += len(page)

        for row in page:
            pid = _to_int(row.get("player_id"))
            tid = _to_int(row.get("team_id"))
            if pid is None or tid is None:
                continue

            bwpr  = _to_float(row.get("bwpr"))
            fwpr  = _to_float(row.get("fwpr"))
            brwpr = _to_float(row.get("brwpr"))

            # Skip rows where no component has been calculated yet
            if bwpr is None and fwpr is None and brwpr is None:
                stats["skipped_no_components"] += 1
                continue

            wpr = round(
                (bwpr  or 0.0) +
                (fwpr  or 0.0) +
                (brwpr or 0.0),
                1,
            )
            stats["rows_computed"] += 1

            # Track partial vs full coverage for diagnostics
            n_components = sum(x is not None for x in [bwpr, fwpr, brwpr])
            if n_components < 3:
                stats["partial_components"] += 1

            payloads.append({
                "player_id": pid,
                "season":    season,
                "team_id":   tid,
                "wpr":       wpr,
            })

        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    ok, fail = flush_wpr(client, payloads)
    stats["rows_written"] = ok
    stats["rows_failed"]  = fail

    print(
        f"calc_wpr_season_metrics: season={season} "
        f"batting_rows={stats['batting_rows']} "
        f"rows_computed={stats['rows_computed']} "
        f"partial_components={stats['partial_components']} "
        f"skipped={stats['skipped_no_components']} "
        f"rows_written={ok} rows_failed={fail}",
        flush=True,
    )
    return dict(stats)


def main() -> None:
    args = _parse_args()
    start, end = args.start_season, args.end_season
    if start > end:
        raise SystemExit(
            f"calc_wpr_season_metrics: --start-season ({start}) "
            f"must be <= --end-season ({end})."
        )

    client = get_client()
    total_written = total_failed = 0

    for season in range(start, end + 1):
        s = run_season(client, season)
        total_written += s.get("rows_written", 0)
        total_failed  += s.get("rows_failed", 0)

    print(
        f"calc_wpr_season_metrics: done — "
        f"total_rows_written={total_written} total_failures={total_failed}",
        flush=True,
    )


if __name__ == "__main__":
    main()
