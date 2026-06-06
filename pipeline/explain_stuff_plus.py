"""
Full step-by-step explanation of how Stuff+ is calculated for a single pitcher/pitch.
Default: Paul Skenes (694973), FF fastball.

Run from pipeline/:
    python explain_stuff_plus.py              # Skenes FF, all available seasons
    python explain_stuff_plus.py --season 2024
    python explain_stuff_plus.py --pitcher 694973 --pitch-type ST --season 2025
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np

import config  # noqa: F401
from db import get_client
from train_stuff_plus_model import PITCH_FAMILY_MAP, build_fb_maps
from weighted_knn import WeightedKNNRegressor  # noqa: F401

SEP  = "=" * 72
SEP2 = "-" * 72
MODEL_PATH = Path(__file__).parent / "models" / "stuff_plus_model.pkl"

_ARSENAL_SELECT = (
    "pitcher_id,season,pitch_type,p_throws,"
    "avg_effective_speed,avg_spin_rate,avg_spin_axis,"
    "avg_h_movement,avg_v_movement,pitches"
)


def _f(val) -> float:
    return float(val)


def explain(pitcher_id: int, pitch_type: str, season: int | None):
    client = get_client()

    # ── 1. Load model bundle ──────────────────────────────────────────────────
    with open(MODEL_PATH, "rb") as fh:
        bundle = pickle.load(fh)

    family = PITCH_FAMILY_MAP.get(pitch_type)
    if family is None:
        raise ValueError(f"Pitch type {pitch_type!r} not in PITCH_FAMILY_MAP")
    fb = bundle[family]

    print(SEP)
    print(f"  MODEL BUNDLE  v{bundle.get('version', '?')}")
    print(SEP2)
    print(f"  Pitch type : {pitch_type}  ->  family : {family}")
    print(f"  CSW  league mean : {fb['csw_league_mean']:.6f}")
    print(f"  Contact league mean : {fb['contact_league_mean']:.6f}")
    print(f"  KNN feature names  : {fb.get('feature_names', 'not stored')}")
    print()

    # ── 2. Fetch DB rows ──────────────────────────────────────────────────────
    q = (
        client.table("statcast_pitching_arsenal")
        .select(_ARSENAL_SELECT)
        .eq("pitcher_id", pitcher_id)
        .eq("pitch_type", pitch_type)
    )
    if season is not None:
        q = q.eq("season", season)
    q = q.order("season")
    res = q.execute()
    rows = res.data or []

    if not rows:
        print(f"  No rows found for pitcher={pitcher_id} pitch={pitch_type}"
              + (f" season={season}" if season else ""))
        return

    # Also fetch ALL pitch types for this pitcher (same seasons) so we can
    # build the fastball reference map for breaking/offspeed differentials.
    seasons_needed = list({r["season"] for r in rows})
    all_rows_res = (
        client.table("statcast_pitching_arsenal")
        .select(_ARSENAL_SELECT)
        .eq("pitcher_id", pitcher_id)
        .in_("season", seasons_needed)
        .execute()
    )
    all_rows = all_rows_res.data or []
    fb_eff_map, fb_v_map = build_fb_maps(all_rows)

    # ── 3. Walk through each season row ──────────────────────────────────────
    for row in rows:
        s = row["season"]
        pthr = str(row.get("p_throws", "") or "").strip().upper()

        print(SEP)
        print(f"  PITCHER {pitcher_id}   PITCH TYPE: {pitch_type}   SEASON: {s}")
        print(SEP)

        # ── 3a. Raw DB values ─────────────────────────────────────────────────
        eff_speed  = float(row["avg_effective_speed"])  if row["avg_effective_speed"]  is not None else None
        spin_rate  = float(row["avg_spin_rate"])        if row["avg_spin_rate"]         is not None else None
        spin_axis  = float(row["avg_spin_axis"])        if row["avg_spin_axis"]         is not None else None
        h_mov      = float(row["avg_h_movement"])       if row["avg_h_movement"]        is not None else None
        v_mov      = float(row["avg_v_movement"])       if row["avg_v_movement"]        is not None else None
        pitches    = int(row["pitches"])                if row["pitches"]               is not None else None

        print("  RAW DB VALUES  (from statcast_pitching_arsenal)")
        print(SEP2)
        print(f"  pitcher_id           : {pitcher_id}")
        print(f"  season               : {s}")
        print(f"  pitch_type           : {pitch_type}")
        print(f"  p_throws             : {pthr}")
        print(f"  pitches              : {pitches}")
        print(f"  avg_effective_speed  : {eff_speed}")
        print(f"  avg_spin_rate        : {spin_rate}")
        print(f"  avg_spin_axis        : {spin_axis}")
        print(f"  avg_h_movement       : {h_mov}  (pfx_x inches, +ve = glove side)")
        print(f"  avg_v_movement       : {v_mov}  (pfx_z inches, relative to gravity)")
        print()

        if any(v is None for v in (eff_speed, spin_rate, spin_axis, h_mov, v_mov)):
            print("  !! One or more required features is NULL — row would be SKIPPED !!")
            continue

        # ── 3b. Feature engineering ───────────────────────────────────────────
        # positive = arm-side run, negative = glove-side run
        # RHP: pfx_x negative for arm-side -> negate to make positive
        # LHP: pfx_x positive for arm-side -> keep as-is
        arm_side = -h_mov if pthr == "R" else h_mov

        print("  FEATURE ENGINEERING")
        print(SEP2)
        print(f"  p_throws = {pthr!r}  (handedness NOT a separate feature)")
        print()
        print(f"  arm_side_movement (sign convention: +ve = arm-side, -ve = glove-side):")
        print(f"    raw avg_h_movement = {h_mov:.4f} feet")
        if pthr == "R":
            print(f"    pitcher is RHP -> pfx_x is negative for arm-side -> negate: "
                  f"arm_side = -({h_mov:.4f}) = {arm_side:.4f}")
        else:
            print(f"    pitcher is LHP -> pfx_x is positive for arm-side -> keep: "
                  f"arm_side = {arm_side:.4f}")
        print(f"    result: {arm_side:+.4f}  "
              f"({'arm-side run' if arm_side > 0 else 'glove-side break'})")
        print()

        feat = [eff_speed, spin_rate, spin_axis, arm_side, v_mov]
        feat_labels = [
            "avg_effective_speed",
            "avg_spin_rate",
            "avg_spin_axis",
            "arm_side_movement",
            "avg_v_movement",
        ]

        if family != "fastball":
            key = (pitcher_id, pthr)
            fb_es = fb_eff_map.get(key)
            fb_vz = fb_v_map.get(key)
            velo_diff    = (fb_es - eff_speed) if fb_es is not None else 0.0
            v_break_diff = (fb_vz - v_mov)     if fb_vz is not None else 0.0
            feat.extend([velo_diff, v_break_diff])
            feat_labels.extend(["velo_diff_vs_fb", "v_break_diff_vs_fb"])
            print(f"  Differential features (vs pitcher's own fastball):")
            print(f"    fastball eff_speed for ({pitcher_id}, {pthr}) = "
                  f"{fb_es if fb_es is not None else 'NOT FOUND (using 0)'}")
            print(f"    fastball v_movement for ({pitcher_id}, {pthr}) = "
                  f"{fb_vz if fb_vz is not None else 'NOT FOUND (using 0)'}")
            print(f"    velo_diff    = fb_eff_speed - this_eff_speed = "
                  f"{fb_es:.4f} - {eff_speed:.4f} = {velo_diff:.4f}")
            print(f"    v_break_diff = fb_v_mov - this_v_mov = "
                  f"{fb_vz:.4f} - {v_mov:.4f} = {v_break_diff:.4f}")
            print()

        print("  FEATURE VECTOR  (pre-scaling)")
        print(SEP2)
        for label, val in zip(feat_labels, feat):
            print(f"    {label:<28} {val:.6f}")
        print()

        # ── 3c. StandardScaler transform ─────────────────────────────────────
        scaler = fb["scaler"]
        X_raw = np.array([feat], dtype=np.float64)
        X_scaled = scaler.transform(X_raw)

        print("  STANDARDSCALER TRANSFORM  (x_scaled = (x - mean) / std)")
        print(SEP2)
        print(f"  {'Feature':<28}  {'Raw':>10}  {'Mean':>10}  {'Std':>10}  {'Scaled':>10}")
        print(f"  {'-'*28}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*10}")
        for i, label in enumerate(feat_labels):
            raw_val    = feat[i]
            mean_val   = scaler.mean_[i]
            std_val    = scaler.scale_[i]
            scaled_val = X_scaled[0][i]
            print(f"  {label:<28}  {raw_val:>10.4f}  {mean_val:>10.4f}  "
                  f"{std_val:>10.4f}  {scaled_val:>10.4f}")
        print()

        # ── 3d. KNN predictions ───────────────────────────────────────────────
        raw_csw     = float(fb["csw_knn"].predict(X_scaled)[0])
        raw_contact = float(fb["contact_knn"].predict(X_scaled)[0])

        print("  KNN PREDICTIONS")
        print(SEP2)
        print(f"  The model finds the K nearest neighbours in the training set")
        print(f"  (pitches with similar features) and returns their weighted mean.")
        print()
        print(f"  CSW KNN  predicted CSW rate      : {raw_csw:.6f}  "
              f"({raw_csw*100:.2f}%)")
        print(f"  Contact KNN  predicted contact wOBA: {raw_contact:.6f}")
        print()

        # ── 3e. Score calculation ─────────────────────────────────────────────
        csw_lg  = fb["csw_league_mean"]
        con_lg  = fb["contact_league_mean"]

        csw_score     = (raw_csw   / max(csw_lg, 1e-6)) * 100.0
        contact_score_raw = (max(con_lg, 0.01) / max(raw_contact, 0.01)) * 100.0
        contact_score = min(contact_score_raw, 200.0)
        capped        = contact_score < contact_score_raw

        stuff_plus = round(csw_score * 0.75 + contact_score * 0.25, 4)

        print("  SCORE CALCULATION")
        print(SEP2)
        print("  csw_score = (predicted_csw / league_csw_mean) * 100")
        print(f"            = ({raw_csw:.6f} / {csw_lg:.6f}) * 100")
        print(f"            = {raw_csw/csw_lg:.6f} * 100")
        print(f"            = {csw_score:.4f}")
        print()
        print("  contact_score = (league_contact_woba / predicted_contact_woba) * 100")
        print(f"                = ({con_lg:.6f} / {raw_contact:.6f}) * 100")
        print(f"                = {con_lg/raw_contact:.6f} * 100")
        print(f"                = {contact_score_raw:.4f}",
              "  [CAPPED at 200]" if capped else "  (no cap needed)")
        print(f"  contact_score (after cap) = {contact_score:.4f}")
        print()
        print("  stuff_plus = csw_score * 0.75 + contact_score * 0.25")
        print(f"             = {csw_score:.4f} * 0.75 + {contact_score:.4f} * 0.25")
        print(f"             = {csw_score*0.75:.4f} + {contact_score*0.25:.4f}")
        print(f"             = {stuff_plus:.4f}")
        print()

        # ── 3f. Final values ──────────────────────────────────────────────────
        print("  FINAL VALUES")
        print(SEP2)
        print(f"  stuff_plus_pitch  (stored in statcast_pitching_arsenal) : {stuff_plus:.4f}")
        print(f"  Interpretation: Skenes's {pitch_type} generates strikeouts/whiffs and")
        print(f"  suppresses contact at  {stuff_plus:.1f}%  of league average.")
        print(f"  (100 = league avg, 115 = 15% better than average)")
        print()

        # ── 3g. Rollup context ────────────────────────────────────────────────
        # Fetch all pitch types for this season so we can show the rollup math
        rollup_rows_res = (
            client.table("statcast_pitching_arsenal")
            .select("pitch_type,pitches")
            .select("pitch_type,pitches")
            .eq("pitcher_id", pitcher_id)
            .eq("season", s)
            .not_.is_("pitches", "null")
            .execute()
        )
        # Fetch the stored pitch-level scores too
        scores_res = (
            client.table("statcast_pitching_arsenal")
            .select("pitch_type,stuff_plus_pitch,pitches")
            .eq("pitcher_id", pitcher_id)
            .eq("season", s)
            .not_.is_("stuff_plus_pitch", "null")
            .execute()
        )

        score_map = {r["pitch_type"]: (float(r["stuff_plus_pitch"]), int(r["pitches"] or 0))
                     for r in (scores_res.data or [])}

        if score_map:
            total_pitches = sum(v[1] for v in score_map.values())
            wsum = sum(v[0] * v[1] for v in score_map.values())
            rollup = round(wsum / total_pitches, 4) if total_pitches > 0 else None

            print("  SEASON ROLLUP  (how pitch-level scores combine into overall stuff_plus)")
            print(SEP2)
            print(f"  {'Pitch':<6}  {'Stuff+':>8}  {'Pitches':>8}  {'Weight%':>8}  {'Contribution':>12}")
            print(f"  {'-----':<6}  {'------':>8}  {'-------':>8}  {'-------':>8}  {'------------':>12}")
            for pt, (sc, np_) in sorted(score_map.items(), key=lambda x: -x[1][1]):
                w = np_ / total_pitches * 100
                contrib = sc * (np_ / total_pitches)
                marker = " << this pitch" if pt == pitch_type else ""
                print(f"  {pt:<6}  {sc:>8.4f}  {np_:>8}  {w:>7.1f}%  {contrib:>12.4f}{marker}")
            print(f"  {'TOTAL':<6}  {'':>8}  {total_pitches:>8}  {'100.0%':>8}  {wsum/total_pitches:>12.4f}")
            print()
            print(f"  Overall stuff_plus (weighted avg) = {rollup}")

            # Compare with stored value
            sp_res = (
                client.table("statcast_pitching")
                .select("stuff_plus")
                .eq("pitcher_id", pitcher_id)
                .eq("season", s)
                .execute()
            )
            stored_overall = None
            if sp_res.data:
                stored_overall = sp_res.data[0].get("stuff_plus")
            print(f"  Stored in statcast_pitching.stuff_plus  = {stored_overall}")

            pps_res = (
                client.table("player_pitching_seasons")
                .select("stuff_plus")
                .eq("player_id", pitcher_id)
                .eq("season", s)
                .execute()
            )
            stored_pps = None
            if pps_res.data:
                stored_pps = pps_res.data[0].get("stuff_plus")
            print(f"  Stored in player_pitching_seasons.stuff_plus = {stored_pps}")
            print(f"  (leaderboard + player page both read player_pitching_seasons)")
        print()


def main():
    p = argparse.ArgumentParser(description="Explain Stuff+ calculation step by step.")
    p.add_argument("--pitcher",    type=int,   default=694973,  help="MLBAM pitcher ID")
    p.add_argument("--pitch-type", type=str,   default="FF",    help="Pitch type (FF, ST, ...)")
    p.add_argument("--season",     type=int,   default=None,    help="Season (omit for all)")
    args = p.parse_args()

    explain(
        pitcher_id=args.pitcher,
        pitch_type=args.pitch_type.upper(),
        season=args.season,
    )


if __name__ == "__main__":
    main()
