"""
Compute baserunning Wins Above Replacement (brWPR) per player batting season.

Two components — both converted to wins via the shared RPW formula:

  wSB (1990+)
    Stolen-base runs: ``SB × runSB + CS × runCS`` using season-specific
    linear weights from ``calculations.baserunning_calcs.get_wsb_weights``.

  Sprint-speed runs (2015+)
    Sprint speed z-score vs the season league distribution, scaled by the
    player's competitive-running opportunities relative to league average,
    then multiplied by ``SPRINT_RUNS_SCALE`` to convert to runs.
    Requires a populated ``statcast_running`` row for the player-season.

Writes ``brwpr`` via ``upsert_player_batting_seasons`` (partial upsert — never
overwrites ``bwpr``, ``fwpr``, or counting stats).

Usage::

    python calc_baserunning_season_metrics.py --start-season 1990 --end-season 2026
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

import config  # noqa: F401 — load pipeline/.env

from calc_batting_season_metrics import (
    get_mlb_games_played,
    load_league_batting_averages_row,
    load_league_pitching_ip,
)
from calculations.baserunning_calcs import (
    SPRINT_SPEED_FIRST_SEASON,
    calc_baserunning_war,
    calc_sprint_runs,
    calc_wsb_runs,
)
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


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_statcast_running(client: Any, season: int) -> dict[int, dict[str, Any]]:
    """
    Load all ``statcast_running`` rows for ``season``.
    Returns a dict keyed by ``player_id``.
    """
    by_player: dict[int, dict[str, Any]] = {}
    offset = 0
    while True:
        try:
            resp = (
                client.table("statcast_running")
                .select("player_id,sprint_speed,competitive_runs")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_baserunning_season_metrics: statcast_running read "
                f"season={season} offset={offset} failed: {exc}",
                flush=True,
            )
            break
        rows = resp.data or []
        for row in rows:
            pid = _to_int(row.get("player_id"))
            if pid is None:
                continue
            by_player[pid] = {
                "sprint_speed":     _to_float(row.get("sprint_speed")),
                "competitive_runs": _to_float(row.get("competitive_runs")),
            }
        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return by_player


def build_sprint_league_stats(
    running_by_player: dict[int, dict[str, Any]],
) -> tuple[float, float]:
    """
    Compute league-wide mean and std of sprint speed from the season's
    ``statcast_running`` data.

    Returns ``(lg_avg_speed, lg_std_speed)``.
    Falls back to zeros when data is absent.
    """
    speeds = [
        r["sprint_speed"]
        for r in running_by_player.values()
        if r["sprint_speed"] is not None
    ]

    if not speeds:
        return 0.0, 0.0

    n = len(speeds)
    avg_speed = math.fsum(speeds) / n
    variance = math.fsum((s - avg_speed) ** 2 for s in speeds) / n
    std_speed = math.sqrt(variance) if variance > 0 else 0.0

    return float(avg_speed), float(std_speed)


def flush_brwpr(client: Any, payloads: list[dict[str, Any]]) -> tuple[int, int, int]:
    ok = failed = failed_batches = 0
    n_batches = (len(payloads) + _RPC_BATCH - 1) // _RPC_BATCH if payloads else 0
    for i in range(0, len(payloads), _RPC_BATCH):
        batch = payloads[i : i + _RPC_BATCH]
        batch_idx = i // _RPC_BATCH + 1
        try:
            client.rpc("upsert_player_batting_seasons", {"rows": batch}).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            failed += len(batch)
            failed_batches += 1
            print(
                f"calc_baserunning_season_metrics: RPC batch {batch_idx}/{n_batches} "
                f"failed ({len(batch)} rows) — {exc}",
                flush=True,
            )
    return ok, failed, failed_batches


# ---------------------------------------------------------------------------
# Per-season runner
# ---------------------------------------------------------------------------

def run_season(client: Any, season: int) -> dict[str, int]:
    stats: dict[str, int] = defaultdict(int)

    lg_bat = load_league_batting_averages_row(client, season)
    if lg_bat is None:
        print(
            f"calc_baserunning_season_metrics: no league_batting_averages for "
            f"season={season}; skipping.",
            flush=True,
        )
        return dict(stats)

    lg_r = _to_float(lg_bat.get("lg_r"))
    lg_ip = load_league_pitching_ip(client, season)
    if lg_r is None or lg_ip is None or lg_ip <= 0:
        print(
            f"calc_baserunning_season_metrics: missing lg_r/lg_ip for "
            f"season={season}; skipping.",
            flush=True,
        )
        return dict(stats)

    try:
        get_mlb_games_played(client, season)
    except Exception as exc:  # noqa: BLE001
        print(
            f"calc_baserunning_season_metrics: get_mlb_games_played season={season} "
            f"warning ({exc}); continuing.",
            flush=True,
        )

    # Load sprint speed data when in Statcast era
    running_by_player: dict[int, dict[str, Any]] = {}
    if season >= SPRINT_SPEED_FIRST_SEASON:
        running_by_player = load_statcast_running(client, season)
        stats["sprint_rows"] = len(running_by_player)

    lg_avg_speed, lg_std_speed = build_sprint_league_stats(running_by_player)

    payloads: list[dict[str, Any]] = []
    offset = 0

    while True:
        try:
            resp = (
                client.table("player_batting_seasons")
                .select("player_id,season,team_id,sb,cs")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_baserunning_season_metrics: player_batting_seasons read "
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

            sb = _to_float(row.get("sb"))
            cs = _to_float(row.get("cs"))

            wsb_runs = calc_wsb_runs(sb, cs, season)

            sprint_runs: float | None = None
            if season >= SPRINT_SPEED_FIRST_SEASON and pid in running_by_player:
                r = running_by_player[pid]
                sprint_runs = calc_sprint_runs(
                    r["sprint_speed"],
                    r["competitive_runs"],
                    lg_avg_speed,
                    lg_std_speed,
                )
                stats["sprint_path"] += 1
            else:
                stats["wsb_only_path"] += 1

            brwpr = calc_baserunning_war(wsb_runs, sprint_runs, float(lg_r), float(lg_ip))
            if brwpr is None:
                stats["skipped_no_rpw"] += 1
                continue

            payloads.append({
                "player_id": pid,
                "season":    season,
                "team_id":   tid,
                "brwpr":     brwpr,
            })

        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    ok, fail, fail_batches = flush_brwpr(client, payloads)
    stats["rows_written"] = ok
    stats["rows_failed"]  = fail

    print(
        f"calc_baserunning_season_metrics: season={season} "
        f"batting_rows={stats['batting_rows']} sprint_rows={stats['sprint_rows']} "
        f"sprint_path={stats['sprint_path']} wsb_only_path={stats['wsb_only_path']} "
        f"rows_written={ok} rows_failed={fail}",
        flush=True,
    )
    return dict(stats)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    start, end = args.start_season, args.end_season
    if start > end:
        raise SystemExit(
            f"calc_baserunning_season_metrics: --start-season ({start}) "
            f"must be <= --end-season ({end})."
        )

    client = get_client()
    total_written = total_failed = 0

    for season in range(start, end + 1):
        s = run_season(client, season)
        total_written += s.get("rows_written", 0)
        total_failed  += s.get("rows_failed", 0)

    print(
        f"calc_baserunning_season_metrics: done — "
        f"total_rows_written={total_written} total_failures={total_failed}",
        flush=True,
    )


if __name__ == "__main__":
    main()
