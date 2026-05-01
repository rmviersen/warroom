"""Batting rate stats derived from counting inputs (see ``player_batting_seasons`` in SCHEMA)."""

from __future__ import annotations

from .constants import STATCAST_MIN_SEASON, get_woba_weights
from .fetch_league_averages import get_league_averages


def calc_iso(slg: float | None, avg: float | None) -> float | None:
    if slg is None or avg is None:
        return None
    return float(slg - avg)


def calc_bb_pct(bb: float | None, pa: float | None) -> float | None:
    if bb is None or pa is None or pa == 0:
        return None
    return float(bb / pa)


def calc_k_pct(so: float | None, pa: float | None) -> float | None:
    if so is None or pa is None or pa == 0:
        return None
    return float(so / pa)


def calc_babip(
    h: float | None,
    hr: float | None,
    ab: float | None,
    so: float | None,
    sf: float | None = 0,
) -> float | None:
    if h is None or hr is None or ab is None or so is None:
        return None
    sfo = 0.0 if sf is None else float(sf)
    den = float(ab) - float(so) - float(hr) + sfo
    if den == 0:
        return None
    return float((float(h) - float(hr)) / den)


def calc_singles(
    h: float | None,
    doubles: float | None,
    triples: float | None,
    hr: float | None,
) -> float | None:
    if h is None or doubles is None or triples is None or hr is None:
        return None
    return float(h - doubles - triples - hr)


def calc_tb(
    singles: float | None,
    doubles: float | None,
    triples: float | None,
    hr: float | None,
) -> float | None:
    if singles is None or doubles is None or triples is None or hr is None:
        return None
    return float(singles + 2 * doubles + 3 * triples + 4 * hr)


def calc_woba(
    bb: float | None,
    hbp: float | None,
    singles: float | None,
    doubles: float | None,
    triples: float | None,
    hr: float | None,
    pa: float | None,
    season: int,
) -> float | None:
    if (
        bb is None
        or hbp is None
        or singles is None
        or doubles is None
        or triples is None
        or hr is None
        or pa is None
        or pa == 0
    ):
        return None
    w = get_woba_weights(season)
    num = (
        w["uBB"] * float(bb)
        + w["HBP"] * float(hbp)
        + w["single"] * float(singles)
        + w["double"] * float(doubles)
        + w["triple"] * float(triples)
        + w["HR"] * float(hr)
    )
    return float(num / float(pa))


def calc_ops_plus(
    obp: float | None,
    slg: float | None,
    season: int,
    park_factor: float = 1.0,
) -> float | None:
    if obp is None or slg is None:
        return None
    lg = get_league_averages(season)
    if lg is None:
        return None
    lg_obp = lg.get("lgOBP")
    lg_slg = lg.get("lgSLG")
    if lg_obp is None or lg_slg is None:
        return None
    try:
        lo = float(lg_obp)
        ls = float(lg_slg)
    except (TypeError, ValueError):
        return None
    if lo == 0 or ls == 0 or park_factor == 0:
        return None
    return float(100.0 * (float(obp) / lo + float(slg) / ls - 1.0) / float(park_factor))


def calc_rc(h: float | None, bb: float | None, tb: float | None, ab: float | None) -> float | None:
    if h is None or bb is None or tb is None or ab is None:
        return None
    den = float(ab) + float(bb)
    if den == 0:
        return None
    return float((float(h) + float(bb)) * float(tb) / den)


def calc_cqi(
    avg_ev: float | None,
    barrel_rate: float | None,
    hard_hit_rate: float | None,
    season: int,
) -> float | None:
    """
    Contact Quality Index: 100 = league average (``statcast_batting`` / league JSON Statcast fields).

    Uses 40% exit velo, 40% barrel rate, 20% hard-hit vs league ``lgAvgEV``, ``lgBarrelRate``,
    ``lgHardHitRate`` (same units as Savant exports in ``league_averages.json``).
    """
    if season < STATCAST_MIN_SEASON:
        return None
    if avg_ev is None or barrel_rate is None or hard_hit_rate is None:
        return None
    lg = get_league_averages(season)
    if lg is None:
        return None
    lg_ev = lg.get("lgAvgEV")
    lg_br = lg.get("lgBarrelRate")
    lg_hh = lg.get("lgHardHitRate")
    if lg_ev is None or lg_br is None or lg_hh is None:
        return None
    try:
        r_ev = float(avg_ev) / float(lg_ev)
        r_br = float(barrel_rate) / float(lg_br)
        r_hh = float(hard_hit_rate) / float(lg_hh)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return float(100.0 * (0.4 * r_ev + 0.4 * r_br + 0.2 * r_hh))


__all__ = [
    "calc_babip",
    "calc_bb_pct",
    "calc_cqi",
    "calc_iso",
    "calc_k_pct",
    "calc_ops_plus",
    "calc_rc",
    "calc_singles",
    "calc_tb",
    "calc_woba",
]
