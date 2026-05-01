"""
Build season-level MLB league batting/pitching / Statcast rate stats for constants.

Core rule: **sum counting stats first**, then derive rates from those totals (never
average player-level rates for league lines).

Primary source: ``player_batting_seasons``, ``player_pitching_seasons``,
``statcast_batting``, and league pitch velo/spin from the
``statcast_pitch_season_averages`` view (aggregated from ``statcast_pitches``).

Fallback when a season has no warehouse rows: paginate the MLB Stats API
(``playerPool=all``) and sum player splits locally.
"""

from __future__ import annotations

import json
import math
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

import config  # noqa: F401
from db import get_client

START_SEASON = 1990
END_SEASON = 2026
SEASON_DELAY_SEC = 1.0
REQUEST_TIMEOUT = 10
STATCAST_MIN_SEASON = 2015

USER_AGENT = "WARroom-pipeline/1.0"

STATS_BASE = "https://statsapi.mlb.com/api/v1/stats"

_JSON_PATH = Path(__file__).resolve().parent / "league_averages.json"

_BY_SEASON: dict[int, dict[str, Any]] | None = None

STATCAST_DEFAULTS: dict[str, Any] = {
    "lgAvgEV": None,
    "lgBarrelRate": None,
    "lgHardHitRate": None,
    "lgAvgSprintSpeed": None,
    "lgAvgxwOBA": None,
    "lgAvgVelo": None,
    "lgAvgSpinRate": None,
}

# Placeholder until real park indices are wired (CSV / table keyed by franchise + year).
NEUTRAL_PARK_FACTOR = 1.0


def get_park_factor(team_id: int, season: int) -> float:
    """
    Return run environment multiplier for ``team_id`` in ``season`` (1.0 = neutral).

    To plug in real factors later: load a table such as ``park_factors(team_id,
    season, hr_factor, so_factor, ...)`` (FanGraphs, Clay Davenport, or a custom
    blend), convert to ``PF`` vs league (often /100), and interpolate seasons /
    franchise moves. For now every park returns ``NEUTRAL_PARK_FACTOR``.
    """
    _ = (team_id, season)
    return float(NEUTRAL_PARK_FACTOR)


def get_woba_weights(season: int) -> dict[str, float]:
    """Static wOBA linear weights by MLB era (approximate league-wide values)."""
    y = int(season)
    if y < 2002:
        w = (0.70, 0.73, 0.89, 1.27, 1.61, 2.03)
    elif y <= 2005:
        w = (0.70, 0.73, 0.89, 1.27, 1.61, 2.03)
    elif y <= 2010:
        w = (0.70, 0.73, 0.89, 1.26, 1.60, 2.02)
    elif y <= 2015:
        w = (0.69, 0.72, 0.88, 1.25, 1.59, 2.01)
    elif y <= 2020:
        w = (0.69, 0.72, 0.88, 1.24, 1.58, 2.00)
    else:
        w = (0.69, 0.72, 0.88, 1.25, 1.59, 2.01)
    return {
        "uBB": w[0],
        "HBP": w[1],
        "single": w[2],
        "double": w[3],
        "triple": w[4],
        "HR": w[5],
    }


def _hit_url(season: int, limit: int, offset: int) -> str:
    return (
        f"{STATS_BASE}?stats=season&group=hitting&season={season}"
        f"&sportId=1&gameType=R&playerPool=all&limit={limit}&offset={offset}"
    )


def _pitch_url(season: int, limit: int, offset: int) -> str:
    return (
        f"{STATS_BASE}?stats=season&group=pitching&season={season}"
        f"&sportId=1&gameType=R&playerPool=all&limit={limit}&offset={offset}"
    )


def _safe_int(v: Any) -> int:
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def ip_to_outs(value: Any) -> int:
    """Convert baseball IP (e.g. 54.1) to outs; MLB text / DB numeric safe."""
    if value is None:
        return 0
    s = str(value).strip()
    if not s:
        return 0
    if "." not in s:
        return _safe_int(float(s)) * 3
    whole_s, frac_s = s.split(".", 1)
    frac_digit = frac_s[0] if frac_s else "0"
    w = _safe_int(whole_s) if whole_s else 0
    t = _safe_int(frac_digit) if frac_digit in "0123456789" else 0
    if t not in (0, 1, 2):
        t = 0
    return w * 3 + t


