"""
Load ``player_batting_seasons`` (SCHEMA.md) from 1990 through the current year.

- **Source 1:** MLB Stats API season hitting stats (standard counting / slash lines).
- **Source 2:** pybaseball / FanGraphs ``batting_stats`` (advanced), 2002+ only, joined
  via ``playerid_reverse_lookup`` (FanGraphs ID -> MLBAM) and team abbreviation -> MLB
  team id.

FanGraphs requests are sent with browser-like headers (monkey-patched onto pybaseball's
``requests.get``). If the live fetch returns 403, the script retries using pybaseball's
disk cache when a prior cached response exists.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

import config  # noqa: F401
import pandas as pd
import pybaseball.cache as pb_cache
import requests
from pybaseball import batting_stats, playerid_reverse_lookup
from pybaseball.datasources import html_table_processor as _pybb_html_table

from db import get_client

START_SEASON = 1990
FANGRAPHS_START = 2002
MLB_STATS_URL = (
    "https://statsapi.mlb.com/api/v1/stats"
    "?stats=season&group=hitting&season={season}&sportId=1&limit={limit}&offset={offset}"
)
MLB_TEAMS_URL = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
_BATCH_SIZE = 500
_DELAY_SEC = 2
_FG_DELAY_SEC = 3
_LOOKUP_CHUNK = 150

# Browser-like headers for FanGraphs / pybaseball HTTP (avoids 403 on bot filtering).
_FANGRAPHS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.fangraphs.com/",
}

_FG_HTTP_SESSION = requests.Session()
_FG_HTTP_SESSION.headers.update(_FANGRAPHS_HEADERS)
_ORIG_PYBB_REQUESTS_GET = _pybb_html_table.requests.get

# FanGraphs team abbrev quirks vs MLB ``abbreviation`` on /teams
_FG_TO_MLB_ABBREV = {
    "ARI": "AZ",
    "WSN": "WSH",
    "SFG": "SF",
    "TBR": "TB",
    "KCR": "KC",
    "SDP": "SD",
    "CHW": "CWS",
}

_UPSERT_COLUMNS = (
    "player_id",
    "player_name",
    "season",
    "team_id",
    "team",
    "league",
    "g",
    "ab",
    "pa",
    "r",
    "h",
    "doubles",
    "triples",
    "hr",
    "rbi",
    "sb",
    "cs",
    "bb",
    "so",
    "avg",
    "obp",
    "slg",
    "ops",
    "babip",
    "iso",
    "bb_pct",
    "k_pct",
    "ops_plus",
    "woba",
    "wrc_plus",
    "war",
)


def _patch_pybaseball_requests_for_fangraphs() -> None:
    """Route pybaseball FanGraphs fetches through a browser-like Session."""

    def _patched_get(url: str, **kwargs: Any) -> requests.Response:
        return _FG_HTTP_SESSION.get(url, **kwargs)

    _pybb_html_table.requests.get = _patched_get  # type: ignore[assignment]


def _unpatch_pybaseball_requests() -> None:
    _pybb_html_table.requests.get = _ORIG_PYBB_REQUESTS_GET  # type: ignore[assignment]


def fetch_fangraphs_batting_stats(season: int) -> pd.DataFrame | None:
    """
    Pull FanGraphs batting leaderboard for one season.

    1. Monkey-patch pybaseball to use Session headers, then call ``batting_stats``.
    2. On 403, retry with pybaseball disk cache enabled (no patch) so a prior cached
       dataframe can be returned without a new HTTP request.
    3. If both fail, log and return None.
    """

    _patch_pybaseball_requests_for_fangraphs()
    try:
        df = batting_stats(season, qual=1)
        if df is not None and not df.empty:
            return df
        return None
    except requests.HTTPError as exc:
        err = str(exc)
        if "403" not in err:
            raise
    finally:
        _unpatch_pybaseball_requests()

    cache_was_on = pb_cache.config.enabled
    pb_cache.enable()
    try:
        df = batting_stats(season, qual=1)
        if df is not None and not df.empty:
            print(
                f"seed_player_batting_seasons: FanGraphs season {season} — "
                "using pybaseball disk cache (403 on live fetch).",
                flush=True,
            )
            return df
    except Exception as exc:  # noqa: BLE001
        print(
            f"seed_player_batting_seasons: FanGraphs cache fallback failed "
            f"(season={season}): {exc}",
            flush=True,
        )
    finally:
        if not cache_was_on:
            pb_cache.disable()

    print(
        f"seed_player_batting_seasons: FanGraphs season {season} — "
        "403 and no usable cache; continuing MLB-only for advanced columns.",
        flush=True,
    )
    return None


def fetch_team_abbrev_to_id() -> dict[str, int]:
    """Map uppercase team abbreviation -> MLB team id (all franchises, sportId=1)."""

    req = urllib.request.Request(MLB_TEAMS_URL, headers={"User-Agent": "WARroom-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    out: dict[str, int] = {}
    for t in payload.get("teams") or []:
        tid = t.get("id")
        ab = t.get("abbreviation")
        if tid is None or not isinstance(ab, str):
            continue
        out[ab.strip().upper()] = int(tid)
    return out


def resolve_fg_team_id(raw_team: str, abbrev_to_id: dict[str, int]) -> int | None:
    s = raw_team.strip().upper() if isinstance(raw_team, str) else ""
    if not s or s in ("-", "TOT", "AVG") or "TM" in s or "TMS" in s:
        return None
    if "/" in s:
        return None
    if s in abbrev_to_id:
        return abbrev_to_id[s]
    alt = _FG_TO_MLB_ABBREV.get(s)
    if alt and alt in abbrev_to_id:
        return abbrev_to_id[alt]
    return None


def to_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, bool):
        return int(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def to_pct_float(v: Any) -> float | None:
    """FanGraphs may give 8.2 or 0.082; store as fraction (e.g. 0.082)."""
    x = to_float(v)
    if x is None:
        return None
    if x > 1.0:
        return round(x / 100.0, 4)
    return x


def fetch_mlb_hitting_splits(season: int, limit: int = 1000) -> list[dict[str, Any]]:
    all_splits: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = MLB_STATS_URL.format(season=season, limit=limit, offset=offset)
        req = urllib.request.Request(url, headers={"User-Agent": "WARroom-pipeline/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MLB stats failed season={season}: {exc}") from exc

        stats_blocks = payload.get("stats") or []
        if not stats_blocks:
            break
        splits = stats_blocks[0].get("splits") or []
        all_splits.extend(splits)
        if len(splits) < limit:
            break
        offset += limit
    return all_splits


def split_to_base_row(split: dict[str, Any], season: int) -> dict[str, Any] | None:
    player = split.get("player") or {}
    team = split.get("team") or {}
    stat = split.get("stat") or {}
    league = split.get("league") or {}

    pid = player.get("id")
    if pid is None:
        return None
    tid = team.get("id")

    return {
        "player_id": int(pid),
        "player_name": player.get("fullName"),
        "season": season,
        "team_id": int(tid) if tid is not None else None,
        "team": team.get("name"),
        "league": league.get("name") if isinstance(league, dict) else None,
        "g": to_int(stat.get("gamesPlayed")),
        "ab": to_int(stat.get("atBats")),
        "pa": to_int(stat.get("plateAppearances")),
        "r": to_int(stat.get("runs")),
        "h": to_int(stat.get("hits")),
        "doubles": to_int(stat.get("doubles")),
        "triples": to_int(stat.get("triples")),
        "hr": to_int(stat.get("homeRuns")),
        "rbi": to_int(stat.get("rbi")),
        "sb": to_int(stat.get("stolenBases")),
        "cs": to_int(stat.get("caughtStealing")),
        "bb": to_int(stat.get("baseOnBalls")),
        "so": to_int(stat.get("strikeOuts")),
        "avg": to_float(stat.get("avg")),
        "obp": to_float(stat.get("obp")),
        "slg": to_float(stat.get("slg")),
        "ops": to_float(stat.get("ops")),
        "babip": to_float(stat.get("babip")),
        "iso": None,
        "bb_pct": None,
        "k_pct": None,
        "ops_plus": None,
        "woba": None,
        "wrc_plus": None,
        "war": None,
    }


def fg_id_to_mlbam(fg_ids: list[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    if not fg_ids:
        return out
    for i in range(0, len(fg_ids), _LOOKUP_CHUNK):
        chunk = fg_ids[i : i + _LOOKUP_CHUNK]
        try:
            df = playerid_reverse_lookup(chunk, key_type="fangraphs")
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            kfg = row.get("key_fangraphs")
            mlb = row.get("key_mlbam")
            if kfg is None or mlb is None or pd.isna(mlb):
                continue
            try:
                out[int(kfg)] = int(mlb)
            except (TypeError, ValueError):
                pass
    return out


def _series_get(row: pd.Series, *names: str) -> Any:
    for n in names:
        if n in row.index:
            v = row[n]
            if pd.isna(v):
                return None
            return v
    return None


def build_fg_adv_maps(
    season: int,
    abbrev_to_id: dict[str, int],
) -> tuple[dict[tuple[int, int, int], dict[str, Any]], dict[tuple[int, int], dict[str, Any]]]:
    """
    FanGraphs row keys:
    - Exact: (mlbam, season, team_id) when team abbrev resolves.
    - Fallback: (mlbam, season) for multi-team / ambiguous abbrev rows (last wins).
    """

    adv_exact: dict[tuple[int, int, int], dict[str, Any]] = {}
    adv_fallback: dict[tuple[int, int], dict[str, Any]] = {}

    df = fetch_fangraphs_batting_stats(season)
    if df is None or df.empty:
        return adv_exact, adv_fallback

    if "IDfg" not in df.columns:
        print(f"seed_player_batting_seasons: FanGraphs frame missing IDfg (season={season}).")
        return adv_exact, adv_fallback

    fg_ids = []
    for raw in df["IDfg"].tolist():
        n = to_int(raw)
        if n is not None:
            fg_ids.append(n)
    fg_ids = sorted(set(fg_ids))
    fg_to_mlb = fg_id_to_mlbam(fg_ids)

    for _, row in df.iterrows():
        fg = to_int(_series_get(row, "IDfg"))
        if fg is None:
            continue
        mlb = fg_to_mlb.get(fg)
        if mlb is None:
            continue

        team_raw = _series_get(row, "Team")
        team_id = resolve_fg_team_id(str(team_raw), abbrev_to_id) if team_raw is not None else None

        pack = {
            "iso": to_float(_series_get(row, "ISO")),
            "bb_pct": to_pct_float(_series_get(row, "BB%")),
            "k_pct": to_pct_float(_series_get(row, "K%")),
            "ops_plus": to_int(_series_get(row, "OPS+")),
            "woba": to_float(_series_get(row, "wOBA")),
            "wrc_plus": to_int(_series_get(row, "wRC+")),
            "war": to_float(_series_get(row, "WAR")),
        }

        if team_id is not None:
            adv_exact[(mlb, season, team_id)] = pack
        else:
            adv_fallback[(mlb, season)] = pack

    return adv_exact, adv_fallback


def merge_advanced(
    row: dict[str, Any],
    adv_exact: dict[tuple[int, int, int], dict[str, Any]],
    adv_fallback: dict[tuple[int, int], dict[str, Any]],
) -> None:
    pid = row["player_id"]
    season = row["season"]
    tid = row["team_id"]

    pack = None
    if tid is not None:
        pack = adv_exact.get((pid, season, int(tid)))
    if pack is None:
        pack = adv_fallback.get((pid, season))
    if pack is None:
        return
    row["iso"] = pack.get("iso")
    row["bb_pct"] = pack.get("bb_pct")
    row["k_pct"] = pack.get("k_pct")
    row["ops_plus"] = pack.get("ops_plus")
    row["woba"] = pack.get("woba")
    row["wrc_plus"] = pack.get("wrc_plus")
    row["war"] = pack.get("war")


def row_for_upsert(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in _UPSERT_COLUMNS}


def upsert_batches(rows: list[dict[str, Any]]) -> tuple[int, int]:
    client = get_client()
    ok = 0
    failed = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = [row_for_upsert(r) for r in rows[i : i + _BATCH_SIZE]]
        batch_no = i // _BATCH_SIZE + 1
        try:
            client.table("player_batting_seasons").upsert(
                batch,
                on_conflict="player_id,season,team_id",
            ).execute()
            ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"seed_player_batting_seasons: upsert batch {batch_no} failed: {exc}")
            failed += len(batch)
    return ok, failed


def main() -> None:
    end_year = datetime.now().year
    print(
        f"seed_player_batting_seasons: MLB {START_SEASON}..{end_year}; "
        f"FanGraphs merge from {FANGRAPHS_START}. "
        f"Post-season pause: {_DELAY_SEC}s (pre-{FANGRAPHS_START}), "
        f"{_FG_DELAY_SEC}s for FanGraphs years.",
        flush=True,
    )
    abbrev_to_id = fetch_team_abbrev_to_id()
    print(f"seed_player_batting_seasons: loaded {len(abbrev_to_id)} team abbreviations.", flush=True)

    total_ok = 0
    total_fail = 0
    seasons_run = 0

    for year in range(START_SEASON, end_year + 1):
        splits = fetch_mlb_hitting_splits(year)
        adv_exact: dict[tuple[int, int, int], dict[str, Any]] = {}
        adv_fallback: dict[tuple[int, int], dict[str, Any]] = {}
        fg_msg = "no FanGraphs (year < 2002)"

        if year >= FANGRAPHS_START:
            try:
                adv_exact, adv_fallback = build_fg_adv_maps(year, abbrev_to_id)
                fg_msg = (
                    f"FG keys exact={len(adv_exact)} fallback={len(adv_fallback)}"
                )
            except Exception as exc:  # noqa: BLE001
                fg_msg = f"FanGraphs skip ({exc})"

        merged: list[dict[str, Any]] = []
        for sp in splits:
            base = split_to_base_row(sp, year)
            if base is None:
                continue
            merge_advanced(base, adv_exact, adv_fallback)
            merged.append(base)

        ok, fail = upsert_batches(merged)
        total_ok += ok
        total_fail += fail
        seasons_run += 1

        print(
            f"seed_player_batting_seasons: season {year} — "
            f"MLB splits={len(splits)}, merged_rows={len(merged)}, "
            f"{fg_msg}; upsert_ok_batch={ok}, upsert_fail_batch={fail}",
            flush=True,
        )

        if year < end_year:
            time.sleep(_FG_DELAY_SEC if year >= FANGRAPHS_START else _DELAY_SEC)

    print(
        f"seed_player_batting_seasons: finished — seasons={seasons_run}, "
        f"rows upsert accepted={total_ok}, rows in failed batches={total_fail}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
