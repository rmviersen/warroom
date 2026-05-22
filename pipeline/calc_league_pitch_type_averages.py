"""
Compute league mean velo, spin, and movement by ``(season, pitch_type, p_throws)``
from ``statcast_pitches`` and upsert into ``league_pitch_type_averages``.

Those rows feed ``calculations.pitching_calcs.calc_stuff_plus()`` during pitcher
arsenal aggregation (pitch-type and handedness-specific league baselines).
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd

import config  # noqa: F401 — loads pipeline/.env before db access
from db import get_client

_DEFAULT_START_SEASON = 2015
_PAGE_SIZE = 1_000
_UPSERT_BATCH = 100

_STATCAST_SELECT = (
    "game_date,pitch_type,p_throws,release_speed,release_spin_rate,pfx_x,pfx_z"
)

PITCH_TYPE_TO_CATEGORY: dict[str, str] = {
    "FF": "Fastball",
    "SI": "Fastball",
    "FC": "Fastball",
    "FA": "Fastball",
    "SL": "Breaking",
    "ST": "Breaking",
    "SV": "Breaking",
    "CU": "Breaking",
    "KC": "Breaking",
    "CS": "Breaking",
    "CH": "Offspeed",
    "FS": "Offspeed",
    "FO": "Offspeed",
    "KN": "Knuckleball",
    "EP": "Other",
    "SC": "Other",
    "FT": "Other",
}

EXCLUDED_PITCH_TYPES: frozenset[str] = frozenset({"IN", "PO", "UN", "AB"})

_ALLOWED_P_THROWS: frozenset[str] = frozenset({"L", "R"})


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Aggregate statcast_pitches into league_pitch_type_averages by "
            "season and pitch_type."
        ),
    )
    p.add_argument(
        "--start-season",
        type=int,
        default=_DEFAULT_START_SEASON,
        help=f"First season (default {_DEFAULT_START_SEASON}).",
    )
    p.add_argument(
        "--end-season",
        type=int,
        default=datetime.now().year,
        help="Last season (default: current calendar year).",
    )
    return p.parse_args()


def _load_season_pitches(client: Any, year: int) -> pd.DataFrame:
    """Paginated read of ``statcast_pitches`` for ``year`` (calendar bounds)."""
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        q = (
            client.table("statcast_pitches")
            .select(_STATCAST_SELECT)
            .gte("game_date", start)
            .lte("game_date", end)
            .range(offset, offset + _PAGE_SIZE - 1)
            .limit(_PAGE_SIZE)
        )
        res = q.execute()
        page = res.data or []
        if not page:
            break
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return pd.DataFrame(rows)


def _num_for_db(val: Any, *, ndigits: int = 4) -> float | None:
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except TypeError:
        pass
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(x):
        return None
    return round(x, ndigits)


def _normalize_p_throws(val: Any) -> str | None:
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except TypeError:
        pass
    s = str(val).strip().upper()
    return s if s in _ALLOWED_P_THROWS else None


def _filter_pitch_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df[df["pitch_type"].notna()].copy()
    if out.empty:
        return out
    pt = out["pitch_type"].astype(str).str.strip()
    out = out.loc[~pt.isin(EXCLUDED_PITCH_TYPES)].copy()
    out["pitch_type"] = out["pitch_type"].astype(str).str.strip()
    out["p_throws"] = out["p_throws"].map(_normalize_p_throws)
    out = out[out["p_throws"].notna()].copy()
    return out


def aggregate_season(df: pd.DataFrame, season: int) -> list[dict[str, Any]]:
    """One output row per distinct ``(pitch_type, p_throws)`` in ``df``."""
    df = _filter_pitch_rows(df)
    if df.empty:
        return []

    now = datetime.now(timezone.utc).isoformat()
    grouped = df.groupby(["pitch_type", "p_throws"], sort=True)
    counts = grouped.size()
    avgs = grouped[["release_speed", "release_spin_rate", "pfx_x", "pfx_z"]].mean()

    records: list[dict[str, Any]] = []
    for idx in counts.index:
        pt_key, throws_key = idx
        pt_str = str(pt_key)
        ph_str = str(throws_key)
        row = avgs.loc[idx]
        cat = PITCH_TYPE_TO_CATEGORY.get(pt_str, "Other")
        records.append(
            {
                "season": season,
                "pitch_type": pt_str,
                "p_throws": ph_str,
                "pitch_category": cat,
                "pitch_count": int(counts.loc[idx]),
                "avg_velo": _num_for_db(row.get("release_speed")),
                "avg_spin_rate": _num_for_db(row.get("release_spin_rate")),
                "avg_h_movement": _num_for_db(row.get("pfx_x")),
                "avg_v_movement": _num_for_db(row.get("pfx_z")),
                "updated_at": now,
            }
        )
    return records


def upsert_batches(
    client: Any, rows: list[dict[str, Any]]
) -> tuple[int, int]:
    """Returns ``(ok_rows, failed_rows)``."""
    ok = 0
    failed = 0
    n_batches = (len(rows) + _UPSERT_BATCH - 1) // _UPSERT_BATCH if rows else 0
    for i in range(0, len(rows), _UPSERT_BATCH):
        batch = rows[i : i + _UPSERT_BATCH]
        batch_no = i // _UPSERT_BATCH + 1
        try:
            client.table("league_pitch_type_averages").upsert(
                batch,
                on_conflict="season,pitch_type,p_throws",
            ).execute()
            ok += len(batch)
            print(
                f"calc_league_pitch_type_averages: batch {batch_no}/{n_batches}: "
                f"success {len(batch)} row(s)",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            failed += len(batch)
            print(
                f"calc_league_pitch_type_averages: batch {batch_no}/{n_batches}: "
                f"failure {len(batch)} row(s) — {exc}",
                flush=True,
            )
    return ok, failed


def run_season(client: Any, year: int) -> tuple[int, int, int, int]:
    """
    Returns ``(pitch_type_hand_combos, total_pitches, ok_rows, failed_rows)``.
    """
    print(
        f"calc_league_pitch_type_averages: loading statcast_pitches for {year}…",
        flush=True,
    )
    raw = _load_season_pitches(client, year)
    filtered = _filter_pitch_rows(raw)
    print(
        f"calc_league_pitch_type_averages: {len(raw)} row(s) loaded, "
        f"{len(filtered)} after pitch_type and p_throws filters; aggregating…",
        flush=True,
    )
    records = aggregate_season(raw, year)
    n_types = len(records)
    total_pitches = int(len(filtered))

    ok, failed = upsert_batches(client, records)
    return n_types, total_pitches, ok, failed


def main() -> None:
    args = _parse_args()
    start_s = int(args.start_season)
    end_s = int(args.end_season)
    if start_s > end_s:
        raise SystemExit(
            "[calc_league_pitch_type_averages] --start-season must be <= --end-season."
        )

    client = get_client()
    total_types_processed = 0
    total_fail_rows = 0

    for year in range(start_s, end_s + 1):
        n_types, total_pitches, ok, fail_r = run_season(client, year)
        total_types_processed += ok
        total_fail_rows += fail_r
        print(
            f"calc_league_pitch_type_averages: season {year} summary — "
            f"pitch_type_hand_combos={n_types}, total_pitches={total_pitches}, "
            f"ok_rows={ok}, failed_rows={fail_r}",
            flush=True,
        )

    print(
        f"calc_league_pitch_type_averages: final summary — "
        f"total_pitch_types_across_all_seasons={total_types_processed}, "
        f"total_failures={total_fail_rows}",
        flush=True,
    )


if __name__ == "__main__":
    main()
