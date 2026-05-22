"""
Derive batting rate stats and contextual metrics from ``player_batting_seasons`` counting
columns (no MLB API). Writes patches via ``upsert_player_batting_seasons`` so existing
counts stay intact (partial upsert semantics).

Counts read per row include MLB-style lines plus ``g`` (games) for the positional term in
batting-only WPR (``bwpr``, from ``calc_batting_war``). League batting totals plus league
``lg_pa``/``lg_r`` for that computation come from Supabase ``league_batting_averages``;
league ``lg_ip`` for RPW from ``league_pitching_averages`` (warehouse totals via
``calc_league_averages``); park multipliers from ``park_factors.runs_factor`` keyed by
``(team_id, season)``.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime
from typing import Any

import config  # noqa: F401 — loads pipeline/.env before db access

from calculations.batting_calcs import (
    calc_babip,
    calc_batting_war,
    calc_bb_pct,
    calc_iso,
    calc_k_pct,
    calc_singles,
    calc_tb,
    calc_woba,
    calc_wrc_plus,
)
from db import get_client

_START_DEFAULT = 1990
_PAGE_SIZE = 1000
_RPC_BATCH = 500

_SELECT = (
    "player_id,season,team_id,team,ab,pa,h,doubles,triples,hr,rbi,"
    "bb,so,hbp,r,sb,g"
)

_METRIC_KEYS = (
    "avg",
    "obp",
    "slg",
    "ops",
    "iso",
    "babip",
    "bb_pct",
    "k_pct",
    "woba",
    "ops_plus",
    "wrc_plus",
    "bwpr",
)


def get_mlb_games_played(client: Any, season: int) -> float:
    """League-wide game tally for batting replacement scaling in ``calc_batting_war``."""
    if season == 2020:
        return 900.0
    if season < 2022:
        return 2430.0
    date_start = f"{season}-01-01"
    date_end = f"{season}-12-31"
    resp = (
        client.table("game_logs")
        .select("game_pk", count="exact", head=True)
        .eq("status", "Final")
        .gte("game_date", date_start)
        .lte("game_date", date_end)
        .execute()
    )
    n = resp.count
    if n is None:
        raise RuntimeError(
            f"calc_batting_season_metrics: game_logs count unavailable for season={season}"
        )
    return float(n)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Compute derived metrics for player_batting_seasons from counts; "
            "upsert patches via RPC upsert_player_batting_seasons."
        ),
    )
    p.add_argument(
        "--start-season",
        type=int,
        default=_START_DEFAULT,
        help=f"First season (default {_START_DEFAULT}).",
    )
    p.add_argument(
        "--end-season",
        type=int,
        default=datetime.now().year,
        help="Last season (default: current calendar year).",
    )
    return p.parse_args()


def _to_float(val: Any) -> float | None:
    """NaN-safe float for DB / JSON primitives."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        x = float(str(val).strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _calc_ops_plus_extrinsic(
    obp: float | None,
    slg_val: float | None,
    lg_obp_ln: float | None,
    lg_slg_ln: float | None,
    park_factor: float,
) -> float | None:
    """OPS+ (BR-style) using league slash lines supplied by caller (cf. ``calc_ops_plus``)."""
    if obp is None or slg_val is None:
        return None
    if lg_obp_ln is None or lg_slg_ln is None:
        return None
    lo = float(lg_obp_ln)
    ls = float(lg_slg_ln)
    if lo == 0 or ls == 0 or park_factor == 0:
        return None
    pf = float(park_factor)
    return float(100.0 * (float(obp) / lo + float(slg_val) / ls - 1.0) / pf)


def _calc_avg(h: float | None, ab: float | None) -> float | None:
    if h is None or ab is None or ab == 0:
        return None
    return round(float(h) / float(ab), 3)


def _calc_obp(
    h: float | None,
    bb: float | None,
    hbp: float | None,
    ab: float | None,
    *,
    sf: float = 0.0,
) -> float | None:
    """OBP numerator ``H + BB + HBP``; denominator ``AB + BB + HBP + SF`` (SF default 0)."""
    if h is None or bb is None or ab is None:
        return None
    hb = 0.0 if hbp is None else float(hbp)
    num = float(h) + float(bb) + hb
    den = float(ab) + float(bb) + hb + float(sf)
    if den == 0:
        return None
    return round(num / den, 3)


