"""
Seed ``players`` (SCHEMA.md) for MLBAM IDs listed in ``missing_player_ids.txt``.

Populated by :func:`statcast_pipeline.upsert_statcast` when pitch rows skip due
to FK (missing ``players.id``). Fetches each missing id from the MLB Stats API
and upserts. Rewrites the ID file to only IDs that could not be seeded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import config  # noqa: F401 — load .env before db access
from db import get_client
from seed_players import map_person_to_row

MISSING_IDS_PATH = Path(__file__).resolve().parent / "missing_player_ids.txt"
PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people/{player_id}?hydrate=currentTeam"
_LOOK_CHUNK = 500


def _read_ids_from_file() -> list[int]:
    if not MISSING_IDS_PATH.exists():
        return []
    try:
        text = MISSING_IDS_PATH.read_text(encoding="utf-8")
    except OSError:
        return []
    out: set[int] = set()
    for line in text.splitlines():
        s = line.strip()
        if s.isdigit():
            out.add(int(s))
    return sorted(out)


def _existing_player_ids(ids: list[int]) -> set[int]:
    if not ids:
        return set()
    client = get_client()
    found: set[int] = set()
    for i in range(0, len(ids), _LOOK_CHUNK):
        batch = ids[i : i + _LOOK_CHUNK]
        resp = client.table("players").select("id").in_("id", batch).execute()
        for r in resp.data or []:
            pid = r.get("id")
            if pid is not None:
                found.add(int(pid))
    return found


def _fetch_person(player_id: int) -> dict[str, Any] | None:
    url = PEOPLE_URL.format(player_id=player_id)
    req = Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
    try:
        with urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"seed_missing_players: fetch failed for id={player_id}: {exc}")
        return None
    people = payload.get("people") or []
    if not people:
        print(f"seed_missing_players: empty people[] for id={player_id}")
        return None
    person = people[0]
    if not isinstance(person, dict):
        return None
    return person


def _upsert_players_rows(rows: list[dict[str, Any]]) -> tuple[int, int]:
    client = get_client()
    ok = 0
    failed = 0
    for row in rows:
        try:
            client.table("players").upsert([row], on_conflict="id").execute()
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"seed_missing_players: upsert failed id={row.get('id')}: {exc}")
            failed += 1
    return ok, failed


def main() -> None:
    ids = _read_ids_from_file()
    if not ids:
        print(
            "seed_missing_players: missing_player_ids.txt is missing or empty; "
            "nothing to do.",
        )
        return

    in_db = _existing_player_ids(ids)
    already = len(in_db)
    pending = [pid for pid in ids if pid not in in_db]

    print(
        f"seed_missing_players: {len(ids)} unique id(s) in file — "
        f"{already} already in players, {len(pending)} to resolve.",
    )

    if not pending:
        MISSING_IDS_PATH.write_text("", encoding="utf-8")
        print(
            "seed_missing_players: done — already_in_db="
            f"{already}, fetched_inserted=0, failed=0 (cleared file).",
        )
        return

    rows: list[dict[str, Any]] = []
    failed_fetch = 0
    for pid in pending:
        person = _fetch_person(pid)
        if person is None:
            failed_fetch += 1
            continue
        row = map_person_to_row(person)
        if row is None:
            failed_fetch += 1
            print(f"seed_missing_players: map_person_to_row skipped id={pid}")
            continue
        rows.append(row)

    inserted_ok, upsert_failed = _upsert_players_rows(rows)

    still = set(pending) - _existing_player_ids(pending)
    MISSING_IDS_PATH.write_text(
        "".join(f"{pid}\n" for pid in sorted(still)),
        encoding="utf-8",
    )

    failed_total = failed_fetch + upsert_failed
    if not still:
        print(
            "seed_missing_players: cleared missing_player_ids.txt "
            "(all pending IDs now in players).",
        )

    print(
        "seed_missing_players: done — "
        f"already_in_db={already}, fetched_inserted={inserted_ok}, "
        f"failed={failed_total} (fetch_fail={failed_fetch}, "
        f"upsert_fail={upsert_failed}), remaining_in_file={len(still)}.",
    )


if __name__ == "__main__":
    main()
