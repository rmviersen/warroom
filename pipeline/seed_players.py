"""
Seed ``players`` (SCHEMA.md) from the MLB Stats API active rosters for the
current regular season. Run before ``statcast_pipeline`` so ``player_id`` FKs
resolve.

Endpoint:
  GET /api/v1/sports/1/players?season={year}&gameType=R
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

# Load .env first (side effect of importing config).
import config  # noqa: F401
from db import get_client

MLB_PLAYERS_URL = (
    "https://statsapi.mlb.com/api/v1/sports/1/players"
    "?season={season}&gameType=R"
)
_BATCH_SIZE = 500


def fetch_active_players(season: int) -> list[dict[str, Any]]:
    """Return the raw ``people`` array from the MLB Stats API."""

    url = MLB_PLAYERS_URL.format(season=season)
    req = urllib.request.Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"MLB API request failed: {exc}") from exc

    return list(payload.get("people") or [])


def map_person_to_row(person: dict[str, Any]) -> dict[str, Any] | None:
    """
    Map one MLB ``people`` object to a row matching ``players`` in SCHEMA.md.

    Skips entries without ``id`` or ``fullName`` (``full_name`` is NOT NULL).
    """

    pid = person.get("id")
    full_name = person.get("fullName")
    if pid is None or not full_name:
        return None

    team = person.get("currentTeam") or {}
    pos = person.get("primaryPosition") or {}
    bat = person.get("batSide") or {}
    p_hand = person.get("pitchHand") or {}

    raw_num = person.get("primaryNumber")
    jersey: str | None
    if raw_num is None or raw_num == "":
        jersey = None
    else:
        jersey = str(raw_num)

    birth = person.get("birthDate")
    if isinstance(birth, str) and birth.strip():
        birth_date: str | None = birth.strip()
    else:
        birth_date = None

    team_id = team.get("id")
    return {
        "id": int(pid),
        "full_name": str(full_name),
        "team": team.get("name"),
        "team_id": int(team_id) if team_id is not None else None,
        "position": pos.get("abbreviation"),
        "jersey_number": jersey,
        "bats": bat.get("code"),
        "throws": p_hand.get("code"),
        "birth_date": birth_date,
        "active": True,
    }


def upsert_players(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """
    Upsert player rows in batches of ``_BATCH_SIZE``.

    Returns (success_row_count, failed_row_count).
    """

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
            print(f"seed_players: batch {batch_no} failed: {exc}")
            failed += len(batch)

    return ok, failed


def main() -> None:
    season = datetime.now().year
    print(f"seed_players: fetching active MLB players for season={season}…")

    raw = fetch_active_players(season)
    rows: list[dict[str, Any]] = []
    for person in raw:
        row = map_person_to_row(person)
        if row is not None:
            rows.append(row)

    print(f"seed_players: mapped {len(rows)} rows from {len(raw)} API records; upserting…")

    ok, failed = upsert_players(rows)
    print(f"seed_players: done — upserted {ok} rows, {failed} row(s) in failed batches.")


if __name__ == "__main__":
    main()
