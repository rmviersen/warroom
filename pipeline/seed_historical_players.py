"""
Seed ``players`` (SCHEMA.md) with all MLB players appearing on regular-season
rosters from 1990 through the current calendar year.

Uses the MLB Stats API per season:
  GET /api/v1/sports/1/players?season={year}&gameType=R

Expect ~35 API calls (~35s delay budget) and roughly 10k–15k unique players.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

import config  # noqa: F401
from db import get_client

START_SEASON = 1990
MLB_PLAYERS_URL = (
    "https://statsapi.mlb.com/api/v1/sports/1/players"
    "?season={season}&gameType=R"
)
_BATCH_SIZE = 500
_DELAY_SEC = 1


def fetch_season_players(season: int) -> list[dict[str, Any]]:
    url = MLB_PLAYERS_URL.format(season=season)
    req = urllib.request.Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"MLB API request failed for season={season}: {exc}") from exc

    return list(payload.get("people") or [])


def _optional_str(person: dict[str, Any], key: str) -> str | None:
    v = person.get(key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _parse_weight(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def map_person_to_row(person: dict[str, Any]) -> dict[str, Any] | None:
    """
    Map one MLB ``people`` object to columns in ``players`` (SCHEMA.md).

    Skips entries without ``id`` or ``fullName`` (``full_name`` is NOT NULL).
    """

    pid = person.get("id")
    full_name = person.get("fullName")
    if pid is None or not full_name:
        return None

    team = person.get("currentTeam") or {}
    if not isinstance(team, dict):
        team = {}
    pos = person.get("primaryPosition") or {}
    if not isinstance(pos, dict):
        pos = {}
    bat = person.get("batSide") or {}
    if not isinstance(bat, dict):
        bat = {}
    p_hand = person.get("pitchHand") or {}
    if not isinstance(p_hand, dict):
        p_hand = {}

    raw_num = person.get("primaryNumber")
    if raw_num is None or raw_num == "":
        jersey = None
    else:
        jersey = str(raw_num)

    birth_date = _optional_str(person, "birthDate")
    debut_raw = person.get("mlbDebutDate")
    if isinstance(debut_raw, str) and debut_raw.strip():
        debut_date = debut_raw.strip()
    else:
        debut_date = None

    team_id = team.get("id")
    active_raw = person.get("active")
    if active_raw is None:
        active = True
    else:
        active = bool(active_raw)

    return {
        "id": int(pid),
        "full_name": str(full_name),
        "name_first": _optional_str(person, "firstName"),
        "name_last": _optional_str(person, "lastName"),
        "team": team.get("name"),
        "team_id": int(team_id) if team_id is not None else None,
        "position": pos.get("abbreviation"),
        "jersey_number": jersey,
        "bats": bat.get("code"),
        "throws": p_hand.get("code"),
        "birth_date": birth_date,
        "birth_city": _optional_str(person, "birthCity"),
        "birth_country": _optional_str(person, "birthCountry"),
        "height": _optional_str(person, "height"),
        "weight": _parse_weight(person.get("weight")),
        "active": active,
        "debut_date": debut_date,
    }


def upsert_players(rows: list[dict[str, Any]]) -> tuple[int, int]:
    client = get_client()
    ok = 0
    failed = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("players").upsert(batch, on_conflict="id").execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_historical_players: batch {batch_no} failed: {exc}")
            failed += len(batch)
    return ok, failed


def main() -> None:
    end_season = datetime.now().year
    seasons = list(range(START_SEASON, end_season + 1))
    print(
        f"seed_historical_players: fetching seasons {START_SEASON}..{end_season} "
        f"({len(seasons)} year(s)), {_DELAY_SEC}s between requests…",
    )

    by_id: dict[int, dict[str, Any]] = {}

    for i, year in enumerate(seasons):
        people = fetch_season_players(year)
        added = 0
        for person in people:
            row = map_person_to_row(person)
            if row is None:
                continue
            pid = row["id"]
            if pid not in by_id:
                added += 1
            by_id[pid] = row
        print(
            f"seed_historical_players: season {year} — "
            f"{len(people)} roster row(s), "
            f"+{added} new id(s) this season, "
            f"{len(by_id)} unique player(s) total so far",
            flush=True,
        )
        if i < len(seasons) - 1:
            time.sleep(_DELAY_SEC)

    rows_sorted = sorted(by_id.values(), key=lambda r: r["id"])
    print(
        f"seed_historical_players: upserting {len(rows_sorted)} unique players "
        f"in {_BATCH_SIZE}-row batches…",
        flush=True,
    )
    ok, failed = upsert_players(rows_sorted)
    print(
        f"seed_historical_players: done — {len(by_id)} unique players, "
        f"{ok} row(s) accepted by upsert, {failed} row(s) in failed batches.",
        flush=True,
    )


if __name__ == "__main__":
    main()
