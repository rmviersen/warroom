"""
Compute fielding Wins Above Replacement (**fWPR**) per player batting season.

Uses ``statcast_fielding_oaa.fielding_runs_prevented`` (2016+) when present; otherwise
RF/9 z-scores vs position-season leagues from ``player_fielding_seasons``. Writes
``fwpr`` via ``upsert_player_batting_seasons`` (partial upsert).
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

import config  # noqa: F401 — load pipeline/.env

from calc_batting_season_metrics import (
    get_mlb_games_played,
    load_league_batting_averages_row,
    load_league_pitching_ip,
)
from db import get_client

_PAGE_SIZE = 1000
_RPC_BATCH = 500
_OAA_FIRST_SEASON = 2016


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.strip())
    p.add_argument(
        "--start-season",
        type=int,
        default=datetime.now().year,
        help="First season inclusive (default: current calendar year).",
    )
    p.add_argument(
        "--end-season",
        type=int,
        default=datetime.now().year,
        help="Last season inclusive (default: current calendar year).",
    )
    return p.parse_args()


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def calc_rpw(lg_r: float, lg_ip: float) -> float | None:
    """Runs per win matching ``calc_batting_war`` / ``calc_pitching_war`` RPW."""

    if lg_ip <= 0:
        return None
    rpw = 9.0 * (lg_r / lg_ip) * 1.5 + 3.0
    return rpw if rpw != 0 else None


def _norm_pos(raw: Any) -> str:
    if raw is None:
        return "UNK"
    s = str(raw).strip().upper()
    return s if s else "UNK"


def weighted_mean_and_std(
    values: list[float], weights: list[float]
) -> tuple[float, float]:
    """
    Innings-weighted mean of ``values`` (RF/9) and sqrt of weighted variance.
    Returns ``(mean, std)`` with ``std >= 0``; single-point groups yield std 0.
    """

    sw = math.fsum(weights)
    if sw <= 0 or not values:
        return 0.0, 0.0
    mu = math.fsum(v * w for v, w in zip(values, weights, strict=False)) / sw
    var = math.fsum(w * (v - mu) ** 2 for v, w in zip(values, weights, strict=False)) / sw
    sig = math.sqrt(var) if var > 0 else 0.0
    return float(mu), float(sig)


def load_statcast_oaa_for_season(
    client: Any, season: int
) -> tuple[dict[int, float], set[int], int]:
    """
    Aggregate Statcast defensive runs prevented by ``player_id``.
    Returns ``(frp_sum_by_player, player_ids_with_any_row, db_rows_read)``.
    """

    totals: defaultdict[int, float] = defaultdict(float)
    seen: set[int] = set()
    rows_read = 0

    offset = 0
    while True:
        try:
            resp = (
                client.table("statcast_fielding_oaa")
                .select("player_id,fielding_runs_prevented")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_fielding_season_metrics: statcast_fielding_oaa read "
                f"season={season} offset={offset} failed: {exc}",
                flush=True,
            )
            break

        rows = resp.data or []
        for row in rows:
            rows_read += 1
            pid_raw = row.get("player_id")
            if pid_raw is None:
                continue
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                continue
            seen.add(pid)
            frp = _to_float(row.get("fielding_runs_prevented"))
            if frp is not None:
                totals[pid] += frp

        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    return dict(totals), seen, rows_read


def load_player_fielding_season_rows(
    client: Any, season: int
) -> tuple[list[dict[str, Any]], int]:
    """
    All ``player_fielding_seasons`` rows for ``season``.
    Each dict has ``player_id``, ``position``, ``inn``, ``rf_per_9``.
    """

    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        try:
            resp = (
                client.table("player_fielding_seasons")
                .select("player_id,position,inn,rf_per_9")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_fielding_season_metrics: player_fielding_seasons read "
                f"season={season} offset={offset} failed: {exc}",
                flush=True,
            )
            break

        chunk = resp.data or []
        for row in chunk:
            pid_raw = row.get("player_id")
            if pid_raw is None:
                continue
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                continue
            inn_val = row.get("inn")
            inn_f = _to_float(inn_val) if inn_val is not None else None
            if inn_f is None:
                inn_f = 0.0
            rows.append(
                {
                    "player_id": pid,
                    "position": _norm_pos(row.get("position")),
                    "inn": float(inn_f),
                    "rf_per_9": _to_float(row.get("rf_per_9")),
                }
            )

        if len(chunk) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    return rows, len(rows)


def build_position_rf9_league(rows: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """
    Per normalized position: innings-weighted mean RF/9 and weighted std (for z-scores).
    """

    by_pos: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        inn_f = row["inn"]
        rf_f = row["rf_per_9"]
        if inn_f <= 0 or rf_f is None:
            continue
        by_pos[row["position"]].append((float(rf_f), float(inn_f)))

    out: dict[str, tuple[float, float]] = {}
    for pos, pairs in by_pos.items():
        vals = [p[0] for p in pairs]
        weights = [p[1] for p in pairs]
        mu, sig = weighted_mean_and_std(vals, weights)
        out[pos] = (mu, sig)
    return out


def fielding_runs_via_rf9_fallback(
    player_rows: list[dict[str, Any]],
    pos_league: dict[str, tuple[float, float]],
) -> float:
    """Step 3: sum ``z * (inn/9) * 0.1`` across position appearances."""

    tot = 0.0
    for row in player_rows:
        inn_f = row["inn"]
        rf_f = row["rf_per_9"]
        if inn_f <= 0 or rf_f is None:
            continue
        pos = row["position"]
        mu, sig = pos_league.get(pos, (0.0, 0.0))
        z = (float(rf_f) - mu) / sig if sig >= 1e-9 else 0.0
        tot += z * (float(inn_f) / 9.0) * 0.1
    return float(tot)


def _flush_fwpr_batches(client: Any, payloads: list[dict[str, Any]]) -> tuple[int, int, int]:
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
                f"calc_fielding_season_metrics: RPC batch {batch_idx}/{n_batches} "
                f"failed ({len(batch)} rows) — {exc}",
                flush=True,
            )
    return ok_rows, failed_rows, failed_batches


def run_season(client: Any, season: int) -> tuple[int, int, int, int, int, int, int, int]:
    """
    Returns
    -------
    batting_rows_read, statcast_rows_read, fielding_rows_read,
    batting_rows_using_oaa, batting_rows_using_rf9_fallback, rows_written,
    rows_failed_write, failed_batches
    """

    lg_bat = load_league_batting_averages_row(client, season)
    if lg_bat is None:
        print(
            f"calc_fielding_season_metrics: warning: no league_batting_averages for "
            f"season={season}; skipping.",
            flush=True,
        )
        return (0, 0, 0, 0, 0, 0, 0, 0)

    lg_r = _to_float(lg_bat.get("lg_r"))
    lg_ip = load_league_pitching_ip(client, season)
    if lg_r is None or lg_ip is None or lg_ip <= 0:
        print(
            f"calc_fielding_season_metrics: warning: missing lg_r/lg_ip for "
            f"season={season}; skipping.",
            flush=True,
        )
        return (0, 0, 0, 0, 0, 0, 0, 0)

    rpw = calc_rpw(float(lg_r), float(lg_ip))
    if rpw is None or rpw <= 0:
        print(
            f"calc_fielding_season_metrics: warning: RPW unavailable for "
            f"season={season}; skipping.",
            flush=True,
        )
        return (0, 0, 0, 0, 0, 0, 0, 0)

    # ``game_logs`` league game tally (same helper as other season-metric scripts).
    try:
        _ = get_mlb_games_played(client, season)
    except Exception as exc:  # noqa: BLE001
        print(
            f"calc_fielding_season_metrics: get_mlb_games_played season={season} "
            f"failed ({exc}); continuing.",
            flush=True,
        )

    oaa_sums, oaa_players, statcast_rows = load_statcast_oaa_for_season(client, season)
    fld_rows, fielding_rows_ct = load_player_fielding_season_rows(client, season)

    by_player_fld: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in fld_rows:
        by_player_fld[r["player_id"]].append(r)

    pos_league = build_position_rf9_league(fld_rows)

    payloads: list[dict[str, Any]] = []
    batting_rows_via_oaa = 0
    batting_rows_via_fallback = 0
    batting_read = 0

    offset = 0
    while True:
        try:
            resp = (
                client.table("player_batting_seasons")
                .select("player_id,season,team_id")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_fielding_season_metrics: player_batting_seasons read "
                f"season={season} offset={offset} failed: {exc}",
                flush=True,
            )
            break

        page = resp.data or []
        if not page:
            break

        batting_read += len(page)
        for row in page:
            pid_raw = row.get("player_id")
            tid_raw = row.get("team_id")
            if pid_raw is None or tid_raw is None:
                continue
            try:
                pid_i = int(pid_raw)
                tid_i = int(tid_raw)
            except (TypeError, ValueError):
                continue

            use_oaa = season >= _OAA_FIRST_SEASON and pid_i in oaa_players
            if use_oaa:
                fruns = float(oaa_sums.get(pid_i, 0.0))
                batting_rows_via_oaa += 1
            else:
                pr = by_player_fld.get(pid_i, [])
                fruns = fielding_runs_via_rf9_fallback(pr, pos_league)
                batting_rows_via_fallback += 1

            fwpr = round(fruns / rpw, 1)
            payloads.append(
                {
                    "player_id": pid_i,
                    "season": season,
                    "team_id": tid_i,
                    "fwpr": fwpr,
                }
            )

        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    written, failed_w, failed_b = _flush_fwpr_batches(client, payloads)
    return (
        batting_read,
        statcast_rows,
        fielding_rows_ct,
        batting_rows_via_oaa,
        batting_rows_via_fallback,
        written,
        failed_w,
        failed_b,
    )


def main() -> None:
    args = _parse_args()
    start = args.start_season
    end = args.end_season
    if start > end:
        raise SystemExit(
            f"calc_fielding_season_metrics: --start-season ({start}) must be "
            f"<= --end-season ({end})."
        )

    client = get_client()
    tot_wr = tot_fail = 0
    tot_bat = tot_sc = tot_fld = 0
    tot_oaa_p = tot_fb_p = 0

    for season in range(start, end + 1):
        br, sr, fr, oaa_rows, fb_rows, wr, fw, fb = run_season(client, season)
        tot_bat += br
        tot_sc += sr
        tot_fld += fr
        tot_oaa_p += oaa_rows
        tot_fb_p += fb_rows
        tot_wr += wr
        tot_fail += fw
        print(
            f"calc_fielding_season_metrics: season {season} — "
            f"rows_read(batting)={br}, statcast_oaa_rows={sr}, "
            f"fielding_rows={fr}, oaa_path_batting_rows={oaa_rows}, "
            f"fallback_batting_rows={fb_rows}, rows_written={wr}, "
            f"rows_failed_write={fw}, failed_batches={fb}",
            flush=True,
        )

    print(
        f"calc_fielding_season_metrics: done — "
        f"total_rows_read(batting)={tot_bat}, total_statcast_oaa_rows={tot_sc}, "
        f"total_fielding_rows={tot_fld}, total_oaa_path_batting_rows={tot_oaa_p}, "
        f"total_fallback_batting_rows={tot_fb_p}, total_rows_written={tot_wr}, "
        f"total_failures={tot_fail}",
        flush=True,
    )


if __name__ == "__main__":
    main()
