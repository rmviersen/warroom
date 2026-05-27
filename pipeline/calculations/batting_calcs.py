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
    """
    OPS+ (Baseball Reference methodology):

    ``100 × (OBP/lgOBP + SLG/lgSLG − 1) / park_factor``

    League averages ``lgOBP`` / ``lgSLG`` come from ``get_league_averages(season)``.
    ``park_factor`` defaults to ``1.0`` (neutral environment). Pass the batter's
    team park adjustment (e.g. ``park_factors.runs_factor``) when available.
    """

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

    Uses 35% exit velo, 50% barrel rate, 15% hard-hit vs league ``lgAvgEV``, ``lgBarrelRate``,
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
    return float(100.0 * (0.35 * r_ev + 0.5 * r_br + 0.15 * r_hh))


# FanGraphs guts page wOBA scale by season (https://www.fangraphs.com/guts.aspx).
_WOBA_SCALE_FG: dict[int, float] = {
    1990: 1.190,
    1991: 1.195,
    1992: 1.200,
    1993: 1.155,
    1994: 1.160,
    1995: 1.165,
    1996: 1.160,
    1997: 1.165,
    1998: 1.170,
    1999: 1.175,
    2000: 1.180,
    2001: 1.195,
    2002: 1.200,
    2003: 1.195,
    2004: 1.185,
    2005: 1.195,
    2006: 1.185,
    2007: 1.185,
    2008: 1.190,
    2009: 1.210,
    2010: 1.251,
    2011: 1.264,
    2012: 1.245,
    2013: 1.277,
    2014: 1.304,
    2015: 1.251,
    2016: 1.230,
    2017: 1.185,
    2018: 1.180,
    2019: 1.190,
    2020: 1.220,
    2021: 1.210,
    2022: 1.210,
    2023: 1.230,
    2024: 1.242,
    2025: 1.232,
    2026: 1.266,
}


def get_woba_scale(season: int) -> float:
    """FanGraphs-published wOBA scale for ``season`` (guts table)."""
    if season < 1990:
        return 1.20
    return _WOBA_SCALE_FG.get(season, 1.20)


def calc_woba_scale(lg_obp: float | None, lg_woba: float | None) -> float | None:
    if lg_obp is None or lg_woba is None:
        return None
    try:
        lo = float(lg_obp)
        lw = float(lg_woba)
    except (TypeError, ValueError):
        return None
    if lw == 0 or lo == 0:
        return None
    return float(lo / lw)


def calc_wrc_plus(
    woba: float | None,
    pa: float | None,
    season: int,
    lg_woba: float | None,
    lg_r_per_pa: float | None,
    park_factor: float = 1.0,
) -> int | None:
    """
    wRC+ (FanGraphs): league runs/PA from linear-weight wOBA baseline ``lgRperPA``.

    ``wRAA/PA = (wOBA - lgwOBA) / wOBA_scale`` using FanGraphs guts ``wOBA_scale``.
    ``numerator = wRAA/PA + lgRperPA + (lgRperPA - PF × lgRperPA)``.
    ``wRC+ = 100 × numerator / lgRperPA``.
    """
    if (
        woba is None
        or pa is None
        or lg_woba is None
        or lg_r_per_pa is None
        or park_factor is None
    ):
        return None
    try:
        w = float(woba)
        p = float(pa)
        lgw = float(lg_woba)
        lrpa = float(lg_r_per_pa)
        pf = float(park_factor)
    except (TypeError, ValueError):
        return None
    if p == 0 or lrpa == 0 or pf == 0:
        return None

    scale = get_woba_scale(season)
    wraa_per_pa = (w - lgw) / scale
    numerator = wraa_per_pa + lrpa + (lrpa - pf * lrpa)
    wrc_plus = 100.0 * numerator / lrpa
    return int(round(wrc_plus))


# Baseball-Reference-style runs vs average per 162 games by primary position (batter).
_BATTING_POSITION_ADJ_PER_162: dict[str, float] = {
    "C": 12.5,
    "SS": 7.5,
    "2B": 2.5,
    "3B": 2.5,
    "CF": 2.5,
    "LF": -7.5,
    "RF": -7.5,
    "1B": -12.5,
    "DH": -17.5,
}

_MIN_INN_FOR_POSITION = 20.0