def outs_to_ip(outs: int) -> float:
    return outs / 3.0 if outs else 0.0


def _empty_batting_counts() -> dict[str, int]:
    return {
        "pa": 0,
        "ab": 0,
        "h": 0,
        "doubles": 0,
        "triples": 0,
        "hr": 0,
        "bb": 0,
        "so": 0,
        "r": 0,
        "hbp": 0,
        "sf": 0,
    }


def _empty_pitching_counts() -> dict[str, int | float]:
    return {"outs": 0, "ip": 0.0, "er": 0, "hr": 0, "bb": 0, "so": 0, "h": 0}


def _fetch_mlb_hitting_totals(season: int) -> dict[str, int]:
    limit = 500
    offset = 0
    totals = _empty_batting_counts()
    total_splits = None
    headers = {"User-Agent": USER_AGENT}

    while True:
        try:
            r = requests.get(
                _hit_url(season, limit, offset),
                timeout=REQUEST_TIMEOUT,
                headers=headers,
            )
            r.raise_for_status()
            payload = r.json()
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            warnings.warn(
                f"MLB hitting stats failed season={season}: {exc!s}", stacklevel=2
            )
            print(f"[warn] MLB hitting season={season}: {exc}", flush=True)
            return _empty_batting_counts()

        stats_list = payload.get("stats") or []
        if not stats_list:
            break
        block = stats_list[0]
        if total_splits is None:
            total_splits = _safe_int(block.get("totalSplits"))

        for sp in block.get("splits") or []:
            st = sp.get("stat") or {}
            totals["ab"] += _safe_int(st.get("atBats"))
            totals["h"] += _safe_int(st.get("hits"))
            totals["doubles"] += _safe_int(st.get("doubles"))
            totals["triples"] += _safe_int(st.get("triples"))
            totals["hr"] += _safe_int(st.get("homeRuns"))
            totals["bb"] += _safe_int(st.get("baseOnBalls"))
            totals["so"] += _safe_int(st.get("strikeOuts"))
            totals["hbp"] += _safe_int(st.get("hitByPitch"))
            totals["sf"] += _safe_int(st.get("sacFlies"))
            totals["pa"] += _safe_int(st.get("plateAppearances"))
            totals["r"] += _safe_int(st.get("runs"))

        n = len(block.get("splits") or [])
        offset += n
        if n < limit:
            break
        if total_splits is not None and offset >= total_splits:
            break

    return totals


def _fetch_mlb_pitching_totals(season: int) -> dict[str, int | float]:
    limit = 500
    offset = 0
    outs = 0
    er = 0
    hr = 0
    bb = 0
    so = 0
    h = 0
    total_splits = None
    headers = {"User-Agent": USER_AGENT}

    while True:
        try:
            r = requests.get(
                _pitch_url(season, limit, offset),
                timeout=REQUEST_TIMEOUT,
                headers=headers,
            )
            r.raise_for_status()
            payload = r.json()
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            warnings.warn(
                f"MLB pitching stats failed season={season}: {exc!s}", stacklevel=2
            )
            print(f"[warn] MLB pitching season={season}: {exc}", flush=True)
            return dict(_empty_pitching_counts())

        stats_list = payload.get("stats") or []
        if not stats_list:
            break
        block = stats_list[0]
        if total_splits is None:
            total_splits = _safe_int(block.get("totalSplits"))

        for sp in block.get("splits") or []:
            st = sp.get("stat") or {}
            outs += ip_to_outs(st.get("inningsPitched"))
            er += _safe_int(st.get("earnedRuns"))
            hr += _safe_int(st.get("homeRuns"))
            bb += _safe_int(st.get("baseOnBalls"))
            so += _safe_int(st.get("strikeOuts"))
            h += _safe_int(st.get("hits"))

        n = len(block.get("splits") or [])
        offset += n
        if n < limit:
            break
        if total_splits is not None and offset >= total_splits:
            break

    ip = outs_to_ip(outs)
    return {"outs": outs, "ip": ip, "er": er, "hr": hr, "bb": bb, "so": so, "h": h}


