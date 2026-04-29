"""
Seed ``teams`` (SCHEMA.md) from the MLB Stats API.

Endpoint:
  GET /api/v1/teams?sportId=1
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

# Load .env first (side effect of importing config).
import config  # noqa: F401
from db import get_client

MLB_TEAMS_URL = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
_BATCH_SIZE = 500


def fetch_teams() -> list[dict[str, Any]]:
    """Return the raw ``teams`` array from the MLB Stats API."""

    req = urllib.request.Request(MLB_TEAMS_URL, headers={"User-Agent": "WARroom-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"MLB API request failed: {exc}") from exc

    return list(payload.get("teams") or [])


def _venue_name(team: dict[str, Any]) -> str | None:
    """Normalize ``venue`` to a string name, or None."""

    venue = team.get("venue")
    if venue is None:
        return None
    if isinstance(venue, str):
        return venue or None
    if isinstance(venue, dict):
        n = venue.get("name")
        return str(n) if n else None
    return None


def map_team_to_row(team: dict[str, Any]) -> dict[str, Any] | None:
    """
    Map one MLB ``teams`` object to a row matching ``teams`` in SCHEMA.md.

    ``name`` is NOT NULL in the schema; skips entries without ``id`` or ``name``.
    """

    tid = team.get("id")
    name = team.get("name")
    if tid is None or not name:
        return None

    division = team.get("division") or {}
    league = team.get("league") or {}
    div_id = division.get("id")
    league_id = league.get("id")

    return {
        "id": int(tid),
        "name": str(name),
        "abbreviation": team.get("abbreviation"),
        "team_name": team.get("teamName"),
        "location_name": team.get("locationName"),
        "division": division.get("name"),
        "division_id": int(div_id) if div_id is not None else None,
        "league": league.get("name"),
        "league_id": int(league_id) if league_id is not None else None,
        "venue": _venue_name(team),
    }


def upsert_teams(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """
    Upsert team rows in batches of ``_BATCH_SIZE``.

    Returns (success_row_count, failed_row_count).
    """

    client = get_client()
    ok = 0
    failed = 0

    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("teams").upsert(batch, on_conflict="id").execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_teams: batch {batch_no} failed: {exc}")
            failed += len(batch)

    return ok, failed


def main() -> None:
    print("seed_teams: fetching MLB teams (sportId=1)…")

    raw = fetch_teams()
    rows: list[dict[str, Any]] = []
    for team in raw:
        row = map_team_to_row(team)
        if row is not None:
            rows.append(row)

    print(f"seed_teams: mapped {len(rows)} rows from {len(raw)} API records; upserting…")

    ok, failed = upsert_teams(rows)
    print(f"seed_teams: done — upserted {ok} rows, {failed} row(s) in failed batches.")


if __name__ == "__main__":
    main()