def _calc_slg_from_counts(
    h: float | None,
    doubles: float | None,
    triples: float | None,
    hr: float | None,
    ab: float | None,
) -> float | None:
    singles = calc_singles(h, doubles, triples, hr)
    tb = calc_tb(singles, doubles, triples, hr)
    if tb is None or ab is None or ab == 0:
        return None
    return round(float(tb) / float(ab), 3)


def load_league_batting_averages_row(client: Any, season: int) -> dict[str, Any] | None:
    """One row from ``league_batting_averages`` for ``season`` (or ``None`` if missing)."""

    try:
        resp = (
            client.table("league_batting_averages")
            .select(
                "lg_avg,lg_obp,lg_slg,lg_woba,lg_runs_per_pa,lg_wrc_per_pa,lg_pa,lg_r"
            )
            .eq("season", season)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"calc_batting_season_metrics: league_batting_averages read failed "
            f"season={season}: {exc}",
            flush=True,
        )
        return None
    rows = resp.data or []
    if not rows:
        return None
    return rows[0]


def load_league_pitching_ip(client: Any, season: int) -> float | None:
    """League pitching IP (``lgIP``) for RPW inside ``calc_batting_war`` → stored ``bwpr``."""

    try:
        resp = (
            client.table("league_pitching_averages")
            .select("lg_ip")
            .eq("season", season)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"calc_batting_season_metrics: league_pitching_averages read failed "
            f"season={season}: {exc}",
            flush=True,
        )
        return None
    rows = resp.data or []
    if not rows:
        return None
    return _to_float(rows[0].get("lg_ip"))


def load_park_map_for_season(client: Any, season: int) -> dict[int, float]:
    """``team_id`` -> ``runs_factor`` for one season (neutral absent keys -> 1.0 at lookup)."""

    out: dict[int, float] = {}
    offset = 0
    while True:
        try:
            resp = (
                client.table("park_factors")
                .select("team_id,runs_factor")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_batting_season_metrics: park_factors season={season} "
                f"offset={offset} failed: {exc}",
                flush=True,
            )
            break
        rows = resp.data or []
        for row in rows:
            tid = row.get("team_id")
            rf = row.get("runs_factor")
            if tid is None or rf is None:
                continue
            try:
                out[int(tid)] = float(rf)
            except (TypeError, ValueError):
                continue
        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return out


def _park_for_row(park_map: dict[int, float], team_id: Any) -> float:
    if team_id is None:
        return 1.0
    try:
        tid = int(team_id)
    except (TypeError, ValueError):
        return 1.0
    v = park_map.get(tid)
    return float(v) if v is not None else 1.0


def ensure_player_positions(client: Any, cache: dict[int, str | None], ids: set[int]) -> None:
    pending = sorted(i for i in ids if i not in cache)
    if not pending:
        return
    for i in range(0, len(pending), _RPC_BATCH):
        chunk = pending[i : i + _RPC_BATCH]
        try:
            resp = (
                client.table("players").select("id,position").in_("id", chunk).execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_batting_season_metrics: players lookup failed: {exc}",
                flush=True,
            )
            for pid in chunk:
                cache[pid] = None
            continue
        row_by_id = {int(r["id"]): r.get("position") for r in (resp.data or []) if r.get("id")}
        for pid in chunk:
            cache[pid] = row_by_id.get(pid)


