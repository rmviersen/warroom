"""Pitching rate stats (``player_pitching_seasons`` + league lines in SCHEMA / league JSON)."""

from __future__ import annotations

from .constants import get_fip_constant
from .fetch_league_averages import get_league_averages


def calc_k_per_9(so: float | None, ip: float | None) -> float | None:
    if so is None or ip is None or ip == 0:
        return None
    return float((float(so) / float(ip)) * 9.0)


def calc_bb_per_9(bb: float | None, ip: float | None) -> float | None:
    if bb is None or ip is None or ip == 0:
        return None
    return float((float(bb) / float(ip)) * 9.0)


def calc_hr_per_9(hr: float | None, ip: float | None) -> float | None:
    if hr is None or ip is None or ip == 0:
        return None
    return float((float(hr) / float(ip)) * 9.0)


def calc_k_bb(so: float | None, bb: float | None) -> float | None:
    if so is None or bb is None or bb == 0:
        return None
    return float(float(so) / float(bb))


def calc_whip(h: float | None, bb: float | None, ip: float | None) -> float | None:
    if h is None or bb is None or ip is None or ip == 0:
        return None
    return float((float(h) + float(bb)) / float(ip))


def calc_fip(
    hr: float | None,
    bb: float | None,
    so: float | None,
    ip: float | None,
    season: int,
    *,
    fip_constant_override: float | None = None,
) -> float | None:
    if hr is None or bb is None or so is None or ip is None or ip == 0:
        return None
    if fip_constant_override is not None:
        c = float(fip_constant_override)
    else:
        c_inner = get_fip_constant(season)
        if c_inner is None:
            return None
        c = float(c_inner)
    core = (13.0 * float(hr) + 3.0 * float(bb) - 2.0 * float(so)) / float(ip)
    return float(core + c)


def calc_era_plus(era: float | None, season: int, park_factor: float = 1.0) -> float | None:
    """
    ERA+ (Baseball Reference): ``100 × (lgERA / ERA) / park_factor``.

    ``lgERA`` comes from ``get_league_averages(season)``. Divide by ``park_factor`` so a pitcher in a
    hitter-friendly (inflated ERA) park gets credit versus multiplying, which would wrongly penalize them.
    """
    if era is None or era == 0:
        return None
    lg = get_league_averages(season)
    if lg is None:
        return None
    lg_era = lg.get("lgERA")
    if lg_era is None:
        return None
    try:
        le = float(lg_era)
        e = float(era)
        pf = float(park_factor)
    except (TypeError, ValueError):
        return None
    if pf == 0:
        return None
    return float(100.0 * (le / e) / pf)


def calc_era_plus_with_lg(
    era: float | None, lg_era: float | None, park_factor: float = 1.0
) -> float | None:
    """ERA+ using supplied league ERA (warehouse); ``100 × (lgERA / ERA) / park_factor``."""

    if era is None or era == 0 or lg_era is None:
        return None
    try:
        le = float(lg_era)
        e = float(era)
        pf = float(park_factor)
    except (TypeError, ValueError):
        return None
    if pf == 0:
        return None
    return float(100.0 * (le / e) / pf)


def calc_pitching_war(
    ip: float | None,
    fip: float | None,
    lg_fip: float | None,
    lg_r: float | None,
    lg_pa: float | None,
    lg_ip: float | None,
    *,
    park_factor: float = 1.0,
    mlb_games: float = 2430.0,
) -> float | None:
    """
    **Pitching** wins above replacement (simplified Fangraphs-style).

    Runs above league average pitcher on a FIP rate basis:
    ``(lgFIP - FIP) / 9 × IP / park_factor``.

    Runs per win: ``RPW = 9 × (lgR / lgIP) × 1.5 + 3`` (runs / IP here are league totals).

    Replacement runs use **1000** as the pitcher replacement constant (Fangraphs-style:
    marginal runs allocated to pitchers league-wide versus **570** for position players /
    batting). Formula:
    ``(1000 × (mlb_games/2430)) × (RPW / lg_pa) × BF_proxy`` where ``BF_proxy = (lg_pa / lg_IP) × IP``.

    ``WAR_pitch = (RAA_FIP + replacement_runs) / RPW``.
    """

    if (
        ip is None
        or fip is None
        or lg_fip is None
        or lg_r is None
        or lg_pa is None
        or lg_ip is None
        or park_factor is None
    ):
        return None
    try:
        lip = float(ip)
        f = float(fip)
        lgf = float(lg_fip)
        lr = float(lg_r)
        lpa = float(lg_pa)
        lgi = float(lg_ip)
        pf = float(park_factor)
        mg = float(mlb_games)
    except (TypeError, ValueError):
        return None
    if lip <= 0 or lgi == 0 or lpa == 0 or pf == 0:
        return None

    rpw = 9.0 * (lr / lgi) * 1.5 + 3.0
    if rpw == 0:
        return None

    raa_fip = (lgf - f) / 9.0 * lip / pf
    bf_proxy = (lpa / lgi) * lip
    replacement_runs = (1000.0 * (mg / 2430.0)) * (rpw / lpa) * bf_proxy
    pwarp = (raa_fip + replacement_runs) / rpw
    return float(round(pwarp, 1))


def calc_lob_pct(h: float | None, bb: float | None, hr: float | None, r: float | None) -> float | None:
    if h is None or bb is None or hr is None or r is None:
        return None
    den = float(h) + float(bb) - 1.4 * float(hr)
    if den == 0:
        return None
    return float((float(h) + float(bb) - float(r)) / den)


def calc_stuff_plus(
    velo: float | None,
    spin_rate: float | None,
    h_movement: float | None,
    v_movement: float | None,
    lg_velo: float | None,
    lg_spin_rate: float | None,
    lg_h_movement: float | None,
    lg_v_movement: float | None,
) -> float | None:
    """
    Stuff+ style index for one pitch type: **100** = league average for that pitch type
    (given the league baselines supplied).

    Each pitcher metric is compared to the caller-provided league line (e.g. from
    ``league_pitch_type_averages``). Ratios: ``velo/lg_velo``, ``spin_rate/lg_spin_rate``;
    horizontal and vertical movement use ``abs(pitcher) / abs(league)`` so sign does not
    depend on handedness or break direction. Weights: velo 40%, spin 30%, h-movement 15%,
    v-movement 15%. Formula: ``100 × (0.4×r_v + 0.3×r_s + 0.15×r_h + 0.15×r_z)``.
    """
    if (
        velo is None
        or spin_rate is None
        or h_movement is None
        or v_movement is None
        or lg_velo is None
        or lg_spin_rate is None
        or lg_h_movement is None
        or lg_v_movement is None
    ):
        return None
    try:
        lv = float(lg_velo)
        ls = float(lg_spin_rate)
        lh = float(lg_h_movement)
        lz = float(lg_v_movement)
    except (TypeError, ValueError):
        return None
    if lv == 0 or ls == 0 or lh == 0 or lz == 0:
        return None
    try:
        r_v = float(velo) / lv
        r_s = float(spin_rate) / ls
        r_h = abs(float(h_movement)) / abs(lh)
        r_z = abs(float(v_movement)) / abs(lz)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return float(100.0 * (0.4 * r_v + 0.3 * r_s + 0.15 * r_h + 0.15 * r_z))


__all__ = [
    "calc_bb_per_9",
    "calc_era_plus",
    "calc_era_plus_with_lg",
    "calc_fip",
    "calc_hr_per_9",
    "calc_k_bb",
    "calc_k_per_9",
    "calc_lob_pct",
    "calc_pitching_war",
    "calc_stuff_plus",
    "calc_whip",
]
