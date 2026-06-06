"""
Train the KNN-similarity Stuff+ model v2.

Architecture
------------
Three pitch-family models (fastball, breaking, off-speed).  Each family has
two KNN regressors — one predicting csw_rate (called-strikes + whiffs per
total pitch) and one predicting avg_woba_on_contact (mean wOBA on ball-in-play
events only).  The combined Stuff+ score is their 50/50 average after each is
scaled to 100 = league mean.

Why KNN instead of global regression
-------------------------------------
A global regression treats a 98-mph running FB and a 98-mph rising FB as the
same input vector (both have high velo, both have similar abs(movement)).
KNN finds the *most similar* pitch profiles in history and returns their
average outcomes — a running FB is compared to other running FBs, a rising FB
to other rising FBs.  This captures the nuance that identical velo/spin
numbers can correspond to very different pitch archetypes.

Family membership
-----------------
  fastball  : FF, SI, FC, FA
  breaking  : SL, ST, SV, CU, KC, CS
  offspeed  : CH, FS, FO, KN

Feature sets
------------
  Fastball  (5 features):
    avg_effective_speed, avg_spin_rate, avg_spin_axis,
    arm_side_movement, avg_v_movement

  Breaking / Off-speed  (7 features):
    same 5  +  velo_diff_from_fb,  v_break_diff_from_fb
    (differential vs. pitcher's own weighted-mean fastball in that season)

Arm-side movement transformation
----------------------------------
  arm_side_movement = -avg_h_movement if RHP
                    =  avg_h_movement  if LHP
  Positive = arm-side run, negative = glove-side run for both handednesses.
  RHP fastballs tail arm-side (positive), RHP sweepers break glove-side (negative).
  p_throws is NOT a separate feature — the sign-flipped arm_side already encodes
  handedness implicitly and lets all three family models compare across both hands.

Neighbor weighting
------------------
  Each neighbor is weighted by (1/distance) × sqrt(pitch_count).
  Inverse distance captures proximity in feature space; sqrt-damped
  pitch count up-weights neighbours with more reliable outcome estimates.

League means
------------
  The pitch-count-weighted mean of the training targets is stored in the
  model bundle.  Scoring uses:
    csw_score     = (predicted_csw     / csw_league_mean)     * 100
    contact_score = (contact_league_mean / predicted_contact) * 100  (inverted)
    stuff_plus    = (csw_score + contact_score) / 2

K selection
-----------
  5-fold CV across K ∈ {10,20,30,50,75,100,150,200}.  Optimal K is picked
  independently for the CSW and contact targets within each family.

Output
------
  pipeline/models/stuff_plus_model.pkl  — bundle dict:
    {
      "version": "2.1",
      "fastball":  {scaler, csw_knn, contact_knn,
                    csw_league_mean, contact_league_mean, feature_names},
      "breaking":  {...},
      "offspeed":  {...},
    }
"""

from __future__ import annotations

import argparse
import math
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler

import config  # noqa: F401 — loads pipeline/.env before db access
from db import get_client
from weighted_knn import WeightedKNNRegressor  # noqa: F401 — re-exported for callers

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL_PATH  = Path(__file__).parent / "models" / "stuff_plus_model.pkl"
_PAGE_SIZE   = 1_000
_MIN_PITCHES = 30          # minimum pitches per row to include in training

PITCH_FAMILY_MAP: dict[str, str] = {
    "FF": "fastball", "SI": "fastball", "FC": "fastball", "FA": "fastball",
    "SL": "breaking", "ST": "breaking", "SV": "breaking",
    "CU": "breaking", "KC": "breaking", "CS": "breaking",
    "CH": "offspeed", "FS": "offspeed", "FO": "offspeed", "KN": "offspeed",
}

_FASTBALL_TYPES: frozenset[str] = frozenset({"FF", "SI", "FC", "FA"})

_FAMILIES: tuple[str, ...] = ("fastball", "breaking", "offspeed")

# Feature names per family — must match the order in build_family_dataset()
FASTBALL_FEATURE_NAMES: list[str] = [
    "avg_effective_speed",
    "avg_spin_rate",
    "avg_spin_axis",
    "arm_side_movement",
    "avg_v_movement",
]

BREAKING_OFFSPEED_FEATURE_NAMES: list[str] = [
    "avg_effective_speed",
    "avg_spin_rate",
    "avg_spin_axis",
    "arm_side_movement",
    "avg_v_movement",
    "velo_diff_from_fb",
    "v_break_diff_from_fb",
]

_K_CANDIDATES: list[int] = [10, 20, 30, 50, 75, 100, 150, 200]
_CV_FOLDS:     int        = 5

