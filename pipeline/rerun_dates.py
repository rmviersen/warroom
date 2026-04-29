"""
Re-run ``statcast_pipeline.run_pipeline_for_date`` for a fixed list of dates.

Uses ``config`` for env / Supabase (via ``statcast_pipeline`` → ``db``).
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import config  # noqa: F401 — load .env before db access
from statcast_pipeline import run_pipeline_for_date

# Inclusive calendar range to re-pull from Baseball Savant.
START = date(2026, 3, 20)
END = date(2026, 4, 10)
DELAY_SEC = 10


def daterange_inclusive(start: date, end: date) -> list[date]:
    if start > end:
        return []
    out: list[date] = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def main() -> None:
    dates = daterange_inclusive(START, END)
    total = len(dates)
    if total == 0:
        print("[rerun_dates] No dates in range.")
        return

    print(
        f"[rerun_dates] {START.isoformat()} .. {END.isoformat()} - "
        f"{total} day(s), {DELAY_SEC}s delay between days.\n",
        flush=True,
    )

    total_rows = 0
    errors: list[tuple[str, str]] = []

    for i, d in enumerate(dates):
        date_str = d.isoformat()
        remaining_after = total - i - 1
        print(
            f"[rerun_dates] ({i + 1}/{total}) {date_str} - "
            f"{remaining_after} date(s) left after this",
            flush=True,
        )
        try:
            n = run_pipeline_for_date(date_str)
            total_rows += n
            print(
                f"[rerun_dates]   -> cleaned rows (upsert batch): {n}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            errors.append((date_str, msg))
            print(f"[rerun_dates]   -> ERROR: {msg}", flush=True)

        if i < total - 1:
            time.sleep(DELAY_SEC)

    print("\n[rerun_dates] ========== summary ==========", flush=True)
    print(f"  Dates processed:      {total}", flush=True)
    print(f"  Total cleaned rows: {total_rows}", flush=True)
    print(f"  Dates with errors:  {len(errors)}", flush=True)
    if errors:
        for ds, msg in errors:
            print(f"    - {ds}: {msg}", flush=True)
    print("[rerun_dates] done.", flush=True)


if __name__ == "__main__":
    main()
