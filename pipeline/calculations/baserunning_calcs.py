"""Baserunning value calculations for brWPR."""

from __future__ import annotations

SPRINT_SPEED_FIRST_SEASON = 2015
"""First season with Savant sprint speed data."""

BASERUNNING_RV_FIRST_SEASON = 2016
"""
First season with Savant baserunning run-value data (``runner_runs_tot``).

From 2016 onward, ``calc_baserunning_season_metrics`` uses ``runner_runs_tot``
directly as the run input to brWPR, replacing the wSB + sprint-speed-proxy
approach.  2015 continues to use wSB + sprint speed.  Pre-2015 uses wSB only.
"""

SPRINT_RUNS_SCALE = 1.5
"""
Estimated baserunning runs per unit of sprint-speed z-score for a full-season player
(``competitive_runs`` == ``FULL_SEASON_COMPETITIVE_RUNS``).

Calibration basis: FanGraphs UBR for elite runners (top 5%, ~2 std devs) is ~5–8 runs;
1.5 × 2.0 z × 1.0 pt_scale = 3.0 runs for a 1-std-dev full-season player, ~5 runs for
a 2-std-dev player — consistent with observed UBR distributions. Adjust when
multi-year validation against known brWPR benchmarks is available.
"""

FULL_SEASON_COMPETITIVE_RUNS = 200
"""
Normalization baseline for playing-time scaling in ``calc_sprint_runs``.

Savant competitive_runs for a full-season everyday player is typically 200–300;
using a fixed baseline avoids the league average (≈100) being dragged down by
bench/part-time players and over-inflating full-season sprint run values.
"""

# Season-specific stolen-base run weights (FanGraphs guts-page approximation).
# runSB: runs gained per successful stolen base.
# runCS: runs lost per caught stealing (negative).
# 2023+ uses slightly smaller magnitudes reflecting automatic runner rules / bigger bases.
_WSB_WEIGHTS: dict[int, dict[str, float]] = {
    **{yr: {"runSB": 0.20, "runCS": -0.40} for yr in range(1990, 2023)},
    **{yr: {"runSB": 0.175, "runCS": -0.35} for yr in range(2023, 2031)},
}
_WSB_DEFAULT = {"runSB": 0.20, "runCS": -0.40}


def get_wsb_weights(season: int) -> dict[str, float]:
    """Run values per stolen-base event for ``season``."""
    return _WSB_WEIGHTS.get(season, _WSB_DEFAULT)


def calc_wsb_runs(
    sb: float | None,
    cs: float | None,
    season: int,
) -> float | None:
    """
    Stolen-base runs above zero.

    ``wSB = SB × runSB + CS × runCS`` using season-specific linear weights.
    Returns ``None`` when both inputs are missing.
    """
    if sb is None and cs is None:
        return None
    w = get_wsb_weights(season)
    sb_f = float(sb) if sb is not None else 0.0
    cs_f = float(cs) if cs is not None else 0.0
    return float(sb_f * w["runSB"] + cs_f * w["runCS"])


def calc_sprint_runs(
    sprint_speed: float | None,
    competitive_runs: float | None,
    lg_avg_speed: float,
    lg_std_speed: float,
) -> float | None:
    """
    Sprint-speed baserunning runs above average.

    Z-scores the player's sprint speed vs the season league distribution, then
    scales by playing-time (competitive_runs / FULL_SEASON_COMPETITIVE_RUNS) and
    ``SPRINT_RUNS_SCALE`` to convert to runs.

    Uses the fixed ``FULL_SEASON_COMPETITIVE_RUNS`` baseline rather than the
    season league average, which is dragged down by bench/part-time players
    and would over-inflate full-season sprint run values.

    Returns ``None`` when sprint speed is missing or league std is near zero.
    """
    if sprint_speed is None or competitive_runs is None:
        return None
    if lg_std_speed < 1e-6:
        return None
    try:
        z = (float(sprint_speed) - lg_avg_speed) / lg_std_speed
        pt_scale = float(competitive_runs) / FULL_SEASON_COMPETITIVE_RUNS
        return float(z * pt_scale * SPRINT_RUNS_SCALE)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def calc_baserunning_war(
    br_runs: float | None,
    sprint_runs: float | None,
    lg_r: float,
    lg_ip: float,
) -> float | None:
    """
    Baserunning wins above replacement (brWPR).

    Sums the primary baserunning run component (``br_runs``) and the
    sprint-speed run component (either may be ``None`` / absent), then
    divides by ``RPW = 9 × (lgR / lgIP) × 1.5 + 3``.

    ``br_runs`` meaning by era:

    * **2016+** — pass ``runner_runs_tot`` from ``statcast_baserunning_rv``
      (Statcast total: SB value + extra-bases-taken value).  Pass
      ``sprint_runs=None``; the XB component is already embedded.
    * **2015** — pass ``wsb_runs`` (stolen-base linear weights) as ``br_runs``
      and the sprint-speed z-score result as ``sprint_runs``.
    * **1990–2014** — pass ``wsb_runs`` as ``br_runs``, ``sprint_runs=None``.

    RPW convention matches ``calc_batting_war``, ``calc_pitching_war``, and
    ``calc_fielding_season_metrics``.

    Returns ``None`` when both run components are absent or RPW is unavailable.
    """
    if br_runs is None and sprint_runs is None:
        return None
    if lg_ip <= 0:
        return None
    rpw = 9.0 * (lg_r / lg_ip) * 1.5 + 3.0
    if rpw == 0:
        return None
    total_runs = (br_runs or 0.0) + (sprint_runs or 0.0)
    return float(round(total_runs / rpw, 1))


__all__ = [
    "SPRINT_SPEED_FIRST_SEASON",
    "SPRINT_RUNS_SCALE",
    "FULL_SEASON_COMPETITIVE_RUNS",
    "BASERUNNING_RV_FIRST_SEASON",
    "calc_baserunning_war",
    "calc_sprint_runs",
    "calc_wsb_runs",
    "get_wsb_weights",
]
