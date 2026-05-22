"""
Aggregate ``statcast_pitches`` into ``statcast_pitching_arsenal`` (per pitch type)
and ``statcast_pitching`` (per pitcher-season rollup) via RPC upserts.

NOTE: ``stuff_plus_pitch`` (``statcast_pitching_arsenal``) and ``stuff_plus``
(``statcast_pitching``) are **not** written here; they are owned by
``calc_pitching_metrics.py``. All other rollup / arsenal fields produced by this
aggregation are written via RPC upserts.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime
from typing import Any

import pandas as pd

import config  # noqa: F401 — loads pipeline/.env before db access
from db import get_client

_DEFAULT_START_SEASON = 2015
_PAGE_SIZE = 1_000
_RPC_BATCH = 500

FASTBALL_TYPES: frozenset[str] = frozenset({"FF", "SI", "FC", "FA"})

EXCLUDED_PITCH_TYPES: frozenset[str] = frozenset({"IN", "PO", "UN", "AB"})

_ALLOWED_P_THROWS: frozenset[str] = frozenset({"L", "R"})

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

SWING_DESCRIPTIONS: frozenset[str] = frozenset(
    {
        "swinging_strike",
        "swinging_strike_blocked",
        "foul",
        "foul_tip",
        "hit_into_play",
        "hit_into_play_no_out",
        "hit_into_play_score",
    }
)

WHIFF_DESCRIPTIONS: frozenset[str] = frozenset(
    {"swinging_strike", "swinging_strike_blocked"}
)

OUTSIDE_ZONE_CODES: frozenset[int] = frozenset({11, 12, 13, 14})

_STATCAST_SELECT = (
    "pitcher_id,pitcher_name,pitch_type,p_throws,release_speed,release_spin_rate,"
    "pfx_x,pfx_z,description,zone,game_date"
)


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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Aggregate Statcast pitches into statcast_pitching_arsenal and "
            "statcast_pitching."
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


def _filter_pitch_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df[df["pitcher_id"].notna() & df["pitch_type"].notna()].copy()
    if out.empty:
        return out
    pt = out["pitch_type"].astype(str).str.strip()
    out = out.loc[~pt.isin(EXCLUDED_PITCH_TYPES)].copy()
    out["pitch_type"] = out["pitch_type"].astype(str).str.strip()
    out["pitcher_id"] = pd.to_numeric(out["pitcher_id"], errors="coerce")
    out = out[out["pitcher_id"].notna()]
    out["p_throws"] = out["p_throws"].map(_normalize_p_throws)
    out = out[out["p_throws"].notna()].copy()
    return out


def _zone_int(z: Any) -> int | None:
    if z is None:
        return None
    try:
        if pd.isna(z):
            return None
    except TypeError:
        pass
    try:
        return int(round(float(z)))
    except (TypeError, ValueError):
        return None


def _mean_round(val: Any, *, ndigits: int = 4) -> float | None:
    if val is None:
        return None
    try:
        if isinstance(val, float) and math.isnan(val):
            return None
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


def _pitcher_mode_names(df: pd.DataFrame) -> dict[int, str | None]:
    names: dict[int, str | None] = {}
    for pid, sub in df.groupby("pitcher_id"):
        pid_i = int(pid)
        col = sub["pitcher_name"].dropna()
        if col.empty:
            names[pid_i] = None
            continue
        mode = col.astype(str).mode()
        names[pid_i] = str(mode.iloc[0]) if len(mode) else str(col.iloc[0])
    return names


def _pitcher_mode_throws(df: pd.DataFrame) -> dict[int, str | None]:
    throws: dict[int, str | None] = {}
    for pid, sub in df.groupby("pitcher_id"):
        pid_i = int(pid)
        col = sub["p_throws"].dropna()
        if col.empty:
            throws[pid_i] = None
            continue
        mode = col.astype(str).mode()
        throws[pid_i] = str(mode.iloc[0]) if len(mode) else str(col.iloc[0])
    return throws


def build_arsenal_records(
    df: pd.DataFrame,
    season: int,
) -> list[dict[str, Any]]:
    if df.empty:
        return []
    pitcher_totals = df.groupby("pitcher_id").size()
    mode_names = _pitcher_mode_names(df)
    mode_throws = _pitcher_mode_throws(df)

    records: list[dict[str, Any]] = []
    for (pid, ptype), sub in df.groupby(["pitcher_id", "pitch_type"], sort=True):
        pid_i = int(pid)
        ptype_s = str(ptype)
        n = int(len(sub))
        total_p = int(pitcher_totals.loc[pid_i])
        usage = round(100.0 * n / total_p, 4) if total_p > 0 else None

        desc = sub["description"].astype(str).str.strip()
        whiff_n = int(desc.isin(WHIFF_DESCRIPTIONS).sum())
        whiff_rate = round(100.0 * whiff_n / n, 4) if n > 0 else None

        zi = sub["zone"].map(_zone_int)
        outside = sub[zi.isin(OUTSIDE_ZONE_CODES)]
        if len(outside) == 0:
            chase_rate = None
        else:
            od = outside["description"].astype(str).str.strip()
            chase_rate = round(
                100.0 * od.isin(SWING_DESCRIPTIONS).sum() / len(outside),
                4,
            )

        pthr = mode_throws.get(pid_i)

        records.append(
            {
                "pitcher_id": pid_i,
                "pitcher_name": mode_names.get(pid_i),
                "season": season,
                "p_throws": pthr,
                "pitch_type": ptype_s,
                "pitch_category": PITCH_TYPE_TO_CATEGORY.get(ptype_s, "Other"),
                "pitches": n,
                "usage_rate": usage,
                "avg_velo": _mean_round(sub["release_speed"].mean()),
                "avg_spin_rate": _mean_round(sub["release_spin_rate"].mean()),
                "avg_h_movement": _mean_round(sub["pfx_x"].mean()),
                "avg_v_movement": _mean_round(sub["pfx_z"].mean()),
                "whiff_rate": whiff_rate,
                "chase_rate": chase_rate,
            }
        )
    return records


def _weighted_mean(
    pairs: list[tuple[float | None, int]],
) -> float | None:
    num = 0.0
    den = 0.0
    for val, w in pairs:
        if val is None or w <= 0:
            continue
        num += float(val) * w
        den += float(w)
    if den == 0:
        return None
    return round(num / den, 4)


def build_rollup_records(
    arsenal: list[dict[str, Any]],
    filtered: pd.DataFrame,
    season: int,
) -> list[dict[str, Any]]:
    if not arsenal:
        return []
    by_pid: dict[int, list[dict[str, Any]]] = {}
    for r in arsenal:
        pid = int(r["pitcher_id"])
        by_pid.setdefault(pid, []).append(r)

    rollups: list[dict[str, Any]] = []
    for pid, rows in by_pid.items():
        name = rows[0].get("pitcher_name")
        total_p = sum(int(r["pitches"]) for r in rows)

        fb_pairs = [
            (r.get("avg_velo"), int(r["pitches"]))
            for r in rows
            if r["pitch_type"] in FASTBALL_TYPES
        ]
        avg_fb_velo = _weighted_mean(fb_pairs)

        sub_raw = filtered[pd.to_numeric(filtered["pitcher_id"], errors="coerce") == pid]
        rs = pd.to_numeric(sub_raw["release_speed"], errors="coerce")
        mx = rs.max()
        max_velo = _mean_round(mx) if mx is not None and not pd.isna(mx) else None

        whiff_pairs = [(r.get("whiff_rate"), int(r["pitches"])) for r in rows]
        whiff_roll = _weighted_mean(whiff_pairs)

        chase_pairs = [
            (r.get("chase_rate"), int(r["pitches"]))
            for r in rows
            if r.get("chase_rate") is not None
        ]
        chase_roll = _weighted_mean(chase_pairs)

        rollups.append(
            {
                "pitcher_id": pid,
                "pitcher_name": name,
                "season": season,
                "pitches": total_p,
                "avg_fastball_velo": avg_fb_velo,
                "max_velo": max_velo,
                "whiff_rate": whiff_roll,
                "chase_rate": chase_roll,
            }
        )
    return rollups


def _rpc_batches(
    client: Any,
    rpc_name: str,
    rows: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Returns ``(ok_rows, failed_rows, failed_batches)``."""
    ok = 0
    failed_rows = 0
    failed_batches = 0
    n_batches = (len(rows) + _RPC_BATCH - 1) // _RPC_BATCH if rows else 0
    label = "aggregate_statcast_pitching"
    for i in range(0, len(rows), _RPC_BATCH):
        batch = rows[i : i + _RPC_BATCH]
        batch_no = i // _RPC_BATCH + 1
        try:
            client.rpc(rpc_name, {"rows": batch}).execute()
            ok += len(batch)
            print(
                f"{label}: {rpc_name} batch {batch_no}/{n_batches}: "
                f"success {len(batch)} row(s)",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            failed_rows += len(batch)
            failed_batches += 1
            print(
                f"{label}: {rpc_name} batch {batch_no}/{n_batches}: "
                f"failure {len(batch)} row(s) — {exc}",
                flush=True,
            )
    return ok, failed_rows, failed_batches


def run_season(
    client: Any,
    year: int,
) -> tuple[int, int, int, int, int, int, int]:
    """
    Returns
    ``(pitchers, arsenal_ok, arsenal_fail_rows, arsenal_fail_batches,
    rollup_ok, rollup_fail_rows, rollup_fail_batches)``.
    """
    print(
        f"aggregate_statcast_pitching: loading statcast_pitches for {year}…",
        flush=True,
    )
    raw = _load_season_pitches(client, year)
    df = _filter_pitch_df(raw)
    print(
        f"aggregate_statcast_pitching: {len(raw)} row(s) loaded, "
        f"{len(df)} after filters; aggregating…",
        flush=True,
    )
    arsenal_recs = build_arsenal_records(df, year)
    rollup_recs = build_rollup_records(arsenal_recs, df, year)

    pitchers = len({int(r["pitcher_id"]) for r in arsenal_recs}) if arsenal_recs else 0

    a_ok, a_fail, a_fb = _rpc_batches(
        client, "upsert_statcast_pitching_arsenal", arsenal_recs
    )
    r_ok, r_fail, r_fb = _rpc_batches(
        client, "upsert_statcast_pitching_aggregates", rollup_recs
    )
    return pitchers, a_ok, a_fail, a_fb, r_ok, r_fail, r_fb


def main() -> None:
    args = _parse_args()
    start_s = int(args.start_season)
    end_s = int(args.end_season)
    if start_s > end_s:
        raise SystemExit(
            "[aggregate_statcast_pitching] --start-season must be <= --end-season."
        )

    client = get_client()

    total_pitchers = 0
    total_fail_rows = 0
    total_fail_batches = 0

    for year in range(start_s, end_s + 1):
        (
            pitchers,
            a_ok,
            a_fail,
            a_fb,
            r_ok,
            r_fail,
            r_fb,
        ) = run_season(client, year)
        total_pitchers += pitchers
        total_fail_rows += a_fail + r_fail
        total_fail_batches += a_fb + r_fb
        print(
            f"aggregate_statcast_pitching: season {year} summary — "
            f"pitchers={pitchers}, arsenal_rows_written={a_ok}, "
            f"rollup_rows_written={r_ok}, "
            f"failed_batches_arsenal={a_fb}, failed_batches_rollup={r_fb}",
            flush=True,
        )

    print(
        f"aggregate_statcast_pitching: final summary — "
        f"total_pitchers_across_seasons={total_pitchers}, "
        f"total_failed_rows={total_fail_rows}, "
        f"total_failed_batches={total_fail_batches}",
        flush=True,
    )


if __name__ == "__main__":
    main()
