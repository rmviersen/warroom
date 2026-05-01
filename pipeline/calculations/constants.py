"""League context helpers and re-exports aligned with ``SCHEMA.md`` / ``league_averages.json``."""

from __future__ import annotations

from .fetch_league_averages import (
    get_league_averages,
    get_park_factor,
    get_woba_weights,
)

STATCAST_MIN_SEASON = 2015
"""First season with Statcast-quality league rows in ``league_averages.json`` (see SCHEMA)."""


def get_fip_constant(season: int) -> float | None:
    """
    League FIP constant ``FIP_constant`` for ``season`` (ERA minus FIP core term at league rates).

    Sourced from ``get_league_averages`` / ``league_averages.json`` pitching aggregates.
    """
    row = get_league_averages(season)
    if row is None:
        return None
    c = row.get("FIP_constant")
    if c is None:
        return None
    try:
        return float(c)
    except (TypeError, ValueError):
        return None


__all__ = [
    "STATCAST_MIN_SEASON",
    "get_fip_constant",
    "get_park_factor",
    "get_woba_weights",
]