def _batting_derived(
    c: dict[str, int], season: int, *, obp_method: str
) -> dict[str, Any]:
    lg_pa = int(c["pa"])
    lg_ab = int(c["ab"])
    lg_h = int(c["h"])
    lg_bb = int(c["bb"])
    lg_so = int(c["so"])
    lg_hr = int(c["hr"])
    lg_2b = int(c["doubles"])
    lg_3b = int(c["triples"])
    lg_r = int(c["r"])
    lg_hbp = int(c.get("hbp", 0))
    lg_sf = int(c.get("sf", 0))

    lg_1b = lg_h - lg_2b - lg_3b - lg_hr
    if lg_1b < 0:
        print(
            f"[warn] season {season}: lg1B negative after sums ({lg_1b}); clamping to 0",
            flush=True,
        )
        lg_1b = 0

    lg_tb = lg_1b + (lg_2b * 2) + (lg_3b * 3) + (lg_hr * 4)

    lg_avg = (lg_h / lg_ab) if lg_ab else None
    lg_slg = (lg_tb / lg_ab) if lg_ab else None
    den_obp = lg_ab + lg_bb + lg_hbp + lg_sf
    lg_obp = (
        ((lg_h + lg_bb + lg_hbp) / den_obp) if den_obp else None
    )

    den_babip = lg_ab - lg_so - lg_hr + lg_sf
    lg_babip = ((lg_h - lg_hr) / den_babip) if den_babip > 0 else None

    lg_bb_pct = (lg_bb / lg_pa) if lg_pa else None
    lg_k_pct = (lg_so / lg_pa) if lg_pa else None
    lg_iso = (lg_slg - lg_avg) if (lg_slg is not None and lg_avg is not None) else None

    w = get_woba_weights(season)
    if lg_pa:
        # Note: using total BB as uBB proxy since IBB is not stored in
        # player_batting_seasons. This slightly overstates wOBA for seasons
        # with many intentional walks. Impact is minimal at league level
        # (~0.001 wOBA points).
        woba_num = (
            w["uBB"] * lg_bb
            + w["HBP"] * lg_hbp
            + w["single"] * lg_1b
            + w["double"] * lg_2b
            + w["triple"] * lg_3b
            + w["HR"] * lg_hr
        )
        lgwoba = woba_num / lg_pa
    else:
        lgwoba = None

    out: dict[str, Any] = {
        "lgPA": lg_pa,
        "lgAB": lg_ab,
        "lgH": lg_h,
        "lgBB": lg_bb,
        "lgSO": lg_so,
        "lgHR": lg_hr,
        "lg2B": lg_2b,
        "lg3B": lg_3b,
        "lgR": lg_r,
        "lgHBP": lg_hbp,
        "lgSF": lg_sf,
        "lg1B": lg_1b,
        "lgTB": lg_tb,
        "lgAVG": lg_avg,
        "lgOBP": lg_obp,
        "lgSLG": lg_slg,
        "lgBABIP": lg_babip,
        "lgBB_pct": lg_bb_pct,
        "lgK_pct": lg_k_pct,
        "lgISO": lg_iso,
        "lgwOBA": lgwoba,
        "lgOBP_method": obp_method,
    }
    return out


def _pitching_derived(p: dict[str, int | float]) -> dict[str, Any]:
    lg_ip = float(p["ip"])
    lg_er = int(p["er"])
    lg_hr = int(p["hr"])
    lg_bb = int(p["bb"])
    lg_so = int(p["so"])
    lg_h = int(p["h"])

    lg_era = (9.0 * lg_er / lg_ip) if lg_ip > 0 else None
    lg_whip = ((lg_h + lg_bb) / lg_ip) if lg_ip > 0 else None
    lg_k9 = ((lg_so * 9.0) / lg_ip) if lg_ip > 0 else None
    lg_bb9 = ((lg_bb * 9.0) / lg_ip) if lg_ip > 0 else None
    lg_hr9 = ((lg_hr * 9.0) / lg_ip) if lg_ip > 0 else None
    if lg_ip > 0 and lg_era is not None:
        fip_term = (13 * lg_hr + 3 * lg_bb - 2 * lg_so) / lg_ip
        fip_c = lg_era - fip_term
    else:
        fip_c = None

    return {
        "lgIP": lg_ip,
        "lgER": lg_er,
        "lgHR_pitch": lg_hr,
        "lgBB_pitch": lg_bb,
        "lgSO_pitch": lg_so,
        "lgH_pitch": lg_h,
        "lgERA": lg_era,
        "lgWHIP": lg_whip,
        "lgK_per_9": lg_k9,
        "lgBB_per_9": lg_bb9,
        "lgHR_per_9": lg_hr9,
        "FIP_constant": fip_c,
    }


