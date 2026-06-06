"""
Recompute Stuff+ metrics on pitching warehouse tables using the trained KNN model bundle.

Writes ``stuff_plus_pitch`` via ``upsert_statcast_pitching_arsenal`` and the
pitcher-level ``stuff_plus`` via ``upsert_statcast_pitching_aggregates``.

Model (v2)
----------
Three-family KNN bundle trained by ``train_stuff_plus_model.py`` and stored at
``pipeline/models/stuff_plus_model.pkl``.  Run the training script first if
the model file is missing or if you want to retrain on updated data.

Scoring
-------
For each arsenal row the appropriate family model is selected, features are
built (with arm-side movement transform and fastball-differential features
for breaking / off-speed pitches), and two KNN predictions are made:

  csw_score     = (predicted_csw_rate  / csw_league_mean)      * 100
  contact_score = (contact_league_mean / predicted_contact_woba) * 100  (inverted)
  stuff_plus    = (csw_score + contact_score) / 2

A pitcher scoring 115 has pitches that the model predicts will generate
15 % more called-strikes+whiffs than league average AND / OR suppress
contact quality 15 % below league average.
"""

from __future__ import annotations

import argparse
import math
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

import config  # noqa: F401 — loads pipeline/.env before db access
from db import get_client
from train_stuff_plus_model import PITCH_FAMILY_MAP, build_fb_maps
from weighted_knn import WeightedKNNRegressor  # noqa: F401 — needed so pickle can resolve the class

_DEFAULT_START_SEASON = 2015
_PAGE_SIZE = 1_000
_RPC_BATCH = 500
_MODEL_PATH = Path(__file__).parent / "models" / "stuff_plus_model.pkl"

_ALLOWED_P_THROWS: frozenset[str] = frozenset({"L", "R"})

STUFF_PLUS_ELIGIBLE: frozenset[str] = frozenset(
    {"FF", "SI", "FC", "FA", "SL", "ST", "SV", "CU", "KC", "CS", "CH", "FS", "FO", "KN"}
)

PITCH_TYPE_TO_CATEGORY: dict[str, str] = {
    "FF": "Fastball", "SI": "Fastball", "FC": "Fastball", "FA": "Fastball",
    "SL": "Breaking", "ST": "Breaking", "SV": "Breaking",
    "CU": "Breaking", "KC": "Breaking", "CS": "Breaking",
    "CH": "Offspeed", "FS": "Offspeed", "FO": "Offspeed",
    "KN": "Knuckleball", "EP": "Other", "SC": "Other", "FT": "Other",
}

# New feature columns needed for KNN scoring
_ARSENAL_SELECT = (
    "pitcher_id,season,pitch_type,p_throws,"
    "avg_effective_speed,avg_spin_rate,avg_spin_axis,"
    "avg_h_movement,avg_v_movement,pitches"
)

_FASTBALL_TYPES: frozenset[str] = frozenset({"FF", "SI", "FC", "FA"})


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def load_model() -> dict[str, Any]:
    """Load the trained Stuff+ model bundle from disk."""
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Stuff+ model bundle not found at {_MODEL_PATH}. "
            "Run `python train_stuff_plus_model.py` first."
        )
    with open(_MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)
    version = bundle.get("version", "1.x")
    if version != "2.1":
        raise RuntimeError(
            f"Model bundle version {version!r} is incompatible with this scorer "
            "(expected '2.1'). Re-run train_stuff_plus_model.py to generate a v2.1 bundle."
        )
    families = [k for k in bundle if k != "version"]
    print(
        f"calc_pitching_metrics: loaded Stuff+ model bundle v{version} "
        f"from {_MODEL_PATH}  families={families}",
        flush=True,
    )
    return bundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_p_throws(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip().upper()
    return s if s in _ALLOWED_P_THROWS else None


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Recompute Stuff+ on statcast_pitching_arsenal and "
            "statcast_pitching.stuff_plus using the trained KNN model bundle."
        ),
    )
    p.add_argument(
        "--start-season", type=int, default=_DEFAULT_START_SEASON,
        help=f"First season (default {_DEFAULT_START_SEASON}).",
    )
    p.add_argument(
        "--end-season", type=int, default=datetime.now().year,
        help="Last season (default: current calendar year).",
    )
    return p.parse_args()


