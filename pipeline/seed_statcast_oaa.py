"""
Seed ``statcast_fielding_oaa`` from Baseball Savant unified OAA CSV leaderboards.

Fetches Outs Above Average by numeric position codes 3-9 for each season (Savant CSV
minimum threshold ``min=1``) and upserts on ``(player_id, season, position)``.
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

import config  # noqa: F401 — load .env via side effect
from db import get_client

SAVANT_OAA_URL = (
    "https://baseballsavant.mlb.com/leaderboard/"
    "outs_above_average?type=Fielder&year={season}&team=&range=year"
    "&min=1&pos={pos_code}&roles=&viz=hide&csv=true"
)

OAA_FIRST_SEASON = 2016
POSITION_CODES: tuple[int, ...] = (3, 4, 5, 6, 7, 8, 9)
POSITION_LABEL_BY_CODE: dict[int, str] = {
    3: "1B",
    4: "2B",
    5: "3B",
    6: "SS",
    7: "LF",
    8: "CF",
    9: "RF",
}

_REQUEST_TIMEOUT_SEC = 120
_DELAY_BETWEEN_REQUESTS_SEC = 3.0
_BATCH_SIZE = 500

_NAME_COL = "last_name, first_name"


def _format_player_name(raw: Any) -> str | None:
    """Turn ``Last, First`` into ``First Last``; pass through plain strings."""

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


def _to_optional_str(val: Any) -> str | None:
    if val is None:
        return None
    try:
        if isinstance(val, float) and pd.isna(val):  # type: ignore[union-attr]
            return None
        if pd.isna(val):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return s if s else None


def fetch_oaa_csv(season: int, pos_code: int) -> tuple[pd.DataFrame | None, str | None]:
    """
    GET one Savant CSV. Returns ``(dataframe, error_message)``;
    dataframe is ``None`` on failure or unreadable payload.
    """
    url = SAVANT_OAA_URL.format(season=season, pos_code=pos_code)
    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return None, f"HTTP/request error: {type(exc).__name__}: {exc}"

    raw = resp.text.strip()
    if not raw:
        return None, "empty response body"

    lead = raw.lstrip()
    if lead.startswith("<!DOCTYPE html") or lead.lower().startswith("<html"):
        return None, f"unexpected HTML ({len(raw)} chars)"

    try:
        df = pd.read_csv(io.StringIO(raw))
    except Exception as exc:  # noqa: BLE001
        return None, f"CSV parse error: {type(exc).__name__}: {exc}"

    return df, None


def dataframe_to_records(
    df: pd.DataFrame, *, season_hint: int, pos_code_fallback: int
) -> list[dict[str, Any]]:
    """Map Savant dataframe rows to Supabase ``statcast_fielding_oaa`` payloads."""

    if df.empty:
        return []

    missing = [c for c in (_NAME_COL, "player_id") if c not in df.columns]
    if missing:
        return []

    now_iso = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, Any]] = []
    for _, rr in df.iterrows():
        player_id_val = rr.get("player_id")
        pid = _to_optional_int(player_id_val)
        if pid is None:
            continue

        season_val = rr.get("year")
        season_i = _to_optional_int(season_val) if season_val is not None else None
        if season_i is None:
            season_i = season_hint

        pos_disp = _to_optional_str(rr.get("primary_pos_formatted"))
        if not pos_disp:
            pos_disp = POSITION_LABEL_BY_CODE[pos_code_fallback]

        rec: dict[str, Any] = {
            "player_id": pid,
            "player_name": _format_player_name(rr.get(_NAME_COL)),
            "season": season_i,
            "position": pos_disp,
            "team": _to_optional_str(rr.get("display_team_name")),
            "fielding_runs_prevented": _to_optional_int(rr.get("fielding_runs_prevented")),
            "oaa": _to_optional_int(rr.get("outs_above_average")),
            "oaa_infront": _to_optional_int(rr.get("outs_above_average_infront")),
            "oaa_lateral_3b": _to_optional_int(
                rr.get("outs_above_average_lateral_toward3bline")
            ),
            "oaa_lateral_1b": _to_optional_int(
                rr.get("outs_above_average_lateral_toward1bline")
            ),
            "oaa_behind": _to_optional_int(rr.get("outs_above_average_behind")),
            "oaa_rhh": _to_optional_int(rr.get("outs_above_average_rhh")),
            "oaa_lhh": _to_optional_int(rr.get("outs_above_average_lhh")),
            "updated_at": now_iso,
        }
        rows.append(rec)

    return rows


def upsert_fielding_oaa(
    rows: list[dict[str, Any]], *, client: Any | None = None
) -> tuple[int, int]:
    """Upsert batches; ``(rows_ok_count, rows_failed_count)``. """

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
            client.table("statcast_fielding_oaa").upsert(
                batch,
                on_conflict="player_id,season,position",
            ).execute()
            ok_count += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(
                f"seed_statcast_oaa: upsert batch {batch_no} failed: {exc}",
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
        default=OAA_FIRST_SEASON,
        help=f'First season inclusive (default: {OAA_FIRST_SEASON}).',
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

    skipped = [y for y in seasons_all if y < OAA_FIRST_SEASON]
    for y in skipped:
        print(
            f"[warn] seed_statcast_oaa: season {y} skipped "
            f"(positional OAA CSV has no qualifying rows before {OAA_FIRST_SEASON} on unified endpoint)",
            flush=True,
        )

    seasons = [y for y in seasons_all if y >= OAA_FIRST_SEASON]

    planned_requests = len(seasons) * len(POSITION_CODES)

    cumulative_ok_rows = 0
    cumulative_fail_rows = 0
    cumulative_fetch_failed = 0

    rq_index = 0
    for year in seasons:
        for code in POSITION_CODES:
            if rq_index > 0:
                time.sleep(_DELAY_BETWEEN_REQUESTS_SEC)
            rq_index += 1

            label = POSITION_LABEL_BY_CODE.get(code, str(code))

            df, err = fetch_oaa_csv(year, code)

            if err is not None:
                cumulative_fetch_failed += 1
                print(
                    f"seed_statcast_oaa: season={year} pos={code} ({label}) "
                    f"fetch FAILED — {err}",
                    flush=True,
                )
                continue

            if df.columns.size == 0 or len(df) == 0:
                print(
                    f"seed_statcast_oaa: season={year} pos={code} ({label}) "
                    f"fetched cols={len(df.columns)} rows=0 — nothing to upsert",
                    flush=True,
                )
                continue

            if _NAME_COL not in df.columns or "player_id" not in df.columns:
                print(
                    f"seed_statcast_oaa: season={year} pos={code} ({label}) "
                    f"missing player id columns; columns={list(df.columns)} — skip",
                    flush=True,
                )
                continue

            records = dataframe_to_records(df, season_hint=year, pos_code_fallback=code)
            ok_now, failed_now = upsert_fielding_oaa(records, client=client)
            cumulative_ok_rows += ok_now
            cumulative_fail_rows += failed_now

            status = f"season={year} pos={code} ({label}) "
            status += (
                f"rows_in_csv={len(df)} upsert_ok={ok_now} upsert_failed={failed_now}"
            )
            print(f"seed_statcast_oaa: {status}", flush=True)

    print(
        f"seed_statcast_oaa: done — seasons_scanned={len(seasons)} "
        f"requests_successful={planned_requests - cumulative_fetch_failed} "
        f"requests_failed={cumulative_fetch_failed} "
        f"rows_upserted_ok={cumulative_ok_rows} "
        f"rows_upsert_failed={cumulative_fail_rows}",
        flush=True,
    )


if __name__ == "__main__":
    main()
