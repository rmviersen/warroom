"""
Backfill Statcast pitch-by-pitch data from Opening Day through yesterday (US Eastern).

Loads each calendar day via ``run_pipeline_for_date`` with a pause between days
to reduce Baseball Savant rate-limit risk.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

import config  # noqa: F401 — loads pipeline/.env before db access
from statcast_pipeline import run_pipeline_for_date

# Opening Day 2026 (MLB); adjust if league changes schedule.
SEASON_START = date(2026, 3, 20)
EASTERN = ZoneInfo("America/New_York")
DELAY_SECONDS = 3


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


def main() -> None:
    today_et = datetime.now(EASTERN).date()
    end_et = today_et - timedelta(days=1)

    dates = _daterange_inclusive(SEASON_START, end_et)
    total = len(dates)

    if total == 0:
        print(
            f"[backfill] No dates to process "
            f"(season start {SEASON_START.isoformat()}, "
            f"end {end_et.isoformat()} US/Eastern).",
        )
        return

    print(
        f"[backfill] Season window: {SEASON_START.isoformat()} .. "
        f"{end_et.isoformat()} (Eastern) — {total} day(s). "
        f"Delay between days: {DELAY_SECONDS}s.",
    )
    print("[backfill] Off days are not skipped; empty days are handled by the pipeline.\n")

    dates_with_data = 0
    dates_zero = 0
    errors: list[tuple[str, str]] = []
    iteration_seconds: list[float] = []

    for i, d in enumerate(dates):
        date_str = d.isoformat()
        days_left_inclusive = total - i

        avg_str = "—"
        eta_str = "—"
        if iteration_seconds:
            avg = mean(iteration_seconds)
            rem_pipelines = days_left_inclusive
            rem_sleeps = max(0, days_left_inclusive - 1)
            eta_sec = rem_pipelines * avg + rem_sleeps * DELAY_SECONDS
            avg_str = f"{avg:.1f}s"
            eta_str = _format_eta(eta_sec)

        print(
            f"[backfill] ({i + 1}/{total}) {date_str} — "
            f"{days_left_inclusive} day(s) left (incl. this one) — "
            f"avg pipeline time (so far): {avg_str} — "
            f"ETA remaining: {eta_str}",
        )

        t0 = time.perf_counter()
        try:
            n = run_pipeline_for_date(date_str)
            if n > 0:
                dates_with_data += 1
            else:
                dates_zero += 1
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            errors.append((date_str, msg))
            print(f"[backfill] ERROR {date_str}: {msg}")

        elapsed = time.perf_counter() - t0
        iteration_seconds.append(elapsed)

        if i < total - 1:
            time.sleep(DELAY_SECONDS)

    print("\n[backfill] ========== summary ==========")
    print(f"  Total dates processed:     {total}")
    print(f"  Dates with data (rows>0): {dates_with_data}")
    print(f"  Dates with 0 rows:       {dates_zero}")
    print(f"  Dates with errors:        {len(errors)}")
    if iteration_seconds:
        print(
            f"  Avg pipeline time/date:   {mean(iteration_seconds):.1f}s "
            f"(plus {DELAY_SECONDS}s sleep after each day except the last)",
        )
    if errors:
        print("  Errors:")
        for ds, msg in errors:
            print(f"    - {ds}: {msg}")
    print("[backfill] done.")


if __name__ == "__main__":
    main()
