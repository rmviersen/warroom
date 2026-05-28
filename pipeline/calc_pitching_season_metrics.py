"""
Derive pitching rate metrics from ``player_pitching_seasons`` counting columns (no MLB API).

Writes patches via ``upsert_player_pitching_seasons`` so existing counts stay intact
(partial upsert semantics).

League context loads from warehouse tables ``league_pitching_averages`` and
``league_batting_averages`` (via ``calc_league_averages``). Park factor is neutral
``1.0`` for ``era_plus`` and ``pwpr`` until pitcher/historical park factors exist.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime
from typing import Any

import config  # noqa: F401 — loads pipeline/.env before db access

from calculations.pitching_calcs import (
    calc_bb_per_9,
    calc_era_plus_with_lg,
    calc_fip,
    calc_hr_per_9,
    calc_k_bb,
    calc_k_per_9,
    calc_lob_pct,
    calc_pitching_war,
    calc_whip,
)
from db import get_client

_START_DEFAULT = 1990
_PAGE_SIZE = 1000
_RPC_BATCH = 500

_NEUTRAL_PF = 1.0

_SELECT_PITCHERS = (
    "player_id,season,team_id,ip,h,r,er,hr,bb,so,era,g,gs"
)

_METRIC_KEYS = (
    "whip",
    "k_per_9",
    "bb_per_9",
    "hr_per_9",
    "k_bb",
    "fip",
    "era_plus",
    "lob_pct",
    "pwpr",
    "pitcher_role",
)


def _classify_pitcher_role(g: Any, gs: Any) -> str | None:
    """Return 'SP', 'RP', or None based on games-started share.

    Rule: gs / g >= 0.5 → SP; else → RP.
    Returns None when g is zero or unavailable (no appearances recorded).
    """
    try:
        g_int = int(g)
        gs_int = int(gs) if gs is not None else 0
    except (TypeError, ValueError):
        return None
    if g_int <= 0:
        return None
    return "SP" if gs_int / g_int >= 0.5 else "RP"


def get_mlb_games_played(client: Any, season: int) -> float:
    """League-wide game tally for pitching replacement scaling in ``calc_pitching_war``."""
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
            f"calc_pitching_season_metrics: game_logs count unavailable for season={season}"
        )
    return float(n)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Compute derived metrics for player_pitching_seasons from counts; "
            "upsert patches via RPC upsert_player_pitching_seasons."
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


def load_league_pitching_averages_row(client: Any, season: int) -> dict[str, Any] | None:
    """League pitching context for ERA+, FIP constant, pitching WPR (one row per season)."""

    try:
        resp = (
            client.table("league_pitching_averages")
            .select(
                "lg_era,lg_ip,lg_hr,lg_bb,lg_so,fip_constant,lg_fip"
            )
            .eq("season", season)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"calc_pitching_season_metrics: league_pitching_averages read failed "
            f"season={season}: {exc}",
            flush=True,
        )
        return None
    rows = resp.data or []
    if not rows:
        return None
    return rows[0]


def load_league_batting_rp_row(client: Any, season: int) -> dict[str, Any] | None:
    """League batting ``lg_r`` / ``lg_pa`` for RPW inside ``calc_pitching_war``."""

    try:
        resp = (
            client.table("league_batting_averages")
            .select("lg_r,lg_pa")
            .eq("season", season)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"calc_pitching_season_metrics: league_batting_averages read failed "
            f"season={season}: {exc}",
            flush=True,
        )
        return None
    rows = resp.data or []
    if not rows:
        return None
    return rows[0]


def derive_row_payload(
    row: dict[str, Any],
    season: int,
    lg_pitch: dict[str, Any],
    lg_bat_rp: dict[str, Any],
    mlb_games_played: float,
) -> dict[str, Any] | None:
    pid = row.get("player_id")
    if pid is None:
        return None
    try:
        player_id_int = int(pid)
    except (TypeError, ValueError):
        return None

    team_id_raw = row.get("team_id")
    ip_val = _to_float(row.get("ip"))
    if ip_val is None or ip_val <= 0:
        return None

    h = _to_float(row.get("h"))
    r_ct = _to_float(row.get("r"))
    hr = _to_float(row.get("hr"))
    bb = _to_float(row.get("bb"))
    so = _to_float(row.get("so"))

    whip_v = calc_whip(h, bb, ip_val)
    k9 = calc_k_per_9(so, ip_val)
    bb9 = calc_bb_per_9(bb, ip_val)
    hr9 = calc_hr_per_9(hr, ip_val)
    kbb = calc_k_bb(so, bb)

    fipc = _to_float(lg_pitch.get("fip_constant"))
    fip_val = calc_fip(
        hr,
        bb,
        so,
        ip_val,
        int(season),
        fip_constant_override=fipc,
    )

    era_val = _to_float(row.get("era"))
    lg_era_ln = _to_float(lg_pitch.get("lg_era"))
    erap_raw = calc_era_plus_with_lg(era_val, lg_era_ln, park_factor=_NEUTRAL_PF)
    era_plus_i = int(round(erap_raw)) if erap_raw is not None else None

    lob_pct_v = calc_lob_pct(h, bb, hr, r_ct)

    lg_fip_ln = _to_float(lg_pitch.get("lg_fip"))
    lg_r_ln = _to_float(lg_bat_rp.get("lg_r"))
    lg_pa_ln = _to_float(lg_bat_rp.get("lg_pa"))
    lg_ip_ln = _to_float(lg_pitch.get("lg_ip"))

    pwpr_val = calc_pitching_war(
        ip_val,
        fip_val,
        lg_fip_ln,
        lg_r_ln,
        lg_pa_ln,
        lg_ip_ln,
        park_factor=_NEUTRAL_PF,
        mlb_games=mlb_games_played,
    )

    out: dict[str, Any] = {
        "player_id": player_id_int,
        "season": int(season),
    }
    if team_id_raw is not None:
        try:
            out["team_id"] = int(team_id_raw)
        except (TypeError, ValueError):
            out["team_id"] = None
    else:
        out["team_id"] = None

    if whip_v is not None:
        out["whip"] = round(float(whip_v), 3)
    if k9 is not None:
        out["k_per_9"] = round(float(k9), 2)
    if bb9 is not None:
        out["bb_per_9"] = round(float(bb9), 2)
    if hr9 is not None:
        out["hr_per_9"] = round(float(hr9), 2)
    if kbb is not None:
        out["k_bb"] = round(float(kbb), 2)
    if fip_val is not None:
        out["fip"] = round(float(fip_val), 2)
    if era_plus_i is not None:
        out["era_plus"] = era_plus_i
    if lob_pct_v is not None:
        out["lob_pct"] = round(float(lob_pct_v), 4)
    if pwpr_val is not None:
        out["pwpr"] = pwpr_val

    role = _classify_pitcher_role(row.get("g"), row.get("gs"))
    if role is not None:
        out["pitcher_role"] = role

    if not any(k in out for k in _METRIC_KEYS):
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
            client.rpc("upsert_player_pitching_seasons", {"rows": batch}).execute()
            ok_rows += len(batch)
        except Exception as exc:  # noqa: BLE001
            failed_rows += len(batch)
            failed_batches += 1
            print(
                f"calc_pitching_season_metrics: RPC batch {batch_idx}/{n_batches} "
                f"failed ({len(batch)} rows) — {exc}",
                flush=True,
            )
    return ok_rows, failed_rows, failed_batches


def run_season(client: Any, season: int) -> tuple[int, int, int, int, int, float | None]:
    """Returns ``(rows_read, rows_written, rows_skipped, rows_failed_write, failed_batches,
    mlb_games_played_or_none_when_season_skipped)``.
    """

    lg_pitch = load_league_pitching_averages_row(client, season)
    if lg_pitch is None:
        print(
            f"calc_pitching_season_metrics: warning: no league_pitching_averages row for "
            f"season={season}; skipping entire season.",
            flush=True,
        )
        return (0, 0, 0, 0, 0, None)

    lg_bat_rp = load_league_batting_rp_row(client, season)
    if lg_bat_rp is None:
        print(
            f"calc_pitching_season_metrics: warning: no league_batting_averages row for "
            f"season={season}; skipping entire season.",
            flush=True,
        )
        return (0, 0, 0, 0, 0, None)

    mlb_games_played = get_mlb_games_played(client, season)

    rows_read = 0
    payloads: list[dict[str, Any]] = []
    rows_skipped = 0
    offset = 0

    while True:
        try:
            resp = (
                client.table("player_pitching_seasons")
                .select(_SELECT_PITCHERS)
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"calc_pitching_season_metrics: read player_pitching_seasons "
                f"season={season} offset={offset} failed: {exc}",
                flush=True,
            )
            break
        page = resp.data or []
        if not page:
            break
        rows_read += len(page)

        for prow in page:
            ip_ck = _to_float(prow.get("ip"))
            if ip_ck is None or ip_ck <= 0:
                rows_skipped += 1
                continue

            payload = derive_row_payload(
                prow, season, lg_pitch, lg_bat_rp, mlb_games_played
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
            f"calc_pitching_season_metrics: --start-season ({start}) must be "
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
            f"calc_pitching_season_metrics: season {cur} — mlb_games_played={mlg_s}, "
            f"rows_read={rr}, rows_written={rw}, rows_skipped={skipped}, "
            f"failed_batches={fb}.",
            flush=True,
        )
        total_written += rw
        total_failures += rf
        cur += 1

    print(
        f"calc_pitching_season_metrics: done — total_rows_written={total_written}, "
        f"total_failures={total_failures}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