def _paginate_supabase_table(
    client: Any,
    table: str,
    columns: str,
    season_lo: int,
    season_hi: int,
    season_column: str = "season",
) -> list[dict[str, Any]]:
    page_size = 1000
    start = 0
    rows: list[dict[str, Any]] = []
    while True:
        end = start + page_size - 1
        try:
            resp = (
                client.table(table)
                .select(columns)
                .gte(season_column, season_lo)
                .lte(season_column, season_hi)
                .range(start, end)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Supabase query failed ({table}): {exc}", flush=True)
            return []

        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def _aggregate_batting_from_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    t = _empty_batting_counts()
    for r in rows:
        if int(r.get("season") or 0) == 0:
            continue
        t["ab"] += _safe_int(r.get("ab"))
        t["h"] += _safe_int(r.get("h"))
        t["doubles"] += _safe_int(r.get("doubles"))
        t["triples"] += _safe_int(r.get("triples"))
        t["hr"] += _safe_int(r.get("hr"))
        t["bb"] += _safe_int(r.get("bb"))
        t["so"] += _safe_int(r.get("so"))
        t["pa"] += _safe_int(r.get("pa"))
        t["r"] += _safe_int(r.get("r"))
    return t


def _aggregate_pitching_from_rows(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    outs = 0
    er = 0
    hr = 0
    bb = 0
    so = 0
    h = 0
    for r in rows:
        if int(r.get("season") or 0) == 0:
            continue
        outs += ip_to_outs(r.get("ip"))
        er += _safe_int(r.get("er"))
        hr += _safe_int(r.get("hr"))
        bb += _safe_int(r.get("bb"))
        so += _safe_int(r.get("so"))
        h += _safe_int(r.get("h"))
    ip = outs_to_ip(outs)
    return {"outs": outs, "ip": ip, "er": er, "hr": hr, "bb": bb, "so": so, "h": h}


def _group_int_key_rows(
    rows: list[dict[str, Any]], key: str = "season"
) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        sk = r.get(key)
        if sk is None:
            continue
        s = int(sk)
        out.setdefault(s, []).append(r)
    return out


def _statcast_batting_league(client: Any | None, season_lo: int, season_hi: int) -> dict[int, dict[str, Any]]:
    """PA-weighted league Statcast batting lines per season (2015+ typical)."""
    out: dict[int, dict[str, Any]] = {}
    if client is None:
        return out
    cols = (
        "season, pa, avg_exit_velocity, barrel_rate, hard_hit_rate, "
        "xwoba, sprint_speed"
    )
    rows = _paginate_supabase_table(client, "statcast_batting", cols, season_lo, season_hi)
    by_s = _group_int_key_rows(rows)
    for s, rs in by_s.items():
        if s < STATCAST_MIN_SEASON:
            continue
        w_ev = w_br = w_hh = w_ss = w_xw = 0.0
        pa_ev = pa_br = pa_hh = pa_ss = pa_xw = 0
        for r in rs:
            pa = _safe_int(r.get("pa"))
            if pa <= 0:
                continue
            ev = _safe_float(r.get("avg_exit_velocity"))
            if ev is not None:
                w_ev += ev * pa
                pa_ev += pa
            br = _safe_float(r.get("barrel_rate"))
            if br is not None:
                w_br += br * pa
                pa_br += pa
            hh = _safe_float(r.get("hard_hit_rate"))
            if hh is not None:
                w_hh += hh * pa
                pa_hh += pa
            ss = _safe_float(r.get("sprint_speed"))
            if ss is not None:
                w_ss += ss * pa
                pa_ss += pa
            xw = _safe_float(r.get("xwoba"))
            if xw is not None:
                w_xw += xw * pa
                pa_xw += pa
        out[s] = {
            "lgAvgEV": (w_ev / pa_ev) if pa_ev else None,
            "lgBarrelRate": (w_br / pa_br) if pa_br else None,
            "lgHardHitRate": (w_hh / pa_hh) if pa_hh else None,
            "lgAvgSprintSpeed": (w_ss / pa_ss) if pa_ss else None,
            "lgAvgxwOBA": (w_xw / pa_xw) if pa_xw else None,
        }
    return out


def _statcast_pitch_league_avgs(
    client: Any | None,
    season: int,
) -> dict[str, Any]:
    """
    League mean pitch velo / spin from the ``statcast_pitch_season_averages`` view
    (see SCHEMA.md). One row per calendar ``season``; fast vs paginating ``statcast_pitches``.
    """
    if season < STATCAST_MIN_SEASON or client is None:
        return {"lgAvgVelo": None, "lgAvgSpinRate": None}

    try:
        resp = (
            client.table("statcast_pitch_season_averages")
            .select("lg_avg_velo, lg_avg_spin_rate")
            .eq("season", season)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"[warn] statcast_pitch_season_averages query failed "
            f"(season={season}): {exc}",
            flush=True,
        )
        return {"lgAvgVelo": None, "lgAvgSpinRate": None}

    rows = resp.data or []
    if not rows:
        return {"lgAvgVelo": None, "lgAvgSpinRate": None}

    row = rows[0]
    return {
        "lgAvgVelo": _safe_float(row.get("lg_avg_velo")),
        "lgAvgSpinRate": _safe_float(row.get("lg_avg_spin_rate")),
    }


def build_league_table(
    client: Any | None = None,
    *,
    start: int | None = None,
    end: int | None = None,
) -> dict[int, dict[str, Any]]:
    season_lo = int(start) if start is not None else START_SEASON
    season_hi = int(end) if end is not None else END_SEASON
    if season_lo > season_hi:
        raise ValueError(f"start ({season_lo}) must be <= end ({season_hi})")

    if client is None:
        try:
            client = get_client()
        except RuntimeError:
            client = None

    batting_by_season: dict[int, dict[str, int]] = {}
    pitching_by_season: dict[int, dict[str, int | float]] = {}

    if client is not None:
        b_rows = _paginate_supabase_table(
            client,
            "player_batting_seasons",
            (
                "season, pa, ab, h, doubles, triples, hr, bb, so, r"
            ),
            season_lo,
            season_hi,
        )
        p_rows = _paginate_supabase_table(
            client,
            "player_pitching_seasons",
            "season, ip, er, hr, bb, so, h",
            season_lo,
            season_hi,
        )
        bg = _group_int_key_rows(b_rows)
        pg = _group_int_key_rows(p_rows)
        for s, rs in bg.items():
            if season_lo <= s <= season_hi:
                batting_by_season[s] = _aggregate_batting_from_rows(rs)
        for s, rs in pg.items():
            if season_lo <= s <= season_hi:
                pitching_by_season[s] = _aggregate_pitching_from_rows(rs)

    statcast_bat = _statcast_batting_league(client, season_lo, season_hi)

    results: dict[int, dict[str, Any]] = {}

    for season in range(season_lo, season_hi + 1):
        bat_src = "supabase"
        pit_src = "supabase"

        if season not in batting_by_season or batting_by_season[season]["ab"] == 0:
            batting_by_season[season] = _fetch_mlb_hitting_totals(season)
            bat_src = (
                "mlb_api"
                if batting_by_season[season]["ab"] > 0
                else "failed"
            )

        if season not in pitching_by_season or pitching_by_season[season]["ip"] == 0:
            pitching_by_season[season] = _fetch_mlb_pitching_totals(season)
            pit_src = (
                "mlb_api"
                if pitching_by_season[season]["ip"] > 0
                else "failed"
            )

        obp_method = "mlb_full" if bat_src == "mlb_api" else "warehouse_hbp_sf_zeros"

        bd = _batting_derived(
            batting_by_season[season], season, obp_method=obp_method
        )
        pd = _pitching_derived(pitching_by_season[season])

        scb = statcast_bat.get(season, {})
        scp = _statcast_pitch_league_avgs(client, season)
        statcast_row = {**STATCAST_DEFAULTS, **scb, **scp}

        row: dict[str, Any] = {
            "season": season,
            **bd,
            **pd,
            **statcast_row,
            "batting_source": bat_src,
            "pitching_source": pit_src,
        }
        results[season] = row
        time.sleep(SEASON_DELAY_SEC)

    return results


def _fmt(x: float | None, width: int, prec: int) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return f"{'n/a':>{width}}"
    return f"{x:>{width}.{prec}f}"


def _fmt_pct(x: float | None, width: int) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return f"{'n/a':>{width}}"
    return f"{x * 100.0:>{width}.1f}%"


def _print_table(rows: dict[int, dict[str, Any]]) -> None:
    hdr = (
        f"{'season':>6} {'lgAVG':>7} {'lgOBP':>7} {'lgSLG':>7} {'lgERA':>6} "
        f"{'FIP_c':>6} {'BB%':>6} {'K%':>6} {'wOBA':>6} {'AvgEV':>7}"
    )
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)
    for season in sorted(rows):
        r = rows[season]
        print(
            f"{season:>6} "
            f"{_fmt(r.get('lgAVG'), 7, 3)} "
            f"{_fmt(r.get('lgOBP'), 7, 3)} "
            f"{_fmt(r.get('lgSLG'), 7, 3)} "
            f"{_fmt(r.get('lgERA'), 6, 2)} "
            f"{_fmt(r.get('FIP_constant'), 6, 2)} "
            f"{_fmt_pct(r.get('lgBB_pct'), 6)} "
            f"{_fmt_pct(r.get('lgK_pct'), 6)} "
            f"{_fmt(r.get('lgwOBA'), 6, 3)} "
            f"{_fmt(r.get('lgAvgEV'), 7, 1)}",
            flush=True,
        )


def _save_json(rows: dict[int, dict[str, Any]], path: Path) -> None:
    def _json_default(o: Any) -> Any:
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    if rows:
        season_lo = min(rows)
        season_hi = max(rows)
    else:
        season_lo = START_SEASON
        season_hi = END_SEASON

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season_start": season_lo,
        "season_end": season_hi,
        "seasons": {str(k): v for k, v in sorted(rows.items())},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default)