def derive_row_payload(
    row: dict[str, Any],
    season: int,
    park_map: dict[int, float],
    lg_bat: dict[str, Any],
    lg_ip_league: float | None,
    position_cache: dict[int, str | None],
    mlb_games_played: float,
) -> dict[str, Any] | None:
    pid = row.get("player_id")
    if pid is None:
        return None
    try:
        player_id_int = int(pid)
    except (TypeError, ValueError):
        return None

    team_id = row.get("team_id")
    pf_team = _park_for_row(park_map, team_id)

    ab = _to_float(row.get("ab"))
    pa = _to_float(row.get("pa"))
    h = _to_float(row.get("h"))
    dbl = _to_float(row.get("doubles"))
    tpl = _to_float(row.get("triples"))
    hr = _to_float(row.get("hr"))
    bb = _to_float(row.get("bb"))
    so = _to_float(row.get("so"))
    raw_hbp = row.get("hbp")
    hbp = _to_float(raw_hbp) if raw_hbp is not None else None
    hbp_woba = 0.0 if hbp is None else float(hbp)

    avg = _calc_avg(h, ab)
    obp = _calc_obp(h, bb, hbp, ab)
    slg = _calc_slg_from_counts(h, dbl, tpl, hr, ab)
    ops = round(float(obp) + float(slg), 3) if obp is not None and slg is not None else None
    iso_val = calc_iso(slg, avg)

    babip = calc_babip(h, hr, ab, so, sf=0.0)

    bb_pct_r = calc_bb_pct(bb, pa)
    bb_pct_pct = round(bb_pct_r * 100.0, 1) if bb_pct_r is not None else None
    k_pct_r = calc_k_pct(so, pa)
    k_pct_pct = round(k_pct_r * 100.0, 1) if k_pct_r is not None else None

    singles = calc_singles(h, dbl, tpl, hr)
    woba = (
        calc_woba(
            bb,
            hbp_woba,
            singles,
            dbl,
            tpl,
            hr,
            pa,
            int(season),
        )
        if pa is not None
        else None
    )

    lg_obp_ln = _to_float(lg_bat.get("lg_obp"))
    lg_slg_ln = _to_float(lg_bat.get("lg_slg"))

    raw_ops_plus = _calc_ops_plus_extrinsic(obp, slg, lg_obp_ln, lg_slg_ln, pf_team)
    ops_plus_i = int(round(raw_ops_plus)) if raw_ops_plus is not None else None

    lg_woba_ln = _to_float(lg_bat.get("lg_woba"))
    lg_runs_per_pa_ln = _to_float(lg_bat.get("lg_runs_per_pa"))
    lg_wrc_per_pa_ln = _to_float(lg_bat.get("lg_wrc_per_pa"))
    lg_rperpa = lg_wrc_per_pa_ln if lg_wrc_per_pa_ln is not None else lg_runs_per_pa_ln

    wrc_plus = calc_wrc_plus(
        woba, pa, int(season), lg_woba_ln, lg_rperpa, park_factor=pf_team
    )

    g = _to_float(row.get("g"))
    lg_r_ln = _to_float(lg_bat.get("lg_r"))
    lg_pa_ln = _to_float(lg_bat.get("lg_pa"))
    pos_str = position_cache.get(player_id_int)
    bwpr_val = calc_batting_war(
        woba,
        pa,
        g,
        pos_str,
        int(season),
        lg_woba_ln,
        lg_r_ln,
        lg_pa_ln,
        lg_ip_league,
        park_factor=pf_team,
        mlb_games=mlb_games_played,
    )

    out: dict[str, Any] = {
        "player_id": player_id_int,
        "season": season,
    }
    if team_id is not None:
        try:
            out["team_id"] = int(team_id)
        except (TypeError, ValueError):
            out["team_id"] = None
    else:
        out["team_id"] = None
    if iso_val is not None:
        out["iso"] = round(float(iso_val), 3)
    if avg is not None:
        out["avg"] = avg
    if obp is not None:
        out["obp"] = obp
    if slg is not None:
        out["slg"] = slg
    if ops is not None:
        out["ops"] = ops
    if babip is not None:
        out["babip"] = round(float(babip), 3)
    if bb_pct_pct is not None:
        out["bb_pct"] = bb_pct_pct
    if k_pct_pct is not None:
        out["k_pct"] = k_pct_pct
    if woba is not None:
        out["woba"] = round(float(woba), 3)
    if ops_plus_i is not None:
        out["ops_plus"] = ops_plus_i
    if wrc_plus is not None:
        out["wrc_plus"] = wrc_plus
    if bwpr_val is not None:
        out["bwpr"] = bwpr_val

    wrote_metric = any(k in out for k in _METRIC_KEYS)
    if not wrote_metric:
        return None
    return out


