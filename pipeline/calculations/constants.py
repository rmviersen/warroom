"""League context helpers and re-exports aligned with ``SCHEMA.md`` / ``league_averages.json``."""

from __future__ import annotations

from db import get_client

from .fetch_league_averages import (
    get_league_averages,
    get_woba_weights,
)

STATCAST_MIN_SEASON = 2015
"""First season with Statcast-quality league rows in ``league_averages.json`` (see SCHEMA)."""

NEUTRAL_PARK_FACTOR = 1.0
"""Fallback when Supabase is unavailable or ``(team_id, season)`` is missing from cache."""

_PARK_PAGE = 1000
_PARK_FACTORS_BY_TEAM_SEASON: dict[tuple[int, int], float] = {}


def _load_park_factors_from_supabase() -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], float] = {}
    try:
        client = get_client()
    except Exception:
        return out

    offset = 0
    while True:
        try:
            resp = (
                client.table("park_factors")
                .select("team_id,season,runs_factor")
                .range(offset, offset + _PARK_PAGE - 1)
                .execute()
            )
        except Exception:
            break
        rows = resp.data or []
        for row in rows:
            tid = row.get("team_id")
            sea = row.get("season")
            rf = row.get("runs_factor")
            if tid is None or sea is None or rf is None:
                continue
            try:
                out[(int(tid), int(sea))] = float(rf)
            except (TypeError, ValueError):
                continue
        if len(rows) < _PARK_PAGE:
            break
        offset += _PARK_PAGE
    return out


try:
    _PARK_FACTORS_BY_TEAM_SEASON = _load_park_factors_from_supabase()
except Exception:
    _PARK_FACTORS_BY_TEAM_SEASON = {}


def refresh_park_factors_cache() -> None:
    """Reload ``park_factors.runs_factor`` from Supabase (e.g. after a long ETL updates the table)."""

    global _PARK_FACTORS_BY_TEAM_SEASON
    try:
        _PARK_FACTORS_BY_TEAM_SEASON = _load_park_factors_from_supabase()
    except Exception:
        _PARK_FACTORS_BY_TEAM_SEASON = {}


def get_park_factor(team_id: int, season: int) -> float:
    """
    Run environment multiplier from ``park_factors.runs_factor`` for ``team_id`` / ``season``.

    Returns ``NEUTRAL_PARK_FACTOR`` when the key is missing or ids are invalid.
    """
    try:
        tid = int(team_id)
        sea = int(season)
    except (TypeError, ValueError):
        return float(NEUTRAL_PARK_FACTOR)
    v = _PARK_FACTORS_BY_TEAM_SEASON.get((tid, sea))
    if v is None:
        return float(NEUTRAL_PARK_FACTOR)
    return float(v)


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
    "NEUTRAL_PARK_FACTOR",
    "get_fip_constant",
    "get_park_factor",
    "get_woba_weights",
    "refresh_park_factors_cache",
]
