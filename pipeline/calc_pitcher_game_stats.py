"""
Compute per-game pitcher statistics and write to ``pitcher_game_stats``
and ``pitcher_game_pa_log``.

How it works
------------
For each pitcher-game appearance, pitches are grouped by type.  Features are
computed from the game's own pitch averages (not season averages) so a start
with +2 mph extra velo registers a higher Stuff+ than the season baseline.

Stuff+ uses the KNN similarity bundle (v2) trained by train_stuff_plus_model.py.
Each pitch type is routed to its pitch-family model (fastball / breaking /
offspeed), scored on both csw_rate and contact wOBA targets, and the combined
50/50 score is stored.  The league means come from the bundle itself — no
per-season arsenal load required.

Outputs
-------
``pitcher_game_stats``  — one row per pitcher-game; flat stats + three JSONB
                          breakdowns (pitch_type_stats, first_pitch_mix,
                          count_pitch_mix).

``pitcher_game_pa_log`` — one row per completed plate appearance; final-pitch
                          details and count so UIs can display "K on a 98 mph
                          4-seamer in a 0-2 count".

Stuff+ features (per pitch type within the game)
-------------------------------------------------
  avg_effective_speed, avg_spin_rate, avg_spin_axis,
  arm_side_movement (positive = arm-side, negative = glove-side for both hands),
  avg_v_movement (pfx_z)

  Breaking / off-speed add:
    velo_diff_from_fb    (game fastball eff_speed − this type's eff_speed)
    v_break_diff_from_fb (game fastball pfx_z     − this type's pfx_z)

Usage
-----
  # Full history (default 2015 -> current year)
  python calc_pitcher_game_stats.py

  # Single season
  python calc_pitcher_game_stats.py --start-season 2026 --end-season 2026

  # Single game day (for daily pipeline)
  python calc_pitcher_game_stats.py --date 2026-06-01
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import config  # noqa: F401 -- loads pipeline/.env before db access
from db import get_client
from train_stuff_plus_model import PITCH_FAMILY_MAP as _PITCH_FAMILY_MAP
from weighted_knn import WeightedKNNRegressor  # noqa: F401 — needed so pickle can resolve the class

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL_PATH = Path(__file__).parent / "models" / "stuff_plus_model.pkl"
_PAGE_SIZE   = 1_000
_UPSERT_BATCH = 500
_DEFAULT_START_SEASON = 2015

# Minimum pitches of a type in a game to include in pitch_type_stats JSONB.
# (Overall stuff_plus still uses all eligible types regardless of count.)
_MIN_PITCHES_FOR_TYPE_BREAKDOWN = 5

_FASTBALL_TYPES: frozenset[str] = frozenset({"FF", "SI", "FC", "FA"})

_STUFF_PLUS_ELIGIBLE: frozenset[str] = frozenset(
    {"FF", "SI", "FC", "FA", "SL", "ST", "SV", "CU", "KC", "CS", "CH", "FS", "FO", "KN"}
)

_ALLOWED_P_THROWS: frozenset[str] = frozenset({"L", "R"})

# Statcast description buckets
_SWING_DESCRIPTIONS: frozenset[str] = frozenset({
    "swinging_strike", "swinging_strike_blocked",
    "foul", "foul_tip",
    "hit_into_play", "hit_into_play_no_out", "hit_into_play_score",
})
_WHIFF_DESCRIPTIONS: frozenset[str] = frozenset({
    "swinging_strike", "swinging_strike_blocked",
})

# Statcast zone codes
_IN_ZONE: frozenset[int]     = frozenset(range(1, 10))   # zones 1-9 = in strike zone
_OUTSIDE_ZONE: frozenset[int] = frozenset({11, 12, 13, 14})

# Event type buckets for outcome counting
_K_EVENTS:   frozenset[str] = frozenset({"strikeout", "strikeout_double_play"})
_BB_EVENTS:  frozenset[str] = frozenset({"walk", "intent_walk"})
_HIT_EVENTS: frozenset[str] = frozenset({"single", "double", "triple", "home_run"})
_HR_EVENTS:  frozenset[str] = frozenset({"home_run"})

# Columns pulled from statcast_pitches
_PITCH_SELECT = (
    "pitcher_id,pitcher_name,p_throws,game_pk,game_date,"
    "pitch_type,release_speed,release_spin_rate,pfx_x,pfx_z,"
    "description,zone,home_team,away_team,"
    "at_bat_number,pitch_number,events,batter_id,stand,"
    "balls,strikes,"
    "spin_axis,release_extension,arm_angle,effective_speed,"
    "api_break_z_with_gravity,api_break_x_arm,"
    "delta_run_exp,woba_value"
)

# League means are embedded in the model bundle — no arsenal load required.


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

def _load_model() -> dict[str, Any]:
    """Load the KNN Stuff+ model bundle (v2) from disk."""
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
            f"Model bundle version {version!r} incompatible "
            "(expected '2.1'). Re-run train_stuff_plus_model.py."
        )
    print(
        f"calc_pitcher_game_stats: loaded model bundle v{version} "
        f"from {_MODEL_PATH}",
        flush=True,
    )
    return bundle


def _load_pitches(
    client: Any,
    *,
    season: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Load statcast_pitches rows.

    Pass ``season`` for a full-season load, or ``start_date``/``end_date``
    (YYYY-MM-DD) for a date-range load (e.g. single game day).

    Full-season loads chunk by calendar month to keep each sub-query's max
    OFFSET well below Postgres statement-timeout thresholds (~70 K rows/month
    vs 700 K+ rows/season).
    """
    import calendar as _calendar

    rows: list[dict[str, Any]] = []

    if season is not None:
        # Monthly chunking: 12 passes, each capped at ~70 K rows
        for month in range(1, 13):
            last_day = _calendar.monthrange(season, month)[1]
            m_start  = f"{season}-{month:02d}-01"
            m_end    = f"{season}-{month:02d}-{last_day:02d}"
            offset   = 0
            while True:
                q = (
                    client.table("statcast_pitches")
                    .select(_PITCH_SELECT)
                    .gte("game_date", m_start)
                    .lte("game_date", m_end)
                    .order("game_date")
                    .range(offset, offset + _PAGE_SIZE - 1)
                    .limit(_PAGE_SIZE)
                )
                res  = _safe_execute(q)
                page = res.data or []
                rows.extend(page)
                if len(page) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE
    else:
        # Date-range load (single day or short window) — simple offset loop
        offset = 0
        while True:
            q = client.table("statcast_pitches").select(_PITCH_SELECT)
            if start_date is not None:
                q = q.gte("game_date", start_date)
            if end_date is not None:
                q = q.lte("game_date", end_date)
            q = q.order("game_date").range(offset, offset + _PAGE_SIZE - 1).limit(_PAGE_SIZE)
            res  = _safe_execute(q)
            page = res.data or []
            rows.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _safe_execute(q: Any, retries: int = 4, base_delay: float = 2.0) -> Any:
    """
    Execute a PostgREST query with retry on transient HTTP/2 connection errors.

    Supabase terminates HTTP/2 connections after many streams (GOAWAY frame).
    httpx will open a fresh connection on the next attempt, so a simple retry
    with a short back-off is sufficient.
    """
    for attempt in range(retries):
        try:
            return q.execute()
        except Exception as exc:
            name = type(exc).__name__
            cause_name = type(exc.__cause__).__name__ if exc.__cause__ else ""
            is_transient = any(
                kw in name or kw in cause_name
                for kw in ("RemoteProtocolError", "ConnectError", "ConnectionTerminated")
            )
            if is_transient and attempt < retries - 1:
                delay = base_delay * (attempt + 1)
                print(
                    f"  [retry {attempt + 1}/{retries - 1}] transient connection error "
                    f"({name}), retrying in {delay:.0f}s...",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        x = float(val)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _round(val: Any, ndigits: int = 1) -> float | None:
    f = _to_float(val)
    return None if f is None else round(f, ndigits)


def _mean_col(series: pd.Series, ndigits: int = 1) -> float | None:
    """Mean of a numeric series, None if empty."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return round(float(s.mean()), ndigits)


def _max_col(series: pd.Series, ndigits: int = 1) -> float | None:
    """Max of a numeric series, None if empty."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return round(float(s.max()), ndigits)


def _zone_int(val: Any) -> int | None:
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


def _mode_str(series: pd.Series) -> str | None:
    s = series.dropna().astype(str).str.strip()
    s = s[s != "nan"]
    if s.empty:
        return None
    m = s.mode()
    return str(m.iloc[0]) if not m.empty else str(s.iloc[0])


def _col_present(df: pd.DataFrame, col: str) -> bool:
    """True if ``col`` exists in df and has at least one non-null value."""
    return col in df.columns and df[col].notna().any()


# ---------------------------------------------------------------------------
# Core: build game-level records
# ---------------------------------------------------------------------------

def _build_game_records(
    df: pd.DataFrame,
    season: int,
    bundle: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    For each (pitcher_id, game_pk) group produce:
      - one record for ``pitcher_game_stats``
      - N records for ``pitcher_game_pa_log`` (one per completed PA)

    Returns (game_stats_records, pa_log_records).

    Performance notes
    -----------------
    * Zone/description masks are computed once on the full DataFrame (vectorized)
      rather than repeated per group with Python-level .apply() calls.
    * KNN Stuff+ predictions are batched by pitch-family — 6 total predict()
      calls instead of ~60 K individual calls — so the BallTree can use
      n_jobs=-1 parallelism and BLAS batching.
    * Column-presence flags are evaluated once at function entry.
    """
    if df.empty:
        return [], []

    # ── Coerce numeric columns once upfront ──────────────────────────────────
    for col in (
        "pitcher_id", "game_pk", "at_bat_number", "pitch_number",
        "release_speed", "release_spin_rate", "pfx_x", "pfx_z",
        "spin_axis", "release_extension", "arm_angle", "effective_speed",
        "api_break_z_with_gravity", "api_break_x_arm",
        "delta_run_exp", "woba_value",
        "balls", "strikes",
    ):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["pitch_type"] = df["pitch_type"].astype(str).str.strip()
    df["p_throws"]   = df["p_throws"].astype(str).str.strip()
    df = df[df["p_throws"].isin(_ALLOWED_P_THROWS)].copy()
    df = df[df["pitcher_id"].notna() & df["game_pk"].notna()].copy()

    if df.empty:
        return [], []

    # ── Column-presence flags (checked ONCE, not per sub-DataFrame) ──────────
    has_zone       = "zone" in df.columns and df["zone"].notna().any()
    has_desc       = "description" in df.columns
    has_spin_axis  = _col_present(df, "spin_axis")
    has_eff_speed  = _col_present(df, "effective_speed")
    has_ext        = _col_present(df, "release_extension")
    has_arm_angle  = _col_present(df, "arm_angle")
    has_delta_re   = _col_present(df, "delta_run_exp")
    has_api_brk_z  = _col_present(df, "api_break_z_with_gravity")
    has_api_brk_x  = _col_present(df, "api_break_x_arm")
    has_woba       = _col_present(df, "woba_value")
    has_events     = "events" in df.columns
    has_at_bat     = "at_bat_number" in df.columns
    has_pitch_num  = "pitch_number" in df.columns
    has_balls      = "balls" in df.columns and df["balls"].notna().any()
    has_strikes    = "strikes" in df.columns

    # ── Pre-compute vectorised zone / description masks ───────────────────────
    if has_zone:
        _z = pd.to_numeric(df["zone"], errors="coerce")
        df["_in_zone"]  = _z.between(1, 9, inclusive="both")
        df["_out_zone"] = _z.isin([11, 12, 13, 14])

    if has_desc:
        _d = df["description"].astype(str).str.strip()
        df["_is_swing"] = _d.isin(_SWING_DESCRIPTIONS)
        df["_is_whiff"] = _d.isin(_WHIFF_DESCRIPTIONS)

    # ── Pre-compute vectorised events flags ───────────────────────────────────
    if has_events:
        _ev = df["events"].fillna("").astype(str).str.strip()
        df["_ev_k"]  = _ev.isin(_K_EVENTS)
        df["_ev_bb"] = _ev.isin(_BB_EVENTS)
        df["_ev_h"]  = _ev.isin(_HIT_EVENTS)
        df["_ev_hr"] = _ev.isin(_HR_EVENTS)
        df["_ev_any"] = _ev != ""

    # ── Phase 1: Batch KNN scoring ────────────────────────────────────────────
    # Collect one feature vector per (pitcher_id, game_pk, pitch_type, p_throws),
    # then do ONE predict() call per family×model (6 total) instead of ~60 K.
    knn_scores: dict[tuple[int, int, str], float] = {}

    # Fastball baseline per (pitcher_id, game_pk, p_throws) for differential features
    fb_es_map:  dict[tuple[int, int, str], float | None] = {}
    fb_vz_map:  dict[tuple[int, int, str], float | None] = {}
    if has_eff_speed or "pfx_z" in df.columns:
        fb_sel = df[df["pitch_type"].isin(_FASTBALL_TYPES)]
        if not fb_sel.empty:
            for (pid_, gpk_, pthr_), fbg in fb_sel.groupby(
                ["pitcher_id", "game_pk", "p_throws"], sort=False
            ):
                key_ = (int(pid_), int(gpk_), str(pthr_))
                fb_es_map[key_] = _to_float(fbg["effective_speed"].mean()) if has_eff_speed else None
                fb_vz_map[key_] = _to_float(fbg["pfx_z"].mean()) if "pfx_z" in fbg.columns else None

    elig = df[df["pitch_type"].isin(_STUFF_PLUS_ELIGIBLE)]
    if not elig.empty and has_eff_speed and has_spin_axis:
        for family in ("fastball", "breaking", "offspeed"):
            if family not in bundle:
                continue
            fam_ptypes = frozenset(
                pt for pt, f in _PITCH_FAMILY_MAP.items() if f == family
            )
            fam_df = elig[elig["pitch_type"].isin(fam_ptypes)]
            if fam_df.empty:
                continue

            feat_rows:  list[list[float]] = []
            feat_keys:  list[tuple[int, int, str]] = []

            for (pid_, gpk_, ptype_, pthr_), g in fam_df.groupby(
                ["pitcher_id", "game_pk", "pitch_type", "p_throws"], sort=False
            ):
                pid_i_ = int(pid_)
                gpk_i_ = int(gpk_)
                pthr_s = str(pthr_)
                ptype_s = str(ptype_).strip()

                es   = _to_float(g["effective_speed"].mean())
                sp_r = _to_float(g["release_spin_rate"].mean()) if "release_spin_rate" in g.columns else None
                sa   = _to_float(g["spin_axis"].mean()) if has_spin_axis else None
                hx_v = _to_float(g["pfx_x"].mean()) if "pfx_x" in g.columns else None
                vz_v = _to_float(g["pfx_z"].mean()) if "pfx_z" in g.columns else None

                if any(v is None for v in (es, sp_r, sa, hx_v, vz_v)):
                    continue

                # arm_side: positive = arm-side run, negative = glove-side run
                arm_side = -hx_v if pthr_s == "R" else hx_v  # type: ignore[operator]
                feat: list[float] = [es, sp_r, sa, arm_side, vz_v]  # type: ignore[list-item]

                if family != "fastball":
                    bk = (pid_i_, gpk_i_, pthr_s)
                    fb_es = fb_es_map.get(bk)
                    fb_vz = fb_vz_map.get(bk)
                    feat.extend([
                        (fb_es - es) if fb_es is not None else 0.0,  # type: ignore[operator]
                        (fb_vz - vz_v) if fb_vz is not None else 0.0,  # type: ignore[operator]
                    ])

                feat_rows.append(feat)
                feat_keys.append((pid_i_, gpk_i_, ptype_s))

            if not feat_rows:
                continue

            # Single batch predict — BallTree parallelises across cores
            fb_m     = bundle[family]
            X        = np.array(feat_rows, dtype=np.float64)
            X_scaled = fb_m["scaler"].transform(X)
            raw_csw  = fb_m["csw_knn"].predict(X_scaled)
            raw_con  = fb_m["contact_knn"].predict(X_scaled)
            csw_lg   = fb_m["csw_league_mean"]
            con_lg   = fb_m["contact_league_mean"]

            for i, key_ in enumerate(feat_keys):
                csw_sc  = (raw_csw[i] / max(csw_lg, 1e-6)) * 100.0
                con_sc  = min((max(con_lg, 0.01) / max(float(raw_con[i]), 0.01)) * 100.0, 200.0)
                knn_scores[key_] = round(csw_sc * 0.75 + con_sc * 0.25, 1)

    # ── Phase 2: Loop through (pitcher, game) groups and assemble records ─────
    game_stats: list[dict[str, Any]] = []
    pa_log:     list[dict[str, Any]] = []
    n_groups = 0

    for (pid, gpk), game_df in df.groupby(["pitcher_id", "game_pk"], sort=False):
        n_groups += 1
        if n_groups % 2000 == 0:
            print(f"  [build] {n_groups} groups processed...", flush=True)

        pid_i   = int(pid)
        gpk_i   = int(gpk)
        n_total = len(game_df)

        # ── Metadata ────────────────────────────────────────────────────────
        pitcher_name  = _mode_str(game_df["pitcher_name"]) if "pitcher_name" in game_df.columns else None
        p_throws      = _mode_str(game_df["p_throws"])
        home_team     = _mode_str(game_df["home_team"]) if "home_team" in game_df.columns else None
        away_team     = _mode_str(game_df["away_team"]) if "away_team" in game_df.columns else None
        game_date_str = str(game_df["game_date"].iloc[0])[:10]

        # ── Batters faced ────────────────────────────────────────────────────
        batters_faced = int(game_df["at_bat_number"].nunique()) if has_at_bat else None

        # ── Velocity / spin / extension ─────────────────────────────────────
        avg_velo      = _to_float(round(game_df["release_speed"].mean(), 1))      if "release_speed" in game_df.columns else None
        max_velo      = _to_float(round(game_df["release_speed"].max(), 1))       if "release_speed" in game_df.columns else None
        avg_spin_rate = _to_float(round(game_df["release_spin_rate"].mean(), 0))  if "release_spin_rate" in game_df.columns else None
        avg_extension = _to_float(round(game_df["release_extension"].mean(), 2))  if has_ext else None
        avg_arm_angle = _to_float(round(game_df["arm_angle"].mean(), 1))          if has_arm_angle else None

        # ── Rate stats (game-level) — use pre-computed boolean columns ────────
        swings_n  = int(game_df["_is_swing"].sum()) if has_desc else 0
        whiffs_n  = int(game_df["_is_whiff"].sum()) if has_desc else 0
        whiff_rate      = round(100.0 * whiffs_n / n_total, 4) if n_total > 0 else None
        whiff_per_swing = round(100.0 * whiffs_n / swings_n, 4) if swings_n > 0 else None

        zone_rate  = None
        chase_rate = None
        if has_zone:
            in_zone_n = int(game_df["_in_zone"].sum())
            zone_rate = round(100.0 * in_zone_n / n_total, 4) if n_total > 0 else None
            out_df = game_df[game_df["_out_zone"]]
            if len(out_df) > 0 and has_desc:
                chase_rate = round(100.0 * int(out_df["_is_swing"].sum()) / len(out_df), 4)

        avg_delta_run_exp = _to_float(round(game_df["delta_run_exp"].mean(), 4)) if has_delta_re else None

        # ── Outcome counts ────────────────────────────────────────────────────
        strikeouts = walks = hits_allowed = home_runs_allowed = 0
        if has_events:
            strikeouts       = int(game_df["_ev_k"].sum())
            walks            = int(game_df["_ev_bb"].sum())
            hits_allowed     = int(game_df["_ev_h"].sum())
            home_runs_allowed= int(game_df["_ev_hr"].sum())
        event_df = game_df[game_df["_ev_any"]] if has_events else pd.DataFrame()

        # ── PA log rows ──────────────────────────────────────────────────────
        if has_at_bat and has_pitch_num:
            for ab_num, ab_df in game_df.groupby("at_bat_number", sort=False):
                final = ab_df.loc[ab_df["pitch_number"].idxmax()]
                ev_str = str(final.get("events") or "").strip()
                if not ev_str or ev_str == "nan":
                    continue  # incomplete PA
                fpt   = str(final.get("pitch_type") or "").strip()
                fhand = str(final.get("stand") or "").strip()
                pa_log.append({
                    "pitcher_id":           pid_i,
                    "game_pk":              gpk_i,
                    "at_bat_number":        int(ab_num),
                    "game_date":            game_date_str,
                    "season":               season,
                    "event":                ev_str or None,
                    "pitch_count":          len(ab_df),
                    "final_pitch_type":     fpt if fpt and fpt != "nan" else None,
                    "final_pitch_velo":     _round(final.get("release_speed"), 1),
                    "final_pitch_spin":     _round(final.get("release_spin_rate"), 0),
                    "final_pitch_h_move":   _round(final.get("pfx_x"), 3),
                    "final_pitch_v_move":   _round(final.get("pfx_z"), 3),
                    "final_pitch_spin_axis":_round(final.get("spin_axis"), 0),
                    "final_pitch_extension":_round(final.get("release_extension"), 2),
                    "final_pitch_desc":     str(final.get("description") or "").strip() or None,
                    "balls_at_event":       _to_int(final.get("balls")),
                    "strikes_at_event":     _to_int(final.get("strikes")),
                    "batter_id":            _to_int(final.get("batter_id")),
                    "batter_name":          None,
                    "batter_hand":          fhand if fhand in {"L", "R"} else None,
                })

        # ── Per-pitch-type JSONB: look up pre-computed KNN scores ────────────
        pitch_type_stats: dict[str, Any] = {}
        all_scored: list[tuple[float, int]] = []

        for ptype, pt_df in game_df.groupby("pitch_type", sort=False):
            ptype_s = str(ptype).strip()
            n_type  = len(pt_df)

            # KNN score from pre-computed map (no predict() call here)
            type_stuff: float | None = knn_scores.get((pid_i, gpk_i, ptype_s))
            if type_stuff is not None:
                all_scored.append((type_stuff, n_type))

            # Only include in JSONB if enough pitches
            if n_type < _MIN_PITCHES_FOR_TYPE_BREAKDOWN:
                continue

            # Basic means — columns already numeric, direct .mean() is safe
            av = _to_float(pt_df["release_speed"].mean())      if "release_speed" in pt_df.columns else None
            sp = _to_float(pt_df["release_spin_rate"].mean())  if "release_spin_rate" in pt_df.columns else None
            hx = _to_float(pt_df["pfx_x"].mean())              if "pfx_x" in pt_df.columns else None
            vz = _to_float(pt_df["pfx_z"].mean())              if "pfx_z" in pt_df.columns else None

            # Rate stats — use pre-computed boolean columns
            pt_swings = int(pt_df["_is_swing"].sum()) if has_desc else 0
            pt_whiffs = int(pt_df["_is_whiff"].sum()) if has_desc else 0
            pt_whiff_rate      = round(100.0 * pt_whiffs / n_type, 4) if n_type > 0 else None
            pt_whiff_per_swing = round(100.0 * pt_whiffs / pt_swings, 4) if pt_swings > 0 else None

            pt_zone_rate  = None
            pt_chase_rate = None
            if has_zone:
                pt_in_n = int(pt_df["_in_zone"].sum())
                pt_zone_rate = round(100.0 * pt_in_n / n_type, 4) if n_type > 0 else None
                pt_out_df = pt_df[pt_df["_out_zone"]]
                if len(pt_out_df) > 0 and has_desc:
                    pt_chase_rate = round(
                        100.0 * int(pt_out_df["_is_swing"].sum()) / len(pt_out_df), 4
                    )

            # Outcome counts per type
            pt_strikeouts = pt_walks = pt_hits = pt_hrs = pt_pa_ending = 0
            if has_events and not event_df.empty and "pitch_type" in event_df.columns:
                pt_ev = event_df[event_df["pitch_type"] == ptype_s]
                if not pt_ev.empty:
                    pt_strikeouts = int(pt_ev["_ev_k"].sum())
                    pt_walks      = int(pt_ev["_ev_bb"].sum())
                    pt_hits       = int(pt_ev["_ev_h"].sum())
                    pt_hrs        = int(pt_ev["_ev_hr"].sum())
                    pt_pa_ending  = len(pt_ev)

            pt_avg_dre  = _to_float(round(pt_df["delta_run_exp"].mean(), 4)) if has_delta_re else None
            pt_avg_woba = _to_float(round(pt_df["woba_value"].mean(), 4))    if has_woba else None

            pitch_type_stats[ptype_s] = {
                "pitches":             n_type,
                "usage_pct":           round(100.0 * n_type / n_total, 1) if n_total > 0 else None,
                "avg_velo":            _round(av, 1),
                "max_velo":            _to_float(round(pt_df["release_speed"].max(), 1)) if "release_speed" in pt_df.columns else None,
                "avg_spin_rate":       _round(sp, 0),
                "avg_spin_axis":       _to_float(round(pt_df["spin_axis"].mean(), 0))         if has_spin_axis else None,
                "avg_h_movement":      _round(hx, 3),
                "avg_v_movement":      _round(vz, 3),
                "avg_extension":       _to_float(round(pt_df["release_extension"].mean(), 2)) if has_ext else None,
                "avg_arm_angle":       _to_float(round(pt_df["arm_angle"].mean(), 1))         if has_arm_angle else None,
                "avg_effective_speed": _to_float(round(pt_df["effective_speed"].mean(), 1))   if has_eff_speed else None,
                "avg_api_break_z":     _to_float(round(pt_df["api_break_z_with_gravity"].mean(), 2)) if has_api_brk_z else None,
                "avg_api_break_x_arm": _to_float(round(pt_df["api_break_x_arm"].mean(), 2))         if has_api_brk_x else None,
                "whiff_rate":          pt_whiff_rate,
                "whiff_per_swing":     pt_whiff_per_swing,
                "chase_rate":          pt_chase_rate,
                "zone_rate":           pt_zone_rate,
                "stuff_plus":          type_stuff,
                "avg_delta_run_exp":   pt_avg_dre,
                "avg_woba_value":      pt_avg_woba,
                "strikeouts":          pt_strikeouts,
                "walks":               pt_walks,
                "hits_allowed":        pt_hits,
                "home_runs_allowed":   pt_hrs,
                "pa_ending_count":     pt_pa_ending,
            }

        # ── Weighted overall Stuff+ ───────────────────────────────────────────
        overall_stuff: float | None = None
        if all_scored:
            total_scored = sum(n for _, n in all_scored)
            if total_scored > 0:
                overall_stuff = round(
                    sum(s * n for s, n in all_scored) / total_scored, 1
                )

        # ── first_pitch_mix ──────────────────────────────────────────────────
        first_pitch_mix: dict[str, float] | None = None
        if has_pitch_num:
            fp_df = game_df[game_df["pitch_number"] == 1]
            if len(fp_df) > 0:
                fp_counts = fp_df["pitch_type"].value_counts()
                total_fp  = len(fp_df)
                first_pitch_mix = {
                    str(k): round(100.0 * int(v) / total_fp, 1)
                    for k, v in fp_counts.items()
                    if str(k) not in {"nan", ""}
                }

        # ── count_pitch_mix ──────────────────────────────────────────────────
        count_pitch_mix: dict[str, Any] | None = None
        if has_balls and has_strikes:
            cm_df = game_df[game_df["balls"].notna() & game_df["strikes"].notna()].copy()
            if not cm_df.empty:
                cm_df["count_key"] = (
                    cm_df["balls"].astype(int).astype(str)
                    + "-"
                    + cm_df["strikes"].astype(int).astype(str)
                )
                cpm: dict[str, Any] = {}
                for count_key, cnt_df in cm_df.groupby("count_key", sort=False):
                    n_cnt       = len(cnt_df)
                    type_counts = cnt_df["pitch_type"].value_counts()
                    entry: dict[str, Any] = {"pitches": n_cnt}
                    for pt, pt_n in type_counts.items():
                        if str(pt) not in {"nan", ""}:
                            entry[str(pt)] = round(100.0 * int(pt_n) / n_cnt, 1)
                    cpm[str(count_key)] = entry
                count_pitch_mix = cpm if cpm else None

        # ── Assemble game_stats record ────────────────────────────────────────
        game_stats.append({
            "pitcher_id":           pid_i,
            "game_pk":              gpk_i,
            "game_date":            game_date_str,
            "season":               season,
            "pitcher_name":         pitcher_name,
            "p_throws":             p_throws,
            "home_team":            home_team,
            "away_team":            away_team,
            "pitches":              n_total,
            "batters_faced":        batters_faced,
            "avg_velo":             avg_velo,
            "max_velo":             max_velo,
            "avg_spin_rate":        avg_spin_rate,
            "avg_extension":        avg_extension,
            "avg_arm_angle":        avg_arm_angle,
            "stuff_plus":           overall_stuff,
            "strikeouts":           strikeouts,
            "walks":                walks,
            "hits_allowed":         hits_allowed,
            "home_runs_allowed":    home_runs_allowed,
            "whiff_rate":           whiff_rate,
            "whiff_per_swing":      whiff_per_swing,
            "chase_rate":           chase_rate,
            "zone_rate":            zone_rate,
            "avg_delta_run_exp":    avg_delta_run_exp,
            "pitch_type_stats":     pitch_type_stats if pitch_type_stats else None,
            "first_pitch_mix":      first_pitch_mix,
            "count_pitch_mix":      count_pitch_mix,
        })

    return game_stats, pa_log


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def _upsert_game_stats(client: Any, records: list[dict[str, Any]]) -> tuple[int, int]:
    """Upsert into pitcher_game_stats. Returns (ok, failed)."""
    ok = failed = 0
    table = client.table("pitcher_game_stats")
    for i in range(0, len(records), _UPSERT_BATCH):
        batch = records[i: i + _UPSERT_BATCH]
        batch_no = i // _UPSERT_BATCH + 1
        try:
            table.upsert(batch, on_conflict="pitcher_id,game_pk").execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_pitcher_game_stats: game_stats batch {batch_no} FAILED: {exc}",
                flush=True,
            )
            failed += len(batch)
    return ok, failed


def _upsert_pa_log(client: Any, records: list[dict[str, Any]]) -> tuple[int, int]:
    """Upsert into pitcher_game_pa_log. Returns (ok, failed)."""
    ok = failed = 0
    table = client.table("pitcher_game_pa_log")
    for i in range(0, len(records), _UPSERT_BATCH):
        batch = records[i: i + _UPSERT_BATCH]
        batch_no = i // _UPSERT_BATCH + 1
        try:
            table.upsert(
                batch,
                on_conflict="pitcher_id,game_pk,at_bat_number",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_pitcher_game_stats: pa_log batch {batch_no} FAILED: {exc}",
                flush=True,
            )
            failed += len(batch)
    return ok, failed


# ---------------------------------------------------------------------------
# Season runner
# ---------------------------------------------------------------------------

def run_season(
    client: Any,
    season: int,
    bundle: dict[str, Any],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, int]:
    """
    Process one season (or a date range within it).
    Returns a summary dict with keys:
      games_built, game_stats_ok, game_stats_failed,
      pa_log_rows, pa_log_ok, pa_log_failed
    """
    summary = {
        "games_built": 0,
        "game_stats_ok": 0,
        "game_stats_failed": 0,
        "pa_log_rows": 0,
        "pa_log_ok": 0,
        "pa_log_failed": 0,
    }

    # -- Load pitch data --
    if start_date or end_date:
        print(
            f"calc_pitcher_game_stats: loading pitches "
            f"{start_date or '?'} .. {end_date or '?'}...",
            flush=True,
        )
        df = _load_pitches(client, start_date=start_date, end_date=end_date)
    else:
        print(f"calc_pitcher_game_stats: loading pitches for season {season}...", flush=True)
        df = _load_pitches(client, season=season)

    print(f"  {len(df)} pitch rows loaded", flush=True)
    if df.empty:
        return summary

    # -- Build records --
    game_records, pa_records = _build_game_records(df, season, bundle)
    summary["games_built"] = len(game_records)
    summary["pa_log_rows"] = len(pa_records)
    print(
        f"calc_pitcher_game_stats: {len(game_records)} game records, "
        f"{len(pa_records)} PA log rows built",
        flush=True,
    )

    # -- Upsert --
    gs_ok, gs_fail = _upsert_game_stats(client, game_records)
    pa_ok, pa_fail = _upsert_pa_log(client, pa_records)
    summary["game_stats_ok"]      = gs_ok
    summary["game_stats_failed"]  = gs_fail
    summary["pa_log_ok"]          = pa_ok
    summary["pa_log_failed"]      = pa_fail

    print(
        f"calc_pitcher_game_stats: season {season} done -- "
        f"game_stats upserted={gs_ok} failed={gs_fail}  "
        f"pa_log upserted={pa_ok} failed={pa_fail}",
        flush=True,
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Compute per-game pitcher statistics (Stuff+, outcomes, pitch mix) "
            "and write to pitcher_game_stats and pitcher_game_pa_log."
        )
    )
    p.add_argument(
        "--start-season", type=int, default=_DEFAULT_START_SEASON,
        help=f"First season (default {_DEFAULT_START_SEASON}).",
    )
    p.add_argument(
        "--end-season", type=int, default=datetime.now().year,
        help="Last season (default: current year).",
    )
    p.add_argument(
        "--date", type=str, default=None, metavar="YYYY-MM-DD",
        help=(
            "Process only this single game date.  Season is inferred from the "
            "date.  Used by the daily pipeline for incremental updates."
        ),
    )
    return p.parse_args()


def main() -> None:
    args   = _parse_args()
    bundle = _load_model()
    client = get_client()

    totals = {
        "games_built": 0,
        "game_stats_ok": 0,
        "game_stats_failed": 0,
        "pa_log_rows": 0,
        "pa_log_ok": 0,
        "pa_log_failed": 0,
    }

    if args.date:
        d      = date.fromisoformat(args.date)
        season = d.year
        print(f"calc_pitcher_game_stats: date mode -- {args.date} (season {season})")
        s = run_season(client, season, bundle, start_date=args.date, end_date=args.date)
        for k in totals:
            totals[k] += s[k]
    else:
        start_s = int(args.start_season)
        end_s   = int(args.end_season)
        if start_s > end_s:
            raise SystemExit("--start-season must be <= --end-season")
        for season in range(start_s, end_s + 1):
            print(f"\ncalc_pitcher_game_stats: processing season {season}...", flush=True)
            s = run_season(client, season, bundle)
            for k in totals:
                totals[k] += s[k]

    print(
        f"\n=== calc_pitcher_game_stats: complete ===\n"
        f"  pitcher-games built : {totals['games_built']}\n"
        f"  game_stats upserted : {totals['game_stats_ok']}\n"
        f"  game_stats failed   : {totals['game_stats_failed']}\n"
        f"  PA log rows built   : {totals['pa_log_rows']}\n"
        f"  PA log upserted     : {totals['pa_log_ok']}\n"
        f"  PA log failed       : {totals['pa_log_failed']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
