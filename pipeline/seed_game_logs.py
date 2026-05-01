"""
Backfill ``game_logs`` (SCHEMA.md) from the MLB Stats API schedule endpoint.

Requires ``game_logs.game_pk`` UNIQUE (or equivalent) for PostgREST upsert.
"""

from __future__ import annotations

import sys
import time
from datetime import date
from typing import Any

import requests

import config  # noqa: F401 — load .env via side effect
from db import get_client

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
REQUEST_TIMEOUT = 120
SEASON_DELAY_SEC = 1.0
_BATCH_SIZE = 500
USER_AGENT = "WARroom-pipeline/1.0"

ALLOWED_STATUS = frozenset({"Final", "Completed Early"})


def _parse_season_range() -> tuple[int, int]:
    argv = sys.argv[1:]
    now_y = date.today().year
    try:
        if len(argv) == 0:
            return now_y, now_y
        if len(argv) == 1:
            return int(argv[0]), now_y
        if len(argv) == 2:
            return int(argv[0]), int(argv[1])
    except ValueError:
        print("Invalid season argument(s); integers required.", file=sys.stderr)
        sys.exit(2)

    print(
        "Usage: python seed_game_logs.py [start_season [end_season]]\n"
        "  (no args)     current calendar year only\n"
        "  2022          from 2022 through current year inclusive\n"
        "  2022 2024     from 2022 through 2024 inclusive",
        file=sys.stderr,
    )
    sys.exit(2)


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


def _fetch_schedule_json(season: int) -> dict[str, Any]:
    params = {
        "sportId": 1,
        "season": season,
        "gameType": "R",
        "hydrate": "linescore,venue,team",
    }
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(
        SCHEDULE_URL,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _iter_games(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for day in payload.get("dates") or []:
        for g in day.get("games") or []:
            out.append(g)
    return out


def _game_to_row(game: dict[str, Any]) -> dict[str, Any] | None:
    status = (game.get("status") or {}).get("detailedState") or ""
    if status not in ALLOWED_STATUS:
        return None

    teams = game.get("teams") or {}
    home_side = teams.get("home") or {}
    away_side = teams.get("away") or {}
    home_team = home_side.get("team") or {}
    away_team = away_side.get("team") or {}

    game_pk = _safe_int(game.get("gamePk"))
    if game_pk is None:
        return None

    home_team_id = _safe_int(home_team.get("id"))
    away_team_id = _safe_int(away_team.get("id"))

    official = game.get("officialDate")
    if isinstance(official, str) and len(official) >= 10:
        game_date = official[:10]
    else:
        gd = game.get("gameDate")
        if isinstance(gd, str) and "T" in gd:
            game_date = gd.split("T", 1)[0]
        elif isinstance(gd, str) and len(gd) >= 10:
            game_date = gd[:10]
        else:
            return None

    home_name = home_team.get("name")
    away_name = away_team.get("name")
    venue_obj = game.get("venue") or {}
    venue_name = venue_obj.get("name")

    home_score: int | None = None
    away_score: int | None = None
    if status in ALLOWED_STATUS:
        home_score = _safe_int(home_side.get("score"))
        away_score = _safe_int(away_side.get("score"))

    return {
        "game_pk": game_pk,
        "game_date": game_date,
        "home_team": home_name,
        "home_team_id": home_team_id,
        "away_team": away_name,
        "away_team_id": away_team_id,
        "home_score": home_score,
        "away_score": away_score,
        "status": status,
        "venue": venue_name,
    }


def upsert_game_logs(rows: list[dict[str, Any]], client: Any) -> tuple[int, int]:
    ok = 0
    failed = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("game_logs").upsert(
                batch,
                on_conflict="game_pk",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(
                f"seed_game_logs: upsert batch {batch_no} failed: {exc}",
                flush=True,
            )
            failed += len(batch)
    return ok, failed


def seed_season(
    year: int, client: Any, sleep_before: bool
) -> tuple[int, int, int, int, bool]:
    """
    Fetch schedule for ``year``, upsert final / completed-early games.

    Returns (total_games_in_payload, unique_final_rows, upsert_ok, upsert_failed, fetch_ok).
    """
    if sleep_before:
        time.sleep(SEASON_DELAY_SEC)

    try:
        payload = _fetch_schedule_json(year)
    except Exception as exc:  # noqa: BLE001
        print(f"season {year}: schedule fetch failed: {exc}", flush=True)
        return 0, 0, 0, 0, False

    all_games = _iter_games(payload)
    total = len(all_games)
    all_rows: list[dict[str, Any]] = []
    for g in all_games:
        row = _game_to_row(g)
        if row is not None:
            all_rows.append(row)

    seen: dict[int, dict[str, Any]] = {}
    for row in all_rows:
        seen[row["game_pk"]] = row
    deduped_rows = list(seen.values())

    if len(all_rows) != len(deduped_rows):
        print(
            f"  removed {len(all_rows) - len(deduped_rows)} duplicate game_pk(s)",
            flush=True,
        )

    final_n = len(deduped_rows)
    upsert_ok, upsert_fail = upsert_game_logs(deduped_rows, client)
    return total, final_n, upsert_ok, upsert_fail, True


def main() -> None:
    start_y, end_y = _parse_season_range()
    if start_y > end_y:
        print("start_season must be <= end_season", file=sys.stderr)
        sys.exit(2)

    client = get_client()
    seasons = list(range(start_y, end_y + 1))
    total_ok = 0
    total_fail = 0

    for i, year in enumerate(seasons):
        total, final_n, ok, fail, _ = seed_season(
            year, client, sleep_before=(i > 0)
        )
        print(
            f"season {year}: fetched {total} games, "
            f"{final_n} final, upserted {ok} rows",
            flush=True,
        )
        total_ok += ok
        total_fail += fail

    print(
        f"Total seasons: {len(seasons)}, "
        f"Total games upserted: {total_ok}, "
        f"Failed: {total_fail}",
        flush=True,
    )


if __name__ == "__main__":
    main()
