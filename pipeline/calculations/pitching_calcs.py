"""Pitching rate stats (``player_pitching_seasons`` + league lines in SCHEMA / league JSON)."""

from __future__ import annotations

from .constants import STATCAST_MIN_SEASON, get_fip_constant
from .fetch_league_averages import get_league_averages

_LG_HORIZONTAL_MOVEMENT_IN = 7.5
_LG_VERTICAL_MOVEMENT_IN = 8.0


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


def calc_fip(hr: float | None, bb: float | None, so: float | None, ip: float | None, season: int) -> float | None:
    if hr is None or bb is None or so is None or ip is None or ip == 0:
        return None
    c = get_fip_constant(season)
    if c is None:
        return None
    core = (13.0 * float(hr) + 3.0 * float(bb) - 2.0 * float(so)) / float(ip)
    return float(core + c)


def calc_era_plus(era: float | None, season: int, park_factor: float = 1.0) -> float | None:
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
    except (TypeError, ValueError):
        return None
    return float(100.0 * (le / e) * float(park_factor))


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
    season: int,
) -> float | None:
    """
    Stuff+ style index: 100 = league average velo/spin (``lgAvgVelo``, ``lgAvgSpinRate``) with
    fixed league movement baselines (7.5 in. horizontal, 8.0 in. vertical), weights 40/30/15/15.
    """
    if season < STATCAST_MIN_SEASON:
        return None
    if velo is None or spin_rate is None or h_movement is None or v_movement is None:
        return None
    lg = get_league_averages(season)
    if lg is None:
        return None
    lg_v = lg.get("lgAvgVelo")
    lg_s = lg.get("lgAvgSpinRate")
    if lg_v is None or lg_s is None:
        return None
    try:
        r_v = float(velo) / float(lg_v)
        r_s = float(spin_rate) / float(lg_s)
        r_h = abs(float(h_movement)) / _LG_HORIZONTAL_MOVEMENT_IN
        r_z = abs(float(v_movement)) / _LG_VERTICAL_MOVEMENT_IN
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return float(100.0 * (0.4 * r_v + 0.3 * r_s + 0.15 * r_h + 0.15 * r_z))


__all__ = [
    "calc_bb_per_9",
    "calc_era_plus",
    "calc_fip",
    "calc_hr_per_9",
    "calc_k_bb",
    "calc_k_per_9",
    "calc_lob_pct",
    "calc_stuff_plus",
    "calc_whip",
]
