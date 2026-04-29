"""
Repair FK gaps: seed players from ``missing_player_ids.txt``, then optionally
re-run Statcast for specific dates.

Usage::

    python fix_missing_players.py
    python fix_missing_players.py 2026-03-20 2026-03-21
"""

from __future__ import annotations

import sys
from datetime import datetime

import config  # noqa: F401 — load .env
from seed_missing_players import main as seed_missing_main
from statcast_pipeline import run_pipeline_for_date


def _validate_date(value: str) -> str:
    datetime.strptime(value.strip(), "%Y-%m-%d")
    return value.strip()


def main() -> None:
    seed_missing_main()

    raw_dates = sys.argv[1:]
    dates: list[str] = []
    for d in raw_dates:
        try:
            dates.append(_validate_date(d))
        except ValueError as exc:
            print(
                f"fix_missing_players: invalid date {d!r}; "
                "expected YYYY-MM-DD.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc

    for d in dates:
        print(f"fix_missing_players: re-running Statcast for {d}…", flush=True)
        run_pipeline_for_date(d)

    if not dates:
        print(
            "fix_missing_players: no dates passed; only ran seed_missing_players.",
            flush=True,
        )


if __name__ == "__main__":
    main()
