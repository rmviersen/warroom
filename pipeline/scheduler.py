"""
APScheduler entrypoint: poll Statcast during MLB-friendly Eastern hours.

Uses ``config.GAME_HOURS`` and ``config.POLL_INTERVAL_MINUTES`` so the cron
window stays in sync with shared settings.
"""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

import config
from statcast_pipeline import run_pipeline

_EASTERN = ZoneInfo("America/New_York")


def main() -> None:
    start_h = config.GAME_HOURS["start_hour"]
    end_h = config.GAME_HOURS["end_hour"]
    every = config.POLL_INTERVAL_MINUTES

    sched = BlockingScheduler(timezone=_EASTERN)

    sched.add_job(
        run_pipeline,
        CronTrigger(
            hour=f"{start_h}-{end_h}",
            minute=f"*/{every}",
            timezone=_EASTERN,
        ),
        id="statcast_poll",
        name="Statcast → statcast_pitches",
        max_instances=1,
        coalesce=True,
    )

    print(
        f"WARroom pipeline scheduler (Eastern): every {every} minutes "
        f"from {start_h}:00 through {end_h}:59.",
    )

    print("Running pipeline once immediately on startup…")
    run_pipeline()

    job = sched.get_job("statcast_poll")
    nxt = getattr(job, "next_run_time", None)
    if nxt:
        print(f"Next scheduled run (America/New_York): {nxt}")
    else:
        # Some APScheduler versions resolve this only after the loop starts.
        print(
            "Next run: see BlockingScheduler logs after start "
            f"(cron minutes */{every}, hours {start_h}-{end_h} Eastern).",
        )

    print("BlockingScheduler started — Ctrl+C to exit.")
    sched.start()


if __name__ == "__main__":
    main()