_ARSENAL_SELECT = (
    "pitcher_id,season,pitch_type,p_throws,"
    "avg_effective_speed,avg_spin_rate,avg_spin_axis,"
    "avg_h_movement,avg_v_movement,"
    "pitches,csw_rate,avg_woba_on_contact"
)



# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_arsenal(
    client: Any,
    start_season: int,
    end_season: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for season in range(start_season, end_season + 1):
        offset = 0
        while True:
            res = (
                client.table("statcast_pitching_arsenal")
                .select(_ARSENAL_SELECT)
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
            page = res.data or []
            rows.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        print(
            f"train_stuff_plus_model: loaded season {season} "
            f"— {len(rows)} cumulative rows"
        )
    return rows


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------

def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        x = float(val)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def build_fb_maps(
    rows: list[dict[str, Any]],
) -> tuple[dict[tuple[int, str], float], dict[tuple[int, str], float]]:
    """
    Weighted-mean fastball (effective_speed, v_movement) per (pitcher_id, p_throws).

    Used by breaking / off-speed rows to compute differential features
    vs the pitcher's own fastball baseline in that season.

    Returns (fb_eff_speed_map, fb_v_map).
    """
    eff_speed_bins: dict[tuple[int, str], list[tuple[float, int]]] = {}
    v_mov_bins:     dict[tuple[int, str], list[tuple[float, int]]] = {}

    for row in rows:
        pt = str(row.get("pitch_type") or "").strip()
        if pt not in _FASTBALL_TYPES:
            continue
        pid  = row.get("pitcher_id")
        pthr = str(row.get("p_throws") or "").strip()
        if pid is None or pthr not in ("L", "R"):
            continue
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            continue

        es  = _to_float(row.get("avg_effective_speed"))
        vz  = _to_float(row.get("avg_v_movement"))
        n   = row.get("pitches")
        try:
            n_i = int(n) if n is not None else 0
        except (TypeError, ValueError):
            n_i = 0
        if n_i <= 0:
            continue

        key = (pid_i, pthr)
        if es is not None:
            eff_speed_bins.setdefault(key, []).append((es, n_i))
        if vz is not None:
            v_mov_bins.setdefault(key, []).append((vz, n_i))

    def _wmean(pairs: list[tuple[float, int]]) -> float | None:
        num = sum(v * w for v, w in pairs)
        den = sum(w for _, w in pairs)
        return num / den if den > 0 else None

    fb_eff_map = {k: _wmean(v) for k, v in eff_speed_bins.items()}  # type: ignore[misc]
    fb_v_map   = {k: _wmean(v) for k, v in v_mov_bins.items()}      # type: ignore[misc]
    return fb_eff_map, fb_v_map  # type: ignore[return-value]


def build_family_dataset(
    rows: list[dict[str, Any]],
    fb_eff_map: dict[tuple[int, str], float],
    fb_v_map:   dict[tuple[int, str], float],
    family: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[int]]:
    """
    Build feature matrix and dual-target arrays for one pitch family.

    Arm-side movement transformation is applied here:
        arm_side = avg_h_movement  if RHP
                 = -avg_h_movement if LHP

    Parameters
    ----------
    rows        : arsenal rows (dicts with avg_* keys)
    fb_eff_map  : (pitcher_id, p_throws) -> weighted-mean fastball effective_speed
    fb_v_map    : (pitcher_id, p_throws) -> weighted-mean fastball v_movement
    family      : "fastball" | "breaking" | "offspeed"

    Returns
    -------
    X            : (n, features)  — feature matrix
    y_csw        : (n,)           — csw_rate; NaN where unavailable
    y_contact    : (n,)           — avg_woba_on_contact; NaN where unavailable
    sample_weight: (n,)           — raw pitch counts
    valid_indices: list[int]      — indices into ``rows`` that passed filters
    """
    family_types = frozenset(pt for pt, fam in PITCH_FAMILY_MAP.items() if fam == family)
    is_fastball  = (family == "fastball")
    n_features   = (
        len(FASTBALL_FEATURE_NAMES) if is_fastball
        else len(BREAKING_OFFSPEED_FEATURE_NAMES)
    )

    X_list:   list[list[float]] = []
    csw_list: list[float]       = []
    con_list: list[float]       = []
    sw_list:  list[float]       = []
    idx_list: list[int]         = []

    for i, row in enumerate(rows):
        pt = str(row.get("pitch_type") or "").strip()
        if pt not in family_types:
            continue

        pthr = str(row.get("p_throws") or "").strip()
        if pthr not in ("L", "R"):
            continue

        pid = row.get("pitcher_id")
        if pid is None:
            continue
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            continue

        # All six core features must be present
        eff_speed = _to_float(row.get("avg_effective_speed"))
        spin_rate = _to_float(row.get("avg_spin_rate"))
        spin_axis = _to_float(row.get("avg_spin_axis"))
        h_mov     = _to_float(row.get("avg_h_movement"))
        v_mov     = _to_float(row.get("avg_v_movement"))

        if any(v is None for v in (eff_speed, spin_rate, spin_axis, h_mov, v_mov)):
            continue

        # arm_side: positive = arm-side run, negative = glove-side run
        # RHP: pfx_x is negative for arm-side movement → negate to make positive
        # LHP: pfx_x is positive for arm-side movement → keep as-is
        arm_side = -h_mov if pthr == "R" else h_mov  # type: ignore[operator]

        feat: list[float] = [
            eff_speed,  # type: ignore[list-item]
            spin_rate,  # type: ignore[list-item]
            spin_axis,  # type: ignore[list-item]
            arm_side,
            v_mov,      # type: ignore[list-item]
        ]

        if not is_fastball:
            key          = (pid_i, pthr)
            fb_es        = fb_eff_map.get(key)
            fb_vz        = fb_v_map.get(key)
            velo_diff    = (fb_es - eff_speed) if fb_es is not None else 0.0  # type: ignore[operator]
            v_break_diff = (fb_vz - v_mov)     if fb_vz is not None else 0.0  # type: ignore[operator]
            feat.extend([velo_diff, v_break_diff])

        # Targets — NaN sentinel for missing values
        csw     = _to_float(row.get("csw_rate"))
        contact = _to_float(row.get("avg_woba_on_contact"))

        n_pitches = row.get("pitches")
        try:
            n_i = max(1, int(n_pitches)) if n_pitches is not None else 1
        except (TypeError, ValueError):
            n_i = 1

        X_list.append(feat)
        csw_list.append(csw     if csw     is not None else float("nan"))
        con_list.append(contact if contact is not None else float("nan"))
        sw_list.append(float(n_i))
        idx_list.append(i)

    if not X_list:
        empty = np.empty((0, n_features), dtype=np.float64)
        return empty, np.empty(0), np.empty(0), np.empty(0), []

    return (
        np.array(X_list,  dtype=np.float64),
        np.array(csw_list, dtype=np.float64),
        np.array(con_list, dtype=np.float64),
        np.array(sw_list,  dtype=np.float64),
        idx_list,
    )


# ---------------------------------------------------------------------------
# K cross-validation
# ---------------------------------------------------------------------------

def _cv_r2(
    X: np.ndarray,
    y: np.ndarray,
    sw: np.ndarray,
    k: int,
    n_splits: int = _CV_FOLDS,
    random_state: int = 42,
) -> float:
    """Return mean 5-fold CV R² for WeightedKNNRegressor(K) on (X, y)."""
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    scores: list[float] = []
    for train_idx, val_idx in kf.split(X):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]
        sw_tr       = sw[train_idx]

        scaler  = StandardScaler()
        X_tr_s  = scaler.fit_transform(X_tr)
        X_val_s = scaler.transform(X_val)

        knn = WeightedKNNRegressor(n_neighbors=k)
        knn.fit(X_tr_s, y_tr, sample_weight=sw_tr)
        y_pred = knn.predict(X_val_s)

        ss_res = float(np.sum((y_val - y_pred) ** 2))
        ss_tot = float(np.sum((y_val - y_val.mean()) ** 2))
        r2     = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
        scores.append(r2)
    return float(np.mean(scores))