def _flush_rpc_batches(
    client: Any,
    payloads: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Returns ``(rows_committed_ok, rows_in_failed_batches, failed_batch_count)``."""
    ok_rows = 0
    failed_rows = 0
    failed_batches = 0
    n_batches = (len(payloads) + _RPC_BATCH - 1) // _RPC_BATCH if payloads else 0
    batch_idx = 0
    for i in range(0, len(payloads), _RPC_BATCH):
        batch = payloads[i : i + _RPC_BATCH]
        batch_idx += 1
        try:
            client.rpc("upsert_player_batting_seasons", {"rows": batch}).execute()
            ok_rows += len(batch)
        except Exception as exc:  # noqa: BLE001
            failed_rows += len(batch)
            failed_batches += 1
            print(
                f"calc_batting_season_metrics: RPC batch {batch_idx}/{n_batches} "
                f"failed ({len(batch)} rows) — {exc}",
                flush=True,
            )
    return ok_rows, failed_rows, failed_batches


def run_season(client: Any, season: int) -> tuple[int, int, int, int, int, float | None]:
    """
    Returns ``(rows_read, rows_written, rows_skipped, rows_failed_write, failed_batches,
    mlb_games_played_or_none_when_season_skipped)``.
    """

    lg_bat = load_league_batting_averages_row(client, season)
    if lg_bat is None:
        print(
            f"calc_batting_season_metrics: warning: no league_batting_averages row for "
            f"season={season}; skipping entire season.",
            flush=True,
        )
        return (0, 0, 0, 0, 0, None)

    lg_ip_league = load_league_pitching_ip(client, season)

    park_map = load_park_map_for_season(client, season)
    position_cache: dict[int, str | None] = {}
    mlb_games_played = get_mlb_games_played(client, season)

    rows_read = 0
    payloads: list[dict[str, Any]] = []
    rows_skipped = 0

    offset = 0
    while True:
        try:
            resp = (
                client.table("player_batting_seasons")
                .select(_SELECT)
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_batting_season_metrics: read player_batting_seasons "
                f"season={season} offset={offset} failed: {exc}",
                flush=True,
            )
            break
        page = resp.data or []
        if not page:
            break
        rows_read += len(page)

        page_ids = set()
        for row in page:
            pid_raw = row.get("player_id")
            if pid_raw is None:
                continue
            try:
                page_ids.add(int(pid_raw))
            except (TypeError, ValueError):
                continue
        ensure_player_positions(client, position_cache, page_ids)

        for row in page:
            payload = derive_row_payload(
                row,
                season,
                park_map,
                lg_bat,
                lg_ip_league,
                position_cache,
                mlb_games_played,
            )
            if payload is None:
                rows_skipped += 1
            else:
                payloads.append(payload)

        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    rows_written, rows_failed_write, failed_batches_ct = _flush_rpc_batches(client, payloads)
    return (
        rows_read,
        rows_written,
        rows_skipped,
        rows_failed_write,
        failed_batches_ct,
        mlb_games_played,
    )


def main() -> None:
    args = _parse_args()
    start = args.start_season
    end = args.end_season
    if start > end:
        raise SystemExit(
            f"calc_batting_season_metrics: --start-season ({start}) must be "
            f"<= --end-season ({end})."
        )

    client = get_client()
    total_written = 0
    total_failures = 0

    cur = start
    while cur <= end:
        rr, rw, skipped, rf, fb, mlg = run_season(client, cur)
        if mlg is None:
            mlg_s = "n/a"
        elif float(mlg).is_integer():
            mlg_s = str(int(mlg))
        else:
            mlg_s = repr(mlg)
        print(
            f"calc_batting_season_metrics: season {cur} — mlb_games_played={mlg_s}, "
            f"rows_read={rr}, rows_written={rw}, rows_skipped={skipped}, "
            f"failed_batches={fb}.",
            flush=True,
        )
        total_written += rw
        total_failures += rf
        cur += 1

    print(
        f"calc_batting_season_metrics: done — total_rows_written={total_written}, "
        f"total_failures={total_failures}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
