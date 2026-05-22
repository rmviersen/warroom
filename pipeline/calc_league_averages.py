"""
Aggregate ``player_batting_seasons`` and ``player_pitching_seasons`` by ``season``
into canonical league totals and derived rates.

Writes ``league_batting_averages`` / ``league_pitching_averages`` (warehouse-only;
no MLB API, no ``league_averages.json``).
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from typing import Any

import config  # noqa: F401 — loads pipeline/.env before db access

from calculations.batting_calcs import calc_babip, calc_iso, calc_singles, calc_woba
from db import get_client

_START_DEFAULT = 1990
_PAGE_SIZE = 1000


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Build league batting/pitching average rows from player season tables "
            "(Supabase aggregates only)."
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


def _as_int(val: Any) -> int:
    if val is None:
        return 0
    try:
        if isinstance(val, float) and math.isnan(val):
            return 0
    except TypeError:
        pass
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return 0


def _as_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        if isinstance(val, float) and math.isnan(val):
            return 0.0
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _paginate_batting_season(client: Any, season: int) -> dict[str, int | float]:
    totals = {
        "pa": 0,
        "ab": 0,
        "h": 0,
        "doubles": 0,
        "triples": 0,
        "hr": 0,
        "r": 0,
        "bb": 0,
        "so": 0,
        "hbp": 0,
    }
    offset = 0
    while True:
        try:
            resp = (
                client.table("player_batting_seasons")
                .select("pa,ab,h,doubles,triples,hr,r,bb,so,hbp")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"player_batting_seasons read failed season={season} offset={offset}: {exc}"
            ) from exc
        rows = resp.data or []
        for r in rows:
            totals["pa"] += _as_int(r.get("pa"))
            totals["ab"] += _as_int(r.get("ab"))
            totals["h"] += _as_int(r.get("h"))
            totals["doubles"] += _as_int(r.get("doubles"))
            totals["triples"] += _as_int(r.get("triples"))
            totals["hr"] += _as_int(r.get("hr"))
            totals["r"] += _as_int(r.get("r"))
            totals["bb"] += _as_int(r.get("bb"))
            totals["so"] += _as_int(r.get("so"))
            totals["hbp"] += _as_int(r.get("hbp"))
        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return totals


def _paginate_pitching_season(client: Any, season: int) -> dict[str, float | int]:
    totals: dict[str, float | int] = {"ip": 0.0, "er": 0, "hr": 0, "bb": 0, "so": 0, "h": 0}
    offset = 0
    while True:
        try:
            resp = (
                client.table("player_pitching_seasons")
                .select("ip,er,hr,bb,so,h")
                .eq("season", season)
                .range(offset, offset + _PAGE_SIZE - 1)
                .limit(_PAGE_SIZE)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"player_pitching_seasons read failed season={season} offset={offset}: {exc}"
            ) from exc
        rows = resp.data or []
        for r in rows:
            totals["ip"] = float(totals["ip"]) + _as_float(r.get("ip"))
            totals["er"] = int(totals["er"]) + _as_int(r.get("er"))
            totals["hr"] = int(totals["hr"]) + _as_int(r.get("hr"))
            totals["bb"] = int(totals["bb"]) + _as_int(r.get("bb"))
            totals["so"] = int(totals["so"]) + _as_int(r.get("so"))
            totals["h"] = int(totals["h"]) + _as_int(r.get("h"))
        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return totals


def _build_batting_row(season: int, t: dict[str, int | float]) -> dict[str, Any]:
    lg_pa = int(t["pa"])
    lg_ab = int(t["ab"])
    lg_h = int(t["h"])
    lg_2b = int(t["doubles"])
    lg_3b = int(t["triples"])
    lg_hr = int(t["hr"])
    lg_r = int(t["r"])
    lg_bb = int(t["bb"])
    lg_so = int(t["so"])
    lg_hbp = int(t["hbp"])

    hf, abf = float(lg_h), float(lg_ab)
    twob, threeb = float(lg_2b), float(lg_3b)
    hr_f = float(lg_hr)

    lg_avg = hf / float(lg_ab)
    denom_obp = float(lg_ab + lg_bb + lg_hbp)
    lg_obp = (hf + float(lg_bb) + float(lg_hbp)) / denom_obp if denom_obp != 0 else None

    # TB from singles + weighting doubles/triples/HR — matches slash-line definition.
    singles = lg_h - lg_2b - lg_3b - lg_hr
    lg_tb_num = singles + 2 * lg_2b + 3 * lg_3b + 4 * lg_hr
    lg_slg = float(lg_tb_num) / float(lg_ab) if lg_ab != 0 else None

    lg_ops = lg_obp + lg_slg if lg_obp is not None and lg_slg is not None else None
    lg_iso = calc_iso(lg_slg, lg_avg)

    lg_babip_val = calc_babip(hf, hr_f, abf, float(lg_so), sf=0.0)

    lg_bb_pct = float(lg_bb) / float(lg_pa) if lg_pa != 0 else None
    lg_k_pct = float(lg_so) / float(lg_pa) if lg_pa != 0 else None

    lg_singles_fc = calc_singles(hf, twob, threeb, hr_f)
    # ``calc_woba`` requires ``pa`` denominator (not AB); omit SF league-wide (implicit 0).
    lg_woba = calc_woba(
        float(lg_bb),
        float(lg_hbp),
        lg_singles_fc,
        twob,
        threeb,
        hr_f,
        float(lg_pa),
        season,
    )

    lg_runs_per_pa = float(lg_r) / float(lg_pa) if lg_pa != 0 else None
    lg_wrc_per_pa = lg_runs_per_pa

    return {
        "season": season,
        "lg_pa": lg_pa,
        "lg_ab": lg_ab,
        "lg_h": lg_h,
        "lg_2b": lg_2b,
        "lg_3b": lg_3b,
        "lg_hr": lg_hr,
        "lg_r": lg_r,
        "lg_bb": lg_bb,
        "lg_so": lg_so,
        "lg_hbp": lg_hbp,
        "lg_avg": lg_avg,
        "lg_obp": lg_obp,
        "lg_slg": lg_slg,
        "lg_ops": lg_ops,
        "lg_woba": lg_woba,
        "lg_iso": lg_iso,
        "lg_babip": lg_babip_val,
        "lg_bb_pct": lg_bb_pct,
        "lg_k_pct": lg_k_pct,
        "lg_runs_per_pa": lg_runs_per_pa,
        "lg_wrc_per_pa": lg_wrc_per_pa,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_pitching_row(season: int, t: dict[str, float | int]) -> dict[str, Any]:
    ip_raw = float(t["ip"])
    lg_er = int(t["er"])
    lg_hr = int(t["hr"])
    lg_bb = int(t["bb"])
    lg_so = int(t["so"])
    lg_h = int(t["h"])

    lg_era = (9.0 * float(lg_er) / ip_raw) if ip_raw != 0 else None
    lg_whip = (float(lg_h + lg_bb) / ip_raw) if ip_raw != 0 else None
    lg_k_per_9 = (float(lg_so) * 9.0 / ip_raw) if ip_raw != 0 else None
    lg_bb_per_9 = (float(lg_bb) * 9.0 / ip_raw) if ip_raw != 0 else None
    lg_hr_per_9 = (float(lg_hr) * 9.0 / ip_raw) if ip_raw != 0 else None
    core = (
        (13 * float(lg_hr) + 3 * float(lg_bb) - 2 * float(lg_so)) / ip_raw if ip_raw != 0 else None
    )
    fip_c = (lg_era - core) if lg_era is not None and core is not None else None
    lg_fip = fip_c

    return {
        "season": season,
        "lg_ip": round(ip_raw, 1),
        "lg_er": lg_er,
        "lg_hr": lg_hr,
        "lg_bb": lg_bb,
        "lg_so": lg_so,
        "lg_h": lg_h,
        "lg_era": lg_era,
        "lg_fip": lg_fip,
        "lg_whip": lg_whip,
        "lg_k_per_9": lg_k_per_9,
        "lg_bb_per_9": lg_bb_per_9,
        "lg_hr_per_9": lg_hr_per_9,
        "fip_constant": fip_c,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    args = _parse_args()
    start_s = args.start_season
    end_s = args.end_season
    if start_s > end_s:
        raise SystemExit(
            f"calc_league_averages: --start-season ({start_s}) must be <= "
            f"--end-season ({end_s})."
        )

    client = get_client()
    seasons_written = 0
    total_failures = 0

    for season in range(start_s, end_s + 1):
        bat_totals = _paginate_batting_season(client, season)
        pit_totals = _paginate_pitching_season(client, season)
        lg_ab = int(bat_totals["ab"])
        lg_pa = int(bat_totals["pa"])
        lg_ip = float(pit_totals["ip"])

        batting_ok = False
        pitching_ok = False

        if lg_ab <= 0:
            print(
                f"calc_league_averages: season {season}: skip batting upsert "
                f"(lg_ab={lg_ab}, lg_pa={lg_pa}); no denominator for slash lines.",
                flush=True,
            )
            total_failures += 1
        else:
            try:
                b_row = _build_batting_row(season, bat_totals)
                client.table("league_batting_averages").upsert(
                    b_row, on_conflict="season"
                ).execute()
                batting_ok = True
            except Exception as exc:  # noqa: BLE001
                total_failures += 1
                print(
                    f"calc_league_averages: season {season}: batting upsert failed: {exc}",
                    flush=True,
                )

        if lg_ip <= 0:
            print(
                f"calc_league_averages: season {season}: skip pitching upsert "
                f"(lg_ip={lg_ip}).",
                flush=True,
            )
            total_failures += 1
        else:
            try:
                p_row = _build_pitching_row(season, pit_totals)
                client.table("league_pitching_averages").upsert(
                    p_row, on_conflict="season"
                ).execute()
                pitching_ok = True
            except Exception as exc:  # noqa: BLE001
                total_failures += 1
                print(
                    f"calc_league_averages: season {season}: pitching upsert failed: {exc}",
                    flush=True,
                )

        if batting_ok and pitching_ok:
            seasons_written += 1

        print(
            f"calc_league_averages: season {season}: bat lg_pa={lg_pa} lg_ab={lg_ab}; "
            f"pitch lg_ip={lg_ip}; batting_ok={batting_ok} pitching_ok={pitching_ok}.",
            flush=True,
        )

    print(
        f"calc_league_averages: finished — seasons_written={seasons_written}, "
        f"total_failures={total_failures}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
