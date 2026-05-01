"""Fielding rates from games played / innings (see defensive columns on SCHEMA player tables)."""

from __future__ import annotations


def calc_fld_pct(po: float | None, a: float | None, e: float | None) -> float | None:
    if po is None or a is None or e is None:
        return None
    den = float(po) + float(a) + float(e)
    if den == 0:
        return None
    return float((float(po) + float(a)) / den)


def calc_rf_per_9(po: float | None, a: float | None, inn: float | None) -> float | None:
    if po is None or a is None or inn is None or inn == 0:
        return None
    return float((float(po) + float(a)) / (float(inn) / 9.0))


def calc_rf_per_g(po: float | None, a: float | None, g: float | None) -> float | None:
    if po is None or a is None or g is None or g == 0:
        return None
    return float((float(po) + float(a)) / float(g))


__all__ = [
    "calc_fld_pct",
    "calc_rf_per_9",
    "calc_rf_per_g",
]
