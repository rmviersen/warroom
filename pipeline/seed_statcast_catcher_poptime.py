"""
Seed ``statcast_catcher_defense`` catcher pop-time leaderboards from Baseball Savant
via pybaseball ``statcast_catcher_poptime``.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from pybaseball import statcast_catcher_poptime

import config  # noqa: F401 — load .env via side effect
from db import get_client

POPTIME_FIRST_SEASON = 2016
_DELAY_BETWEEN_SEASONS_SEC = 3.0
_BATCH_SIZE = 500


def _format_player_name(raw: Any) -> str | None:
    """Savant leaderboard names are often ``Last, First``. Normalize to ``First Last``."""

    if raw is None:
        return None
    try:
        if isinstance(raw, float) and pd.isna(raw):  # type: ignore[union-attr]
            return None
    except Exception:  # noqa: BLE001
        pass
    s = str(raw).strip()
    if not s:
        return None
    if ", " in s:
        last, first = s.split(", ", 1)
        merged = f"{first.strip()} {last.strip()}".strip()
        return merged or None
    return s


def _to_optional_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        if pd.isna(val):  # type: ignore[arg-type]
            return None
    except TypeError:
        pass
    x = pd.to_numeric(val, errors="coerce")
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        return None
    return int(round(float(x)))


def _to_optional_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        if pd.isna(val):  # type: ignore[arg-type]
            return None
    except TypeError:
        pass
    x = pd.to_numeric(val, errors="coerce")
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        return None
    return float(x)


SOURCE_COLS_EXPECTED = (
    "entity_id",
    "entity_name",
    "team_id",
    "maxeff_arm_2b_3b_sba",
    "exchange_2b_3b_sba",
    "pop_2b_sba_count",
    "pop_2b_sba",
    "pop_2b_cs",
    "pop_2b_sb",
    "pop_3b_sba_count",
    "pop_3b_sba",
    "pop_3b_cs",
    "pop_3b_sb",
)


def dataframe_to_records(df: pd.DataFrame, *, season: int) -> list[dict[str, Any]]:
    """Map Savant pop-time leaderboard rows to ``statcast_catcher_defense`` payloads."""

    if df.empty:
        return []

    missing = [c for c in SOURCE_COLS_EXPECTED if c not in df.columns]
    if missing:
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []

    for _, rr in df.iterrows():
        pid = _to_optional_int(rr.get("entity_id"))
        if pid is None:
            continue

        rec: dict[str, Any] = {
            "player_id": pid,
            "player_name": _format_player_name(rr.get("entity_name")),
            "season": season,
            "team_id": _to_optional_int(rr.get("team_id")),
            "max_eff_arm_2b_3b": _to_optional_float(rr.get("maxeff_arm_2b_3b_sba")),
            "exchange_2b_3b": _to_optional_float(rr.get("exchange_2b_3b_sba")),
            "pop_2b_sba_count": _to_optional_int(rr.get("pop_2b_sba_count")),
            "pop_2b_sba": _to_optional_float(rr.get("pop_2b_sba")),
            "pop_2b_cs": _to_optional_float(rr.get("pop_2b_cs")),
            "pop_2b_sb": _to_optional_float(rr.get("pop_2b_sb")),
            "pop_3b_sba_count": _to_optional_int(rr.get("pop_3b_sba_count")),
            "pop_3b_sba": _to_optional_float(rr.get("pop_3b_sba")),
            "pop_3b_cs": _to_optional_float(rr.get("pop_3b_cs")),
            "pop_3b_sb": _to_optional_float(rr.get("pop_3b_sb")),
            "updated_at": now_iso,
        }
        rows.append(rec)

    return rows


def upsert_catcher_defense(
    rows: list[dict[str, Any]], *, client: Any | None = None
) -> tuple[int, int]:
    """Batch upserts; returns ``(ok_count, failed_count)``."""

    if not rows:
        return 0, 0

    if client is None:
        client = get_client()

    ok_count = 0
    failed_count = 0

    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("statcast_catcher_defense").upsert(
                batch,
                on_conflict="player_id,season",
            ).execute()
            ok_count += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(
                f"seed_statcast_catcher_poptime: upsert batch {batch_no} failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            failed_count += len(batch)

    return ok_count, failed_count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    now_y = datetime.now().year
    p = argparse.ArgumentParser(description=__doc__.strip())
    p.add_argument(
        "--start-season",
        type=int,
        default=POPTIME_FIRST_SEASON,
        help=f"First season inclusive (default: {POPTIME_FIRST_SEASON}).",
    )
    p.add_argument(
        "--end-season",
        type=int,
        default=now_y,
        help=f"Last season inclusive (default: current year, {now_y}).",
    )
    return p.parse_args(argv)


def main() -> None:
    ns = parse_args()
    start_season = ns.start_season
    end_season = ns.end_season

    if start_season > end_season:
        print(
            f"--start-season ({start_season}) must be <= --end-season ({end_season})",
            file=sys.stderr,
        )
        sys.exit(2)

    client = get_client()
    seasons_all = list(range(start_season, end_season + 1))

    skipped = [y for y in seasons_all if y < POPTIME_FIRST_SEASON]
    for y in skipped:
        print(
            f"[warn] seed_statcast_catcher_poptime: season {y} skipped "
            f"(no data scraped before {POPTIME_FIRST_SEASON})",
            flush=True,
        )

    seasons = [y for y in seasons_all if y >= POPTIME_FIRST_SEASON]

    cumulative_ok_rows = 0
    cumulative_fail_rows = 0
    seasons_fetch_failed = 0
    seasons_missing_columns = 0

    for idx, year in enumerate(seasons):
        if idx > 0:
            time.sleep(_DELAY_BETWEEN_SEASONS_SEC)

        try:
            df = statcast_catcher_poptime(year)
        except Exception as exc:  # noqa: BLE001
            seasons_fetch_failed += 1
            print(
                f"seed_statcast_catcher_poptime: season={year} FETCH FAILED "
                f"({type(exc).__name__}: {exc})",
                flush=True,
            )
            continue

        n_src = len(df)
        missing = [c for c in SOURCE_COLS_EXPECTED if c not in df.columns]

        if missing:
            seasons_missing_columns += 1
            print(
                f"seed_statcast_catcher_poptime: season={year} rows_in_source={n_src} "
                f"MISSING_COLUMNS={missing} — skip upsert",
                flush=True,
            )
            continue

        records = dataframe_to_records(df, season=year)
        ok_now, failed_now = upsert_catcher_defense(records, client=client)
        cumulative_ok_rows += ok_now
        cumulative_fail_rows += failed_now

        print(
            f"seed_statcast_catcher_poptime: season={year} "
            f"rows_in_source={n_src} mapped_rows={len(records)} "
            f"upsert_ok={ok_now} upsert_failed={failed_now}",
            flush=True,
        )

    print(
        f"seed_statcast_catcher_poptime: done — seasons_scanned={len(seasons)} "
        f"season_fetch_failures={seasons_fetch_failed} "
        f"seasons_missing_columns={seasons_missing_columns} "
        f"rows_upserted_ok={cumulative_ok_rows} "
        f"rows_upsert_failed={cumulative_fail_rows}",
        flush=True,
    )


if __name__ == "__main__":
    main()
