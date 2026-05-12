"""
Compute Tier 1 / Tier 2 park factors from ``game_logs`` and upsert ``park_factors``.

Uses only rows with status ``Final`` or ``Completed Early``. Season year is taken
from ``game_date``. ``home_team_id`` / ``away_team_id`` identify the franchise.

Single-season factors use **league adjustment**, then **mean regression** toward
1.0: ``(raw × home_games + 50) / (home_games + 50)`` on each factor, then
multi-year averaging as before.

See SCHEMA.md for column definitions and ``park_factors_team_season`` upsert key.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import config  # noqa: F401 — load .env via side effect
from db import get_client

ALLOWED_STATUS = frozenset({"Final", "Completed Early"})
_PAGE_SIZE = 1000
_BATCH_UPSERT = 200
_LOOKBACK = 3

# Metric key -> RawSeasonFactors attribute name for the factor column.
_METRIC_TO_FACTOR_ATTR: tuple[tuple[str, str], ...] = (
    ("runs", "runs_factor"),
    ("hr", "hr_factor"),
    ("hits", "hits_factor"),
    ("singles", "singles_factor"),
    ("doubles", "doubles_factor"),
    ("triples", "triples_factor"),
    ("bb", "bb_factor"),
    ("so", "so_factor"),
)


@dataclass
class SeasonAgg:
    """Per (team_id, season) counting aggregates before rate/factor math."""

    home_games: int = 0
    home_rs: int = 0
    home_ra: int = 0
    away_games: int = 0
    away_rs: int = 0
    away_ra: int = 0

    home_hr_sum: int = 0
    home_hr_n: int = 0
    away_hr_sum: int = 0
    away_hr_n: int = 0

    home_hits_sum: int = 0
    home_hits_n: int = 0
    away_hits_sum: int = 0
    away_hits_n: int = 0

    home_singles_sum: int = 0
    home_singles_n: int = 0
    away_singles_sum: int = 0
    away_singles_n: int = 0

    home_doubles_sum: int = 0
    home_doubles_n: int = 0
    away_doubles_sum: int = 0
    away_doubles_n: int = 0

    home_triples_sum: int = 0
    home_triples_n: int = 0
    away_triples_sum: int = 0
    away_triples_n: int = 0

    home_bb_sum: int = 0
    home_bb_n: int = 0
    away_bb_sum: int = 0
    away_bb_n: int = 0

    home_so_sum: int = 0
    home_so_n: int = 0
    away_so_sum: int = 0
    away_so_n: int = 0


@dataclass
class SeasonRates:
    """Per team-season: denominator-safe totals plus (home, away) rates per stat."""

    home_games: int
    away_games: int
    home_rs: int
    home_ra: int
    away_rs: int
    away_ra: int
    rates: dict[str, tuple[float | None, float | None]]


@dataclass
class RawSeasonFactors:
    """League-adjusted + mean-regressed single-season factors (before multi-year averaging)."""

    home_games: int
    away_games: int
    home_rs: int
    home_ra: int
    away_rs: int
    away_ra: int

    runs_factor: float | None
    hr_factor: float | None
    hits_factor: float | None
    singles_factor: float | None
    doubles_factor: float | None
    triples_factor: float | None
    bb_factor: float | None
    so_factor: float | None


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


def _season_year(game_date: Any) -> int | None:
    if game_date is None:
        return None
    if isinstance(game_date, str) and len(game_date) >= 4:
        try:
            return int(game_date[:4])
        except ValueError:
            return None
    if hasattr(game_date, "year"):
        return int(game_date.year)
    return None


def _lg_adjusted_factor(
    team_home: float | None,
    team_away: float | None,
    lg_home: float | None,
    lg_away: float | None,
) -> float | None:
    """(team_h / lg_h) / (team_a / lg_a); None if any input missing or invalid."""

    if (
        team_home is None
        or team_away is None
        or lg_home is None
        or lg_away is None
    ):
        return None
    if lg_home <= 0 or lg_away <= 0 or team_away <= 0:
        return None
    return (team_home / lg_home) / (team_away / lg_away)


def _add_pair_stat(
    home_val: int | None,
    away_val: int | None,
    sum_attr: str,
    n_attr: str,
    bucket: SeasonAgg,
) -> None:
    if home_val is None and away_val is None:
        return
    if home_val is None or away_val is None:
        return
    total = home_val + away_val
    setattr(bucket, sum_attr, getattr(bucket, sum_attr) + total)
    setattr(bucket, n_attr, getattr(bucket, n_attr) + 1)


def _ingest_game(home_id: int, away_id: int, season: int, row: dict[str, Any]) -> None:
    """Update global _AGG for home and away franchises."""

    hs = _safe_int(row.get("home_score"))
    aw = _safe_int(row.get("away_score"))
    scores_ok = hs is not None and aw is not None

    for tid, is_home in ((home_id, True), (away_id, False)):
        key = (tid, season)
        if key not in _AGG:
            _AGG[key] = SeasonAgg()
        b = _AGG[key]
        if is_home:
            if scores_ok:
                b.home_games += 1
                b.home_rs += hs
                b.home_ra += aw
            _add_pair_stat(
                _safe_int(row.get("home_hr")),
                _safe_int(row.get("away_hr")),
                "home_hr_sum",
                "home_hr_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_hits")),
                _safe_int(row.get("away_hits")),
                "home_hits_sum",
                "home_hits_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_singles")),
                _safe_int(row.get("away_singles")),
                "home_singles_sum",
                "home_singles_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_doubles")),
                _safe_int(row.get("away_doubles")),
                "home_doubles_sum",
                "home_doubles_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_triples")),
                _safe_int(row.get("away_triples")),
                "home_triples_sum",
                "home_triples_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_bb")),
                _safe_int(row.get("away_bb")),
                "home_bb_sum",
                "home_bb_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_so")),
                _safe_int(row.get("away_so")),
                "home_so_sum",
                "home_so_n",
                b,
            )
        else:
            if scores_ok:
                b.away_games += 1
                b.away_rs += aw
                b.away_ra += hs
            _add_pair_stat(
                _safe_int(row.get("home_hr")),
                _safe_int(row.get("away_hr")),
                "away_hr_sum",
                "away_hr_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_hits")),
                _safe_int(row.get("away_hits")),
                "away_hits_sum",
                "away_hits_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_singles")),
                _safe_int(row.get("away_singles")),
                "away_singles_sum",
                "away_singles_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_doubles")),
                _safe_int(row.get("away_doubles")),
                "away_doubles_sum",
                "away_doubles_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_triples")),
                _safe_int(row.get("away_triples")),
                "away_triples_sum",
                "away_triples_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_bb")),
                _safe_int(row.get("away_bb")),
                "away_bb_sum",
                "away_bb_n",
                b,
            )
            _add_pair_stat(
                _safe_int(row.get("home_so")),
                _safe_int(row.get("away_so")),
                "away_so_sum",
                "away_so_n",
                b,
            )


_AGG: dict[tuple[int, int], SeasonAgg] = {}


def _pair_rate(sum_h: int, n_h: int, sum_a: int, n_a: int) -> tuple[float | None, float | None]:
    h_r = float(sum_h) / n_h if n_h > 0 else None
    a_r = float(sum_a) / n_a if n_a > 0 else None
    return h_r, a_r


def _agg_to_season_rates(a: SeasonAgg) -> SeasonRates:
    hg, ag = a.home_games, a.away_games
    h_rs, h_ra = a.home_rs, a.home_ra
    aws, ara = a.away_rs, a.away_ra
    runs_h = float(h_rs + h_ra) / hg if hg > 0 else None
    runs_a = float(aws + ara) / ag if ag > 0 else None
    rates: dict[str, tuple[float | None, float | None]] = {
        "runs": (runs_h, runs_a),
        "hr": _pair_rate(a.home_hr_sum, a.home_hr_n, a.away_hr_sum, a.away_hr_n),
        "hits": _pair_rate(
            a.home_hits_sum,
            a.home_hits_n,
            a.away_hits_sum,
            a.away_hits_n,
        ),
        "singles": _pair_rate(
            a.home_singles_sum,
            a.home_singles_n,
            a.away_singles_sum,
            a.away_singles_n,
        ),
        "doubles": _pair_rate(
            a.home_doubles_sum,
            a.home_doubles_n,
            a.away_doubles_sum,
            a.away_doubles_n,
        ),
        "triples": _pair_rate(
            a.home_triples_sum,
            a.home_triples_n,
            a.away_triples_sum,
            a.away_triples_n,
        ),
        "bb": _pair_rate(
            a.home_bb_sum,
            a.home_bb_n,
            a.away_bb_sum,
            a.away_bb_n,
        ),
        "so": _pair_rate(
            a.home_so_sum,
            a.home_so_n,
            a.away_so_sum,
            a.away_so_n,
        ),
    }
    return SeasonRates(
        home_games=hg,
        away_games=ag,
        home_rs=h_rs,
        home_ra=h_ra,
        away_rs=aws,
        away_ra=ara,
        rates=rates,
    )


def _league_rate_averages_by_season(
    rates_map: dict[tuple[int, int], SeasonRates],
) -> dict[int, dict[str, tuple[float | None, float | None]]]:
    """Per calendar season, mean home rate and mean away rate per metric."""

    seasons = {s for (_, s) in rates_map}
    out: dict[int, dict[str, tuple[float | None, float | None]]] = {}
    for S in seasons:
        per_m: dict[str, tuple[float | None, float | None]] = {}
        for mkey, _ in _METRIC_TO_FACTOR_ATTR:
            homes: list[float] = []
            aways: list[float] = []
            for (_tid, y), sr in rates_map.items():
                if y != S:
                    continue
                th, ta = sr.rates[mkey]
                if th is not None:
                    homes.append(th)
                if ta is not None:
                    aways.append(ta)
            lg_h = sum(homes) / len(homes) if homes else None
            lg_a = sum(aways) / len(aways) if aways else None
            per_m[mkey] = (lg_h, lg_a)
        out[S] = per_m
    return out


def _regress_factor_toward_neutral(
    raw_factor: float | None,
    home_games: int,
) -> float | None:
    """Shrink small-sample factors toward 1.0: ``(raw × g + 50) / (g + 50)``."""

    if raw_factor is None:
        return None
    g = float(home_games)
    return (float(raw_factor) * g + 1.0 * 50.0) / (g + 50.0)


def _season_rates_to_raw_factors(
    sr: SeasonRates,
    league_row: dict[str, tuple[float | None, float | None]],
) -> RawSeasonFactors:
    """League-relative adjustment, then mean regression toward 1.0 (``home_games`` weight)."""

    kw: dict[str, Any] = {
        "home_games": sr.home_games,
        "away_games": sr.away_games,
        "home_rs": sr.home_rs,
        "home_ra": sr.home_ra,
        "away_rs": sr.away_rs,
        "away_ra": sr.away_ra,
    }
    g = sr.home_games
    for mkey, attr in _METRIC_TO_FACTOR_ATTR:
        th, ta = sr.rates[mkey]
        lg_h, lg_a = league_row[mkey]
        adj = _lg_adjusted_factor(th, ta, lg_h, lg_a)
        kw[attr] = _regress_factor_toward_neutral(adj, g)
    return RawSeasonFactors(**kw)


def _round3(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 3)


def _mean_nonnull(xs: list[float | None]) -> float | None:
    vals = [v for v in xs if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _fetch_teams(client: Any) -> dict[int, str]:
    names: dict[int, str] = {}
    offset = 0
    while True:
        try:
            resp = (
                client.table("teams")
                .select("id,name")
                .order("id")
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(f"calc_park_factors: teams page at {offset} failed: {exc}", flush=True)
            break
        rows = resp.data or []
        for r in rows:
            tid = _safe_int(r.get("id"))
            if tid is not None and r.get("name"):
                names[tid] = str(r["name"])
        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return names


def _fetch_game_logs(client: Any) -> int:
    """Page through game_logs; return row count processed."""

    global _AGG
    _AGG = {}
    total = 0
    offset = 0
    cols = (
        "game_date,home_team_id,away_team_id,home_score,away_score,status,"
        "home_hr,away_hr,home_hits,away_hits,home_singles,away_singles,"
        "home_doubles,away_doubles,home_triples,away_triples,home_bb,away_bb,"
        "home_so,away_so"
    )
    while True:
        try:
            resp = (
                client.table("game_logs")
                .select(cols)
                .in_("status", list(ALLOWED_STATUS))
                .order("game_pk")
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_park_factors: game_logs page at offset {offset} failed: {exc}",
                flush=True,
            )
            break
        rows = resp.data or []
        if not rows:
            break
        for row in rows:
            home_id = _safe_int(row.get("home_team_id"))
            away_id = _safe_int(row.get("away_team_id"))
            season = _season_year(row.get("game_date"))
            if home_id is None or away_id is None or season is None:
                continue
            _ingest_game(home_id, away_id, season, row)
        total += len(rows)
        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return total


def _build_raw_map() -> dict[tuple[int, int], RawSeasonFactors]:
    rates_map: dict[tuple[int, int], SeasonRates] = {}
    for key, a in _AGG.items():
        rates_map[key] = _agg_to_season_rates(a)
    league_avgs = _league_rate_averages_by_season(rates_map)
    out: dict[tuple[int, int], RawSeasonFactors] = {}
    for key, sr in rates_map.items():
        season = key[1]
        out[key] = _season_rates_to_raw_factors(sr, league_avgs[season])
    return out


def _seasons_used_for_runs(
    team_id: int,
    season: int,
    raw: dict[tuple[int, int], RawSeasonFactors],
) -> int:
    """How many prior seasons in the lookback window have a non-null runs_factor."""

    n = 0
    for delta in range(_LOOKBACK):
        y = season - delta
        r = raw.get((team_id, y))
        if r is not None and r.runs_factor is not None:
            n += 1
    return n


def _avg_factor(
    team_id: int,
    season: int,
    raw: dict[tuple[int, int], RawSeasonFactors],
    attr: str,
) -> float | None:
    vals: list[float | None] = []
    for delta in range(_LOOKBACK):
        y = season - delta
        r = raw.get((team_id, y))
        if r is None:
            continue
        vals.append(getattr(r, attr))
    return _mean_nonnull(vals)


def _rows_for_upsert(
    raw: dict[tuple[int, int], RawSeasonFactors],
    team_names: dict[int, str],
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for (team_id, season), r_s in sorted(raw.items()):
        base = raw[(team_id, season)]
        su = _seasons_used_for_runs(team_id, season, raw)
        row: dict[str, Any] = {
            "team_id": team_id,
            "team": team_names.get(team_id),
            "season": season,
            "runs_factor": _round3(_avg_factor(team_id, season, raw, "runs_factor")),
            "hr_factor": _round3(_avg_factor(team_id, season, raw, "hr_factor")),
            "hits_factor": _round3(_avg_factor(team_id, season, raw, "hits_factor")),
            "singles_factor": _round3(
                _avg_factor(team_id, season, raw, "singles_factor")
            ),
            "doubles_factor": _round3(
                _avg_factor(team_id, season, raw, "doubles_factor")
            ),
            "triples_factor": _round3(
                _avg_factor(team_id, season, raw, "triples_factor")
            ),
            "bb_factor": _round3(_avg_factor(team_id, season, raw, "bb_factor")),
            "so_factor": _round3(_avg_factor(team_id, season, raw, "so_factor")),
            "home_games": base.home_games,
            "away_games": base.away_games,
            "home_rs": base.home_rs,
            "home_ra": base.home_ra,
            "away_rs": base.away_rs,
            "away_ra": base.away_ra,
            "seasons_used": su,
            "updated_at": now,
        }
        rows.append(row)
    return rows


def _upsert_park_factors(rows: list[dict[str, Any]], client: Any) -> tuple[int, int]:
    ok = 0
    failed = 0
    for i in range(0, len(rows), _BATCH_UPSERT):
        batch = rows[i : i + _BATCH_UPSERT]
        batch_no = i // _BATCH_UPSERT + 1
        try:
            client.table("park_factors").upsert(
                batch,
                on_conflict="team_id,season",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"calc_park_factors: upsert batch {batch_no} failed: {exc}", flush=True)
            failed += len(batch)
    return ok, failed


def main() -> None:
    print("calc_park_factors: fetching teams…", flush=True)
    client = get_client()
    team_names = _fetch_teams(client)
    print(f"calc_park_factors: loaded {len(team_names)} team name(s)", flush=True)

    print("calc_park_factors: scanning game_logs…", flush=True)
    n_games = _fetch_game_logs(client)
    print(f"calc_park_factors: processed {n_games} game row(s)", flush=True)

    raw = _build_raw_map()
    print(f"calc_park_factors: built {len(raw)} raw team-season bucket(s)", flush=True)

    upsert_rows = _rows_for_upsert(raw, team_names)
    ok, fail = _upsert_park_factors(upsert_rows, client)

    print(
        f"calc_park_factors: done — upsert accepted {ok} row(s), "
        f"{fail} row(s) in failed batches (target {len(raw)} team-season rows).",
        flush=True,
    )
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
