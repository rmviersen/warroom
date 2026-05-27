"""
Seed ``statcast_running`` from the Baseball Savant sprint speed leaderboard.

Fetches sprint speed, home-to-first time, bolt counts, and competitive running
opportunities for each season (2015+) and upserts on ``(player_id, season)``.

Usage::

    python seed_statcast_running.py --start-season 2015 --end-season 2026
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

import config  # noqa: F401 — load pipeline/.env
from db import get_client

SAVANT_SPRINT_URL = (
    "https://baseballsavant.mlb.com/leaderboard/sprint_speed"
    "?year={season}&position=&team=&min=1&csv=true"
)

RUNNING_FIRST_SEASON = 2015
_REQUEST_TIMEOUT_SEC = 120
_DELAY_BETWEEN_REQUESTS_SEC = 2.0
_BATCH_SIZE = 500
_NAME_COL = "last_name, first_name"


def _format_player_name(raw: Any) -> str | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, float) and pd.isna(raw):
            return None
    except Exception:  # noqa: BLE001
        pass
    s = str(raw).strip()
    if not s:
        return None
    if ", " in s:
        last, first = s.split(", ", 1)
        return f"{first.strip()} {last.strip()}".strip() or None
    return s


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        if pd.isna(val):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    x = pd.to_numeric(val, errors="coerce")
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        return None
    return int(round(float(x)))


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        if pd.isna(val):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    x = pd.to_numeric(val, errors="coerce")
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        return None
    return float(x)


def _to_str(val: Any) -> str | None:
    if val is None:
        return None
    try:
        if isinstance(val, float) and pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return s if s else None


def fetch_sprint_csv(season: int) -> tuple[pd.DataFrame | None, str | None]:
    url = SAVANT_SPRINT_URL.format(season=season)
    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return None, f"HTTP error: {type(exc).__name__}: {exc}"

    raw = resp.text.strip()
    if not raw:
        return None, "empty response"
    if raw.lstrip().startswith("<"):
        return None, f"unexpected HTML ({len(raw)} chars)"

    try:
        df = pd.read_csv(io.StringIO(raw))
    except Exception as exc:  # noqa: BLE001
        return None, f"CSV parse error: {type(exc).__name__}: {exc}"

    return df, None


def dataframe_to_records(df: pd.DataFrame, *, season: int) -> list[dict[str, Any]]:
    if df.empty or "player_id" not in df.columns:
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []

    for _, rr in df.iterrows():
        pid = _to_int(rr.get("player_id"))
        if pid is None:
            continue

        bolts = _to_int(rr.get("bolts"))
        comp_runs = _to_int(rr.get("competitive_runs"))
        bolt_rate: float | None = None
        if bolts is not None and comp_runs is not None and comp_runs > 0:
            bolt_rate = round(bolts / comp_runs, 4)

        rows.append({
            "player_id":        pid,
            "player_name":      _format_player_name(rr.get(_NAME_COL)),
            "team_id":          _to_int(rr.get("team_id")),
            "team":             _to_str(rr.get("team")),
            "season":           season,
            "position":         _to_str(rr.get("position")),
            "age":              _to_int(rr.get("age")),
            "sprint_speed":     _to_float(rr.get("sprint_speed")),
            "hp_to_1b":         _to_float(rr.get("hp_to_1b")),
            "bolts":            bolts,
            "competitive_runs": comp_runs,
            "bolt_rate":        bolt_rate,
            "updated_at":       now_iso,
        })

    return rows


def upsert_running(rows: list[dict[str, Any]], *, client: Any) -> tuple[int, int]:
    if not rows:
        return 0, 0
    ok = failed = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        try:
            client.table("statcast_running").upsert(
                batch,
                on_conflict="player_id,season",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(
                f"seed_statcast_running: upsert batch failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            failed += len(batch)
    return ok, failed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    now_y = datetime.now().year
    p = argparse.ArgumentParser(description=__doc__.strip())
    p.add_argument(
        "--start-season", type=int, default=RUNNING_FIRST_SEASON,
        help=f"First season inclusive (default: {RUNNING_FIRST_SEASON}).",
    )
    p.add_argument(
        "--end-season", type=int, default=now_y,
        help=f"Last season inclusive (default: current year, {now_y}).",
    )
    return p.parse_args(argv)


def main() -> None:
    ns = parse_args()
    start, end = ns.start_season, ns.end_season

    if start > end:
        print(
            f"--start-season ({start}) must be <= --end-season ({end})",
            file=sys.stderr,
        )
        sys.exit(2)

    client = get_client()
    seasons = list(range(max(start, RUNNING_FIRST_SEASON), end + 1))
    skipped = [y for y in range(start, end + 1) if y < RUNNING_FIRST_SEASON]

    for y in skipped:
        print(
            f"seed_statcast_running: season {y} skipped "
            f"(sprint speed data not available before {RUNNING_FIRST_SEASON})",
            flush=True,
        )

    total_ok = total_fail = total_fetch_fail = 0

    for idx, season in enumerate(seasons):
        if idx > 0:
            time.sleep(_DELAY_BETWEEN_REQUESTS_SEC)

        df, err = fetch_sprint_csv(season)
        if err is not None:
            total_fetch_fail += 1
            print(f"seed_statcast_running: season={season} fetch FAILED — {err}", flush=True)
            continue

        if df is None or len(df) == 0:
            print(f"seed_statcast_running: season={season} no rows returned", flush=True)
            continue

        records = dataframe_to_records(df, season=season)
        ok, fail = upsert_running(records, client=client)
        total_ok += ok
        total_fail += fail

        print(
            f"seed_statcast_running: season={season} "
            f"csv_rows={len(df)} records_built={len(records)} "
            f"upsert_ok={ok} upsert_failed={fail}",
            flush=True,
        )

    print(
        f"seed_statcast_running: done — "
        f"seasons={len(seasons)} fetch_failures={total_fetch_fail} "
        f"rows_upserted={total_ok} rows_failed={total_fail}",
        flush=True,
    )


if __name__ == "__main__":
    main()
