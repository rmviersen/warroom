"""
Backfill ``game_logs`` counting-stat columns from the MLB Stats API boxscore.

For each row where ``home_hits`` is NULL (all new box columns ship together),
fetches ``/game/{gamePk}/boxscore``, reads ``teams.*.teamStats.batting``, and
updates the row in place via ``game_pk``. Singles are computed as
``hits - doubles - triples - homeRuns`` when components are present.

With ``--fix-incomplete``, targets rows where ``home_hits`` is filled but
``home_hr`` is still NULL (partial enrichment).

Requires the box-score columns from ``SCHEMA.md`` / migration
``20260511120000_game_logs_box_score_stats.sql``.

Usage:
  python enrich_game_logs.py
  python enrich_game_logs.py --delay 1.0 --limit 500
  python enrich_game_logs.py --fix-incomplete
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import requests

import config  # noqa: F401 — load .env via side effect
from db import get_client

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
REQUEST_TIMEOUT = 120
DEFAULT_API_DELAY_SEC = 0.75
_PAGE_SIZE = 500
USER_AGENT = "WARroom-pipeline/1.0"


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


def _fetch_boxscore(game_pk: int) -> dict[str, Any]:
    url = f"{MLB_API_BASE}/game/{game_pk}/boxscore"
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _batting_counting_payload(
    batting: dict[str, Any],
    prefix: str,
) -> dict[str, Any] | None:
    """
    Map MLB ``teamStats.batting`` to ``home_*`` / ``away_*`` SCHEMA columns.

    Returns None if required raw fields are missing.
    """

    hits = _safe_int(batting.get("hits"))
    doubles = _safe_int(batting.get("doubles"))
    triples = _safe_int(batting.get("triples"))
    home_runs = _safe_int(batting.get("homeRuns"))
    walks = _safe_int(batting.get("baseOnBalls"))
    strikeouts = _safe_int(batting.get("strikeOuts"))

    if hits is None:
        return None

    singles: int | None = None
    components = [doubles, triples, home_runs]
    if all(c is not None for c in components):
        d, t, hr = doubles, triples, home_runs
        assert d is not None and t is not None and hr is not None
        singles = hits - d - t - hr
        if singles < 0:
            print(
                f"  warn game_pk: negative singles derived "
                f"({hits=} {d=} {t=} {hr=}); storing singles as NULL",
                flush=True,
            )
            singles = None

    out: dict[str, Any] = {
        f"{prefix}_hits": hits,
        f"{prefix}_hr": home_runs,
        f"{prefix}_bb": walks,
        f"{prefix}_so": strikeouts,
        f"{prefix}_singles": singles,
        f"{prefix}_doubles": doubles,
        f"{prefix}_triples": triples,
    }
    return out


def _boxscore_to_update_row(box: dict[str, Any]) -> dict[str, Any] | None:
    teams = box.get("teams") or {}
    home_side = teams.get("home") or {}
    away_side = teams.get("away") or {}
    home_bat = (home_side.get("teamStats") or {}).get("batting") or {}
    away_bat = (away_side.get("teamStats") or {}).get("batting") or {}

    if not home_bat or not away_bat:
        return None

    home_part = _batting_counting_payload(home_bat, "home")
    away_part = _batting_counting_payload(away_bat, "away")
    if home_part is None or away_part is None:
        return None

    return {**home_part, **away_part}


def _fetch_game_pks_needing_enrich(
    client: Any,
    *,
    fix_incomplete: bool = False,
) -> list[int]:
    """
    Return ``game_pk`` values to enrich.

    Default: ``home_hits`` IS NULL (not yet backfilled).
    With ``fix_incomplete``: ``home_hits`` IS NOT NULL AND ``home_hr`` IS NULL.
    """

    seen: set[int] = set()
    offset = 0

    while True:
        try:
            q = client.table("game_logs").select("game_pk")
            if fix_incomplete:
                q = q.filter("home_hits", "not.is", "null").is_("home_hr", "null")
            else:
                q = q.is_("home_hits", "null")
            resp = (
                q.filter("game_pk", "not.is", "null")
                .order("game_pk")
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(f"enrich_game_logs: page fetch failed at offset {offset}: {exc}", flush=True)
            break

        rows = resp.data or []
        if not rows:
            break

        for row in rows:
            pk = _safe_int(row.get("game_pk"))
            if pk is not None:
                seen.add(pk)

        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    return sorted(seen)


def _update_game_log(client: Any, game_pk: int, payload: dict[str, Any]) -> bool:
    try:
        resp = (
            client.table("game_logs")
            .update(payload)
            .eq("game_pk", game_pk)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  game_pk {game_pk}: supabase update failed: {exc}", flush=True)
        return False

    err = getattr(resp, "error", None)
    if err:
        print(f"  game_pk {game_pk}: supabase error: {err}", flush=True)
        return False
    return True


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill game_logs box-score columns from MLB boxscore API.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_API_DELAY_SEC,
        metavar="SEC",
        help=f"sleep between MLB API calls (default: {DEFAULT_API_DELAY_SEC})",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="process at most N games (0 = no limit)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and parse only; do not write to Supabase",
    )
    p.add_argument(
        "--fix-incomplete",
        action="store_true",
        help=(
            "only rows with home_hits set but home_hr still null "
            "(partial enrichment); default mode is home_hits null"
        ),
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.delay < 0:
        print("--delay must be >= 0", file=sys.stderr)
        sys.exit(2)

    client = get_client()
    if args.dry_run:
        print("enrich_game_logs: dry-run mode — no Supabase writes", flush=True)
    if args.fix_incomplete:
        print(
            "enrich_game_logs: --fix-incomplete (home_hits not null, home_hr null)",
            flush=True,
        )

    game_pks = _fetch_game_pks_needing_enrich(
        client,
        fix_incomplete=args.fix_incomplete,
    )
    if args.limit and args.limit > 0:
        game_pks = game_pks[: args.limit]

    total = len(game_pks)
    print(
        f"enrich_game_logs: {total} game(s) to enrich "
        f"(API delay {args.delay}s between calls)",
        flush=True,
    )

    if total == 0:
        return

    ok = 0
    fetch_fail = 0
    parse_skip = 0
    update_fail = 0

    for i, game_pk in enumerate(game_pks):
        if i > 0 and args.delay > 0:
            time.sleep(args.delay)

        label = f"[{i + 1}/{total}] game_pk={game_pk}"
        try:
            box = _fetch_boxscore(game_pk)
        except requests.HTTPError as exc:
            print(f"{label}: HTTP error: {exc}", flush=True)
            fetch_fail += 1
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"{label}: fetch failed: {exc}", flush=True)
            fetch_fail += 1
            continue

        payload = _boxscore_to_update_row(box)
        if payload is None:
            print(f"{label}: could not parse team batting stats; skip", flush=True)
            parse_skip += 1
            continue

        if args.dry_run:
            ok += 1
            continue

        if _update_game_log(client, game_pk, payload):
            ok += 1
        else:
            update_fail += 1

    print(
        f"enrich_game_logs: done — updated {ok}, fetch_errors {fetch_fail}, "
        f"parse_skips {parse_skip}, update_errors {update_fail}",
        flush=True,
    )


if __name__ == "__main__":
    main()
