"""
Statcast ETL: pull daily pitch-level data via pybaseball and load into Supabase.

Target table columns match ``statcast_pitches`` in SCHEMA.md (warroom/SCHEMA.md).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
import pybaseball.cache as pb_cache
from pybaseball import statcast
from zoneinfo import ZoneInfo

import db

# ---------------------------------------------------------------------------
# pybaseball disk cache — speeds retries if Savant requests are interrupted
# ---------------------------------------------------------------------------
pb_cache.enable()

EASTERN = ZoneInfo("America/New_York")

# Subset of Savant columns we persist; must align with statcast_pitches in SCHEMA.md.
_KEEP_COLUMNS = [
    "player_name",
    "batter",
    "pitcher",
    "game_date",
    "game_pk",
    "pitch_type",
    "pitch_name",
    "release_speed",
    "release_spin_rate",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "launch_angle",
    "launch_speed",
    "hit_distance_sc",
    "events",
    "description",
    "zone",
    "stand",
    "p_throws",
    "home_team",
    "away_team",
]

# Columns allowed on insert (pitcher is dropped — not in schema).
_TABLE_COLUMNS = [
    "player_id",
    "player_name",
    "team_id",
    "game_date",
    "game_pk",
    "pitch_type",
    "pitch_name",
    "release_speed",
    "release_spin_rate",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "launch_angle",
    "launch_speed",
    "hit_distance",
    "events",
    "description",
    "zone",
    "stand",
    "p_throws",
    "home_team",
    "away_team",
]

_INSERT_BATCH_SIZE = 500


def fetch_statcast_for_date(date_str: str) -> pd.DataFrame:
    """
    Pull Statcast for a single calendar day.

    ``date_str`` must be ``YYYY-MM-DD`` (ISO). Uses ``pybaseball.statcast`` with
    ``start_dt`` and ``end_dt`` equal to that date.
    """

    day = date_str.strip()
    datetime.strptime(day, "%Y-%m-%d")
    return statcast(start_dt=day, end_dt=day, verbose=False, parallel=True)


def fetch_todays_statcast() -> pd.DataFrame:
    """
    Pull Statcast for "today" in America/New_York as YYYY-MM-DD.

    Delegates to :func:`fetch_statcast_for_date`.
    """

    today = datetime.now(EASTERN).date().isoformat()
    return fetch_statcast_for_date(today)


def clean_statcast(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize a raw Statcast dataframe for loading.

    - Drops rows with missing ``player_name``
    - Keeps only columns in ``_KEEP_COLUMNS`` that exist on the frame
    - Renames ``hit_distance_sc`` -> ``hit_distance`` (SCHEMA name)
    - Uses None instead of NaN for JSON/PostgREST compatibility
    """

    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    if "player_name" in out.columns:
        out = out[out["player_name"].notna() & (out["player_name"] != "")]

    present = [c for c in _KEEP_COLUMNS if c in out.columns]
    out = out[present]

    if "hit_distance_sc" in out.columns:
        out = out.rename(columns={"hit_distance_sc": "hit_distance"})

    # Replace NaN / NA with None for serialization
    out = out.replace({np.nan: None})
    out = out.astype(object).where(pd.notnull(out), None)

    return out


def _json_safe_value(value: Any) -> Any:
    """Coerce numpy/pandas scalars and NaN-like values to JSON-friendly Python."""

    if value is None:
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except (ValueError, TypeError):
            return value
    return value


def _rows_from_dataframe(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Build insert rows: map batter -> player_id, drop pitcher, schema-only keys."""

    raw_records = df.to_dict(orient="records")
    rows: list[dict[str, Any]] = []

    for raw in raw_records:
        rec = dict(raw)
        if "batter" in rec:
            rec["player_id"] = rec.pop("batter")
        # Not persisted — schema has no pitcher column on statcast_pitches.
        rec.pop("pitcher", None)

        row = {col: _json_safe_value(rec.get(col)) for col in _TABLE_COLUMNS}
        rows.append(row)

    return rows


def upsert_statcast(df: pd.DataFrame) -> None:
    """
    Load cleaned Statcast rows into ``statcast_pitches`` via batched upsert.

    Prints aggregate success and failure row counts (failures count full batch
    size when a batch raises).
    """

    if df is None or df.empty:
        print("upsert_statcast: no rows to load.")
        return

    client = db.get_client()
    records = _rows_from_dataframe(df)
    table = client.table("statcast_pitches")

    ok = 0
    failed = 0
    for i in range(0, len(records), _INSERT_BATCH_SIZE):
        batch = records[i : i + _INSERT_BATCH_SIZE]
        batch_no = i // _INSERT_BATCH_SIZE + 1
        try:
            table.upsert(batch).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"upsert_statcast: batch {batch_no} failed: {exc}")
            failed += len(batch)

    print(f"upsert_statcast: upserted {ok} row(s); failed {failed} row(s).")


def run_pipeline_for_date(date_str: str) -> int:
    """Fetch, clean, and load Statcast data for ``date_str`` (``YYYY-MM-DD``).

    Returns the number of cleaned rows passed to upsert (0 if none).
    """

    day = date_str.strip()
    print(f"[statcast] pipeline start (date={day})")
    df = fetch_statcast_for_date(day)
    print(f"[statcast] raw rows: {len(df)}")

    cleaned = clean_statcast(df)
    print(f"[statcast] cleaned rows: {len(cleaned)}")

    upsert_statcast(cleaned)
    print("[statcast] pipeline finished")
    return len(cleaned)


def run_pipeline() -> None:
    """Fetch, clean, and load today's Statcast data (Eastern calendar date)."""

    run_pipeline_for_date(datetime.now(EASTERN).date().isoformat())


if __name__ == "__main__":
    run_pipeline()