def _weighted_position_adj_per_162(
    fielding_splits: list[dict],
    fallback_position: str,
) -> float:
    """
    Compute an innings-weighted positional adjustment (runs per 162 games).

    fielding_splits: list of dicts with keys 'position' (str) and 'inn' (float).
    Positions with inn < _MIN_INN_FOR_POSITION are excluded.
    If no qualifying innings exist, fall back to fallback_position lookup.
    """
    qualified = [
        s
        for s in fielding_splits
        if isinstance(s.get("inn"), (int, float))
        and s["inn"] >= _MIN_INN_FOR_POSITION
        and isinstance(s.get("position"), str)
    ]
    if not qualified:
        pos_key = fallback_position.strip().upper() if isinstance(fallback_position, str) else ""
        return _BATTING_POSITION_ADJ_PER_162.get(pos_key, 0.0)

    total_inn = sum(s["inn"] for s in qualified)
    if total_inn <= 0:
        pos_key = fallback_position.strip().upper() if isinstance(fallback_position, str) else ""
        return _BATTING_POSITION_ADJ_PER_162.get(pos_key, 0.0)

    weighted = sum(
        _BATTING_POSITION_ADJ_PER_162.get(s["position"].strip().upper(), 0.0) * s["inn"]
        for s in qualified
    )
    return weighted / total_inn


def calc_batting_war(
    woba: float | None,
    pa: float | None,
    g: float | None,
    fielding_splits: list[dict],
    season: int,
    lg_woba: float | None,
    lg_r: float | None,
    lg_pa: float | None,
    lg_ip: float | None,
    park_factor: float = 1.0,
    mlb_games: float = 2430,
    fallback_position: str = "",
) -> float | None:
    """
    Position-player **offensive** batting WAR (hybrid components; FanGraphs-style RPW/replacement).

    Batting runs above average (park-adjusted):
    ``(wOBA - lgwOBA) / wOBA_scale × PA / park_factor`` with guts-page ``wOBA_scale``.

    Positional adjustment: BR-style runs/162 × ``G/162``.

    Replacement runs (FanGraphs):
    ``(570 × (mlb_games/2430)) × (RPW / lg_pa) × PA``. ``mlb_games`` defaults to ``2430``
    (full season).

    Runs per win: ``RPW = 9 × (lgR/lgIP) × 1.5 + 3`` using league pitching innings ``lgIP``.

    ``WAR = (batting_runs + positional_runs + replacement_runs) / RPW``.

    **Known gaps:** (1) League quality adjustment (AL vs NL) is not applied and will be
    added when league averages are split by league. (2) Fielding and baserunning are not
    included—this is offensive value only.
    """
    if (
        woba is None
        or pa is None
        or g is None
        or lg_woba is None
        or lg_r is None
        or lg_pa is None
        or lg_ip is None
        or park_factor is None
    ):
        return None
    try:
        w, p, games, lgw, lr, lpa, lip, pf, mg = (
            float(woba),
            float(pa),
            float(g),
            float(lg_woba),
            float(lg_r),
            float(lg_pa),
            float(lg_ip),
            float(park_factor),
            float(mlb_games),
        )
    except (TypeError, ValueError):
        return None
    if p < 0 or games < 0 or lpa == 0 or lip == 0 or pf == 0:
        return None

    scale = get_woba_scale(season)
    batting_runs = (w - lgw) / scale * p / pf

    adj_162 = _weighted_position_adj_per_162(fielding_splits, fallback_position)
    positional_runs = adj_162 * (games / 162.0)

    rpw = 9.0 * (lr / lip) * 1.5 + 3.0
    if rpw == 0:
        return None
    replacement_runs = (570.0 * (mg / 2430.0)) * (rpw / lpa) * p
    war = (batting_runs + positional_runs + replacement_runs) / rpw
    return float(round(war, 1))


__all__ = [
    "calc_babip",
    "calc_batting_war",
    "calc_bb_pct",
    "calc_cqi",
    "calc_iso",
    "calc_k_pct",
    "calc_ops_plus",
    "calc_rc",
    "calc_singles",
    "calc_tb",
    "calc_woba",
    "calc_woba_scale",
    "calc_wrc_plus",
    "get_woba_scale",
]