def _to_float_optional(val: Any) -> float | None:
    if val is None:
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _to_int_optional(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _weighted_mean(pairs: list[tuple[float | None, int]]) -> float | None:
    num = 0.0
    den = 0.0
    for val, w in pairs:
        if val is None or w <= 0:
            continue
        num += float(val) * float(w)
        den += float(w)
    return round(num / den, 4) if den > 0 else None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_statcast_pitching_arsenal_season(
    client: Any,
    season: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        try:
            res = (
                client.table("statcast_pitching_arsenal")
                .select(_ARSENAL_SELECT)
                .eq("season", season)
                .order("pitcher_id")
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_pitching_metrics: arsenal page offset={offset} "
                f"season={season} failed: {exc}",
                flush=True,
            )
            break
        page = res.data or []
        if not page:
            break
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


# ---------------------------------------------------------------------------
# Core: build features → KNN scoring → payloads
# ---------------------------------------------------------------------------

def _build_payloads_and_rollup(
    loaded: list[dict[str, Any]],
    season: int,
    bundle: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """
    Apply the KNN model bundle to each arsenal row to produce stuff_plus_pitch,
    then build arsenal + rollup upsert payloads.

    Scoring:
      csw_score     = (knn_predicted_csw     / csw_league_mean)      × 100
      contact_score = (contact_league_mean   / knn_predicted_contact) × 100
      stuff_plus    = (csw_score + contact_score) / 2

    Returns (arsenal_payloads, rollup_payloads, n_skipped).
    """
    # Build fastball reference maps for differential features (breaking/offspeed)
    fb_eff_map, fb_v_map = build_fb_maps(loaded)

    arsenal_payloads: list[dict[str, Any]] = []
    rollup_bins:      dict[int, list[tuple[float, int]]] = {}
    skipped = 0

    for row in loaded:
        pid = row.get("pitcher_id")
        pt  = row.get("pitch_type")
        if pid is None or pt is None:
            skipped += 1
            continue
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            skipped += 1
            continue

        ptype_s = str(pt).strip()
        if ptype_s not in STUFF_PLUS_ELIGIBLE:
            skipped += 1
            continue

        family = PITCH_FAMILY_MAP.get(ptype_s)
        if not family or family not in bundle:
            skipped += 1
            continue

        fb     = bundle[family]
        pthr   = _normalize_p_throws(row.get("p_throws"))
        n_p    = _to_int_optional(row.get("pitches"))

        if pthr is None or not n_p or n_p <= 0:
            skipped += 1
            continue

        # Core features
        eff_speed = _to_float_optional(row.get("avg_effective_speed"))
        spin_rate = _to_float_optional(row.get("avg_spin_rate"))
        spin_axis = _to_float_optional(row.get("avg_spin_axis"))
        h_mov     = _to_float_optional(row.get("avg_h_movement"))
        v_mov     = _to_float_optional(row.get("avg_v_movement"))

        if any(v is None for v in (eff_speed, spin_rate, spin_axis, h_mov, v_mov)):
            skipped += 1
            continue

        # arm_side: positive = arm-side run, negative = glove-side run
        arm_side = -h_mov if pthr == "R" else h_mov  # type: ignore[operator]

        feat: list[float] = [
            eff_speed,  # type: ignore[list-item]
            spin_rate,  # type: ignore[list-item]
            spin_axis,  # type: ignore[list-item]
            arm_side,
            v_mov,      # type: ignore[list-item]
        ]

        if family != "fastball":
            key          = (pid_i, pthr)
            fb_es        = fb_eff_map.get(key)
            fb_vz        = fb_v_map.get(key)
            velo_diff    = (fb_es - eff_speed) if fb_es is not None else 0.0  # type: ignore[operator]
            v_break_diff = (fb_vz - v_mov)     if fb_vz is not None else 0.0  # type: ignore[operator]
            feat.extend([velo_diff, v_break_diff])

        # KNN predictions (single-row inference)
        X = fb["scaler"].transform([feat])
        raw_csw     = float(fb["csw_knn"].predict(X)[0])
        raw_contact = float(fb["contact_knn"].predict(X)[0])

        csw_league = fb["csw_league_mean"]
        con_league = fb["contact_league_mean"]

        csw_score     = (raw_csw   / max(csw_league, 1e-6)) * 100.0
        contact_score = min((max(con_league, 0.01) / max(raw_contact, 0.01)) * 100.0, 200.0)
        stuff_rounded = round(csw_score * 0.75 + contact_score * 0.25, 4)

        arsenal_payloads.append({
            "pitcher_id":     pid_i,
            "season":         int(season),
            "pitch_type":     ptype_s,
            "pitch_category": PITCH_TYPE_TO_CATEGORY.get(ptype_s, "Other"),
            "p_throws":       pthr,
            "stuff_plus_pitch": stuff_rounded,
        })

        rollup_bins.setdefault(pid_i, []).append((stuff_rounded, n_p))

    rollup_payloads: list[dict[str, Any]] = []
    for rid, pairs in rollup_bins.items():
        wmean = _weighted_mean(pairs)  # type: ignore[arg-type]
        if wmean is None:
            continue
        rollup_payloads.append({
            "pitcher_id": rid,
            "season":     int(season),
            "stuff_plus": wmean,
        })

    print(
        f"calc_pitching_metrics: season {season} — "
        f"rows_scored={len(arsenal_payloads)}  skipped={skipped}",
        flush=True,
    )
    return arsenal_payloads, rollup_payloads, skipped


# ---------------------------------------------------------------------------
# Upsert batches
# ---------------------------------------------------------------------------

def _upsert_batches(
    client: Any,
    rpc_name: str,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    ok = 0
    failed_rows = 0
    n_batches = (len(rows) + _RPC_BATCH - 1) // _RPC_BATCH if rows else 0
    for i in range(0, len(rows), _RPC_BATCH):
        batch    = rows[i: i + _RPC_BATCH]
        batch_no = i // _RPC_BATCH + 1
        try:
            client.rpc(rpc_name, {"rows": batch}).execute()
            ok += len(batch)
            print(
                f"calc_pitching_metrics: {rpc_name} batch {batch_no}/{n_batches}: "
                f"success {len(batch)} row(s)",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            failed_rows += len(batch)
            print(
                f"calc_pitching_metrics: {rpc_name} batch {batch_no}/{n_batches}: "
                f"failure {len(batch)} row(s) — {exc}",
                flush=True,
            )
    return ok, failed_rows


def _sync_stuff_plus_to_pps(client: Any, season: int) -> int:
    """Bulk-copy statcast_pitching.stuff_plus → player_pitching_seasons.stuff_plus."""
    try:
        res  = client.rpc("sync_pitcher_stuff_plus", {"p_season": season}).execute()
        data = res.data
        if isinstance(data, list) and data:
            return int(data[0])
        if isinstance(data, (int, float)):
            return int(data)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(
            f"calc_pitching_metrics: sync_pitcher_stuff_plus season={season} failed: {exc}",
            flush=True,
        )
        return 0


# ---------------------------------------------------------------------------
# Season runner
# ---------------------------------------------------------------------------

def run_season(
    client: Any,
    season: int,
    bundle: dict[str, Any],
) -> tuple[int, int, int, int, int, int]:
    """Returns (arsenal_read, arsenal_ok, rollup_ok, total_fail_rows, skipped, pps_synced)."""
    arsenal_rows = _load_statcast_pitching_arsenal_season(client, season)
    arsenal_read = len(arsenal_rows)

    arsenal_payloads, rollup_payloads, skipped = _build_payloads_and_rollup(
        arsenal_rows, season, bundle
    )

    a_ok, a_fail = _upsert_batches(
        client, "upsert_statcast_pitching_arsenal", arsenal_payloads
    )
    r_ok, r_fail = _upsert_batches(
        client, "upsert_statcast_pitching_aggregates", rollup_payloads
    )

    pps_synced = _sync_stuff_plus_to_pps(client, season)
    print(
        f"calc_pitching_metrics: synced stuff_plus to player_pitching_seasons: "
        f"{pps_synced} row(s) for season {season}",
        flush=True,
    )

    return arsenal_read, a_ok, r_ok, a_fail + r_fail, skipped, pps_synced


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args    = _parse_args()
    start_s = int(args.start_season)
    end_s   = int(args.end_season)
    if start_s > end_s:
        raise SystemExit("[calc_pitching_metrics] --start-season must be <= --end-season.")

    bundle = load_model()
    client = get_client()

    grand_a_ok = grand_r_ok = grand_fail = grand_pps = 0

    for season in range(start_s, end_s + 1):
        print(f"calc_pitching_metrics: processing season {season}…", flush=True)
        arsenal_read, a_ok, r_ok, fail_rows, skipped, pps_synced = run_season(
            client, season, bundle
        )
        grand_a_ok  += a_ok
        grand_r_ok  += r_ok
        grand_fail  += fail_rows
        grand_pps   += pps_synced
        print(
            f"calc_pitching_metrics: season {season} summary — "
            f"arsenal_rows_read={arsenal_read}, arsenal_rows_updated={a_ok}, "
            f"rollup_rows_written={r_ok}, rows_skipped={skipped}, "
            f"fail_rows={fail_rows}, pps_synced={pps_synced}",
            flush=True,
        )

    print(
        f"calc_pitching_metrics: final summary — "
        f"total_arsenal_rows_updated={grand_a_ok}, "
        f"total_rollup_rows_written={grand_r_ok}, "
        f"total_failures={grand_fail}, "
        f"total_pps_synced={grand_pps}",
        flush=True,
    )


if __name__ == "__main__":
    main()