def _load_json(path: Path) -> dict[int, dict[str, Any]]:
    """Normalize wrapped or flat ``league_averages.json`` to ``season -> row``."""
    with path.open(encoding="utf-8") as f:
        raw: Any = json.load(f)
    if not isinstance(raw, dict):
        return {}

    if isinstance(raw.get("seasons"), dict):
        seasons_src: dict[str, Any] = raw["seasons"]
    else:
        meta_keys = frozenset(
            {
                "generated_at",
                "season_start",
                "season_end",
                "neutral_park_factor",
            }
        )
        seasons_src = {
            k: v
            for k, v in raw.items()
            if k not in meta_keys and isinstance(v, dict)
        }

    out: dict[int, dict[str, Any]] = {}
    for k, v in seasons_src.items():
        try:
            sk = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict):
            out[sk] = v
    return out


def get_league_averages(season: int) -> dict[str, Any] | None:
    """
    Return league-average bundle for ``season`` from cache or ``league_averages.json``.

    Supports JSON either **wrapped**
    ``{ "generated_at", "season_start", "season_end", "seasons": { "1990": ... } }``
    or **flat** ``{ "1990": ... }`` (legacy). The file is read on first use. If the
    file was missing on first load, the in-memory cache starts empty; if the JSON
    appears later on disk, the next call reloads it. ``refresh_league_averages_cache``
    can also populate the cache without reading the file.

    Returns ``None`` if the file is missing (after warning on first miss), if
    ``season`` is absent, or if the JSON could not be parsed into season rows.
    """
    global _BY_SEASON
    if _BY_SEASON is None:
        if not _JSON_PATH.exists():
            print(
                f"[warn] league averages JSON not found at {_JSON_PATH}; "
                "run ``python -m calculations.fetch_league_averages`` or build via "
                "``build_league_table`` and ``_save_json``.",
                flush=True,
            )
            _BY_SEASON = {}
        else:
            _BY_SEASON = _load_json(_JSON_PATH)
    elif len(_BY_SEASON) == 0 and _JSON_PATH.exists():
        _BY_SEASON = _load_json(_JSON_PATH)

    row = _BY_SEASON.get(season)
    if row is None:
        return None
    return dict(row)


def refresh_league_averages_cache(rows: dict[int, dict[str, Any]]) -> None:
    global _BY_SEASON
    _BY_SEASON = dict(rows)


def main() -> None:
    try:
        sb = get_client()
    except RuntimeError as e:
        print(f"{e}; continuing with MLB API only.", flush=True)
        sb = None

    rows = build_league_table(sb)
    refresh_league_averages_cache(rows)
    _save_json(rows, _JSON_PATH)
    _print_table(rows)
    print(f"\nWrote {_JSON_PATH}", flush=True)


if __name__ == "__main__":
    main()