def find_best_k(
    X: np.ndarray,
    y: np.ndarray,
    sw: np.ndarray,
    target_name: str,
    family: str,
) -> int:
    """
    Run 5-fold CV across _K_CANDIDATES.  Prints a result table.
    Returns the K with the highest mean CV R².
    """
    print(f"  [{family} / {target_name}]  K-selection ({_CV_FOLDS}-fold CV):")
    best_k  = _K_CANDIDATES[0]
    best_r2 = -float("inf")

    for k in _K_CANDIDATES:
        if k >= len(X):
            print(f"    K={k:4d}  skipped (k >= n_rows={len(X)})")
            continue
        r2     = _cv_r2(X, y, sw, k)
        marker = " <--" if r2 > best_r2 else ""
        print(f"    K={k:4d}  CV R²={r2:+.4f}{marker}")
        if r2 > best_r2:
            best_r2 = r2
            best_k  = k

    print(f"    best K={best_k}  (CV R²={best_r2:+.4f})")
    return best_k


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    start_season: int = 2015,
    end_season:   int | None = None,
) -> None:
    if end_season is None:
        end_season = datetime.now().year

    client = get_client()

    print(f"train_stuff_plus_model: loading arsenal {start_season}–{end_season}…")
    all_rows = _load_arsenal(client, start_season, end_season)

    # Minimum-pitch filter — removes tiny sample rows from training
    filtered = [r for r in all_rows if (r.get("pitches") or 0) >= _MIN_PITCHES]
    print(
        f"train_stuff_plus_model: {len(all_rows)} total rows -> "
        f"{len(filtered)} after min-pitch filter ({_MIN_PITCHES})"
    )

    # Fastball reference maps — all rows used (not just filtered) so that pitchers
    # who mainly throw fastballs but below the threshold still contribute baselines
    # for other pitch types.
    fb_eff_map, fb_v_map = build_fb_maps(all_rows)

    bundle: dict[str, Any] = {"version": "2.1"}

    for family in _FAMILIES:
        print(f"\n{'='*60}")
        print(f"train_stuff_plus_model: FAMILY = {family.upper()}")
        print(f"{'='*60}")

        X, y_csw, y_contact, sw, _ = build_family_dataset(
            filtered, fb_eff_map, fb_v_map, family
        )

        if X.shape[0] == 0:
            print(f"  no rows for family {family} — skipping")
            continue

        feature_names = (
            FASTBALL_FEATURE_NAMES if family == "fastball"
            else BREAKING_OFFSPEED_FEATURE_NAMES
        )
        print(
            f"  rows={X.shape[0]}  features={X.shape[1]}"
            f"  ({', '.join(feature_names)})"
        )

        # Fit one scaler on all family rows (shared between CSW + contact models
        # within this family so inference uses a single transform per row).
        scaler   = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # ── CSW model ────────────────────────────────────────────────────────
        csw_mask   = np.isfinite(y_csw)
        X_csw      = X_scaled[csw_mask]
        y_csw_f    = y_csw[csw_mask]
        sw_csw     = sw[csw_mask]

        print(
            f"\n  CSW target: {int(csw_mask.sum())} rows  "
            f"mean={y_csw_f.mean():.4f}  "
            f"std={y_csw_f.std():.4f}"
        )
        k_csw   = find_best_k(X_csw, y_csw_f, sw_csw, "csw_rate",    family)
        csw_knn = WeightedKNNRegressor(n_neighbors=k_csw)
        csw_knn.fit(X_csw, y_csw_f, sample_weight=sw_csw)

        # League mean = pitch-count-weighted mean of the training target values
        csw_league_mean = float(np.average(y_csw_f, weights=sw_csw))
        print(f"  CSW league mean: {csw_league_mean:.4f}")

        # ── Contact model ─────────────────────────────────────────────────────
        con_mask = np.isfinite(y_contact)
        X_con    = X_scaled[con_mask]
        y_con    = y_contact[con_mask]
        sw_con   = sw[con_mask]

        print(
            f"\n  Contact target: {int(con_mask.sum())} rows  "
            f"mean={y_con.mean():.4f}  "
            f"std={y_con.std():.4f}"
        )
        k_contact   = find_best_k(X_con, y_con, sw_con, "avg_woba_on_contact", family)
        contact_knn = WeightedKNNRegressor(n_neighbors=k_contact)
        contact_knn.fit(X_con, y_con, sample_weight=sw_con)

        contact_league_mean = float(np.average(y_con, weights=sw_con))
        print(f"  Contact league mean: {contact_league_mean:.4f}")

        bundle[family] = {
            "scaler":               scaler,
            "csw_knn":              csw_knn,
            "contact_knn":          contact_knn,
            "csw_league_mean":      csw_league_mean,
            "contact_league_mean":  contact_league_mean,
            "feature_names":        feature_names,
        }

    # Save bundle
    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(bundle, f)

    families_trained = [k for k in bundle if k != "version"]
    print(f"\ntrain_stuff_plus_model: saved -> {_MODEL_PATH}")
    print(f"  families in bundle: {families_trained}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Train the KNN-similarity Stuff+ model v2 "
            "(3-family, dual-target: CSW + contact wOBA)."
        )
    )
    p.add_argument(
        "--start-season", type=int, default=2015,
        help="First season to include in training data (default 2015).",
    )
    p.add_argument(
        "--end-season", type=int, default=None,
        help="Last season (default: current calendar year).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    train(start_season=args.start_season, end_season=args.end_season)
