"""
Backfill ``statcast_pitches`` for historical seasons (2015–2025 by default).

Iterates day-by-day within each season's regular-season window and calls
``run_pipeline_for_date`` from ``statcast_pipeline``. Dates that already have at
least one row in ``statcast_pitches`` for that ``game_date`` are skipped so the
job is resumable after interruption.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean
from typing import Any

import config  # noqa: F401 — loads pipeline/.env before db access
from db import get_client
from statcast_pipeline import run_pipeline_for_date

# Approximate MLB regular season windows (inclusive).
SEASON_WINDOWS: dict[int, tuple[date, date]] = {
    2015: (date(2015, 4, 5), date(2015, 10, 4)),
    2016: (date(2016, 4, 3), date(2016, 10, 2)),
    2017: (date(2017, 4, 2), date(2017, 10, 1)),
    2018: (date(2018, 3, 29), date(2018, 10, 1)),
    2019: (date(2019, 3, 28), date(2019, 9, 29)),
    2020: (date(2020, 7, 23), date(2020, 9, 27)),
    2021: (date(2021, 4, 1), date(2021, 10, 3)),
    2022: (date(2022, 4, 7), date(2022, 10, 5)),
    2023: (date(2023, 3, 30), date(2023, 10, 1)),
    2024: (date(2024, 3, 20), date(2024, 9, 29)),
    2025: (date(2025, 3, 27), date(2025, 9, 28)),
}

DEFAULT_START_SEASON = 2015
DEFAULT_END_SEASON = 2025
DEFAULT_DELAY_SECONDS = 8.0


def _daterange_inclusive(start: date, end: date) -> list[date]:
    if start > end:
        return []
    days: list[date] = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _format_eta(seconds: float) -> str:
    if seconds <= 0 or not (seconds < float("inf")):
        return "—"
    sec = int(round(seconds))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


_DISTINCT_SCAN_PAGE_SIZE = 1000


def _cell_to_game_date(val: Any) -> date | None:
    """Parse ``game_date`` from a PostgREST row (ISO date string or date-like)."""

    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return date.fromisoformat(s[:10])


def load_existing_game_dates(client: Any, candidates: list[date]) -> set[date]:
    """Candidate dates that already have at least one row in ``statcast_pitches``.

    One paginated scan of ``game_date`` between min/max candidate (inclusive); builds
    a distinct-date set, then intersects with ``candidates`` in Python.
    """

    if not candidates:
        return set()

    cand_set = set(candidates)
    dmin = min(cand_set)
    dmax = max(cand_set)

    print(
        f"[backfill_hist] paginated scan: statcast_pitches.game_date "
        f"between {dmin.isoformat()} and {dmax.isoformat()} …",
        flush=True,
    )

    distinct_in_db: set[date] = set()
    offset = 0
    total_rows = 0

    while True:
        resp = (
            client.table("statcast_pitches")
            .select("game_date")
            .gte("game_date", dmin.isoformat())
            .lte("game_date", dmax.isoformat())
            .order("game_date")
            .range(offset, offset + _DISTINCT_SCAN_PAGE_SIZE - 1)
            .execute()
        )
        rows = resp.data or []
        for row in rows:
            gd = _cell_to_game_date(row.get("game_date"))
            if gd is not None:
                distinct_in_db.add(gd)

        n = len(rows)
        total_rows += n
        page_num = offset // _DISTINCT_SCAN_PAGE_SIZE
        if page_num == 0 or page_num % 10 == 0:
            print(
                f"[backfill_hist] … page chunk starting offset {offset}: "
                f"{n} row(s) this page, {total_rows} total rows read, "
                f"{len(distinct_in_db)} distinct date(s) so far",
                flush=True,
            )

        if n < _DISTINCT_SCAN_PAGE_SIZE:
            break
        offset += _DISTINCT_SCAN_PAGE_SIZE

    have = cand_set & distinct_in_db
    print(
        f"[backfill_hist] scan finished: {total_rows} row(s) read, "
        f"{len(distinct_in_db)} distinct game_date in window, "
        f"{len(have)} of {len(cand_set)} candidate day(s) already in DB.",
        flush=True,
    )
    return have


@dataclass
class SeasonRunStats:
    skipped_at_start: int = 0
    processed: int = 0
    dates_with_data: int = 0
    dates_zero: int = 0
    errors: int = 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill statcast_pitches for historical seasons (day by day).",
    )
    p.add_argument(
        "--start-season",
        type=int,
        default=DEFAULT_START_SEASON,
        help=f"First season (default {DEFAULT_START_SEASON}).",
    )
    p.add_argument(
        "--end-season",
        type=int,
        default=DEFAULT_END_SEASON,
        help=f"Last season (default {DEFAULT_END_SEASON}).",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=(
            "Seconds to sleep after each day that runs the pipeline "
            f"(default {DEFAULT_DELAY_SECONDS})."
        ),
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    start_s = args.start_season
    end_s = args.end_season
    delay = float(args.delay)

    if start_s > end_s:
        raise SystemExit("[backfill_hist] --start-season must be <= --end-season.")
    for y in range(start_s, end_s + 1):
        if y not in SEASON_WINDOWS:
            raise SystemExit(
                f"[backfill_hist] No season window defined for {y}. "
                f"Supported: {min(SEASON_WINDOWS)}..{max(SEASON_WINDOWS)}.",
            )

    client = get_client()

    plan: list[tuple[int, date]] = []
    for season in range(start_s, end_s + 1):
        lo, hi = SEASON_WINDOWS[season]
        for d in _daterange_inclusive(lo, hi):
            plan.append((season, d))

    candidate_dates = [d for _, d in plan]
    existing_snapshot = load_existing_game_dates(client, candidate_dates)

    queue: list[tuple[int, date]] = [
        (s, d) for s, d in plan if d not in existing_snapshot
    ]
    pending: set[date] = {d for _, d in queue}

    season_stats: dict[int, SeasonRunStats] = {
        y: SeasonRunStats() for y in range(start_s, end_s + 1)
    }
    for season in range(start_s, end_s + 1):
        lo, hi = SEASON_WINDOWS[season]
        season_stats[season].skipped_at_start = sum(
            1 for d in _daterange_inclusive(lo, hi) if d in existing_snapshot
        )

    print(
        f"[backfill_hist] Seasons {start_s}..{end_s}; {len(plan)} calendar day(s) in windows; "
        f"{len(queue)} need pipeline run; {len(existing_snapshot)} skip (already in DB). "
        f"Delay after each pipeline day (except last): {delay}s.\n",
        flush=True,
    )

    if not queue:
        print("[backfill_hist] nothing to run — every date in range is already in the database.", flush=True)
        for season in range(start_s, end_s + 1):
            st = season_stats[season]
            print(
                f"[backfill_hist] --- Season {season} summary: "
                f"skipped_at_start={st.skipped_at_start}, "
                f"processed_this_run=0, "
                f"dates_with_data=0, "
                f"dates_zero_rows=0, "
                f"errors=0",
                flush=True,
            )
        print("\n[backfill_hist] ========== FINAL SUMMARY ==========", flush=True)
        print(f"  Total calendar days in windows: {len(plan)}", flush=True)
        print(
            f"  Dates skipped at startup (already in DB): {len(existing_snapshot)}",
            flush=True,
        )
        print("  Total errors: 0", flush=True)
        print("[backfill_hist] done.", flush=True)
        return

    all_errors: list[tuple[int, str, str]] = []
    pipeline_times: list[float] = []

    for idx, (season, d) in enumerate(queue):
        date_str = d.isoformat()
        rem = len(pending)
        avg_s = mean(pipeline_times) if pipeline_times else None
        avg_str = f"{avg_s:.1f}s" if avg_s is not None else "—"
        eta_str = "—"
        if avg_s is not None and rem >= 1:
            eta_sec = rem * avg_s + max(0, rem - 1) * delay
            eta_str = _format_eta(eta_sec)

        print(
            f"[backfill_hist] ({idx + 1}/{len(queue)}) {season} {date_str} — "
            f"{rem} day(s) left in queue — "
            f"avg pipeline (global): {avg_str} — ETA (rough): {eta_str}",
            flush=True,
        )

        t0 = time.perf_counter()
        ran_ok = False
        try:
            n = run_pipeline_for_date(date_str)
            ran_ok = True
            if n > 0:
                season_stats[season].dates_with_data += 1
            else:
                season_stats[season].dates_zero += 1
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            all_errors.append((season, date_str, msg))
            season_stats[season].errors += 1
            print(f"[backfill_hist] ERROR {season} {date_str}: {msg}", flush=True)
        finally:
            pipeline_times.append(time.perf_counter() - t0)

        if ran_ok:
            pending.discard(d)
            season_stats[season].processed += 1

        if idx < len(queue) - 1:
            time.sleep(delay)

    for season in range(start_s, end_s + 1):
        st = season_stats[season]
        print(
            f"[backfill_hist] --- Season {season} summary: "
            f"skipped_at_start={st.skipped_at_start}, "
            f"processed_this_run={st.processed}, "
            f"dates_with_data={st.dates_with_data}, "
            f"dates_zero_rows={st.dates_zero}, "
            f"errors={st.errors}",
            flush=True,
        )

    print("\n[backfill_hist] ========== FINAL SUMMARY ==========", flush=True)
    print(f"  Total calendar days in windows: {len(plan)}", flush=True)
    print(
        f"  Dates skipped at startup (already in DB): {len(existing_snapshot)}",
        flush=True,
    )
    print(f"  Days in pipeline queue this run: {len(queue)}", flush=True)
    if pipeline_times:
        print(
            f"  Avg time per queue step (pipeline + overhead): {mean(pipeline_times):.1f}s "
            f"(plus up to ~{delay}s delay after each step except the last)",
            flush=True,
        )
    print(f"  Total errors: {len(all_errors)}", flush=True)
    if all_errors:
        print("  All errors:", flush=True)
        for sea, ds, msg in all_errors:
            print(f"    - season {sea} {ds}: {msg}", flush=True)
    print("[backfill_hist] done.", flush=True)


if __name__ == "__main__":
    main()
