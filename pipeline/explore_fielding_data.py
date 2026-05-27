"""
Explore fielding data available through pybaseball and direct Baseball Savant CSV URLs.

`statcast_fielding` in pybaseball is a submodule (exported functions listed in its __init__);
there is no single `statcast_fielding(...)` callable.

Run from repo root::

    python pipeline/explore_fielding_data.py

Only the 2025 OAA ``min`` / no-``pos`` probes (quick)::

    python pipeline/explore_fielding_data.py --oaa-min-probe-only
"""

from __future__ import annotations

import io
import sys
import traceback
from typing import Any, Callable
from urllib.parse import urlencode

import pandas as pd
import requests


# Recent season with broadly complete leaderboards when this script runs.
YEAR = 2025


def sep_line(title: str) -> None:
    s = "=" * 80
    print(f"\n{s}\n{title}\n{s}")


def try_savant_csv(url: str) -> tuple[bool, pd.DataFrame | None, str | None]:
    """
    GET URL; returns (parsed_ok, dataframe_or_None, error_or_None).
    HTML responses are treated as not parsed_ok.
    """
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return False, None, f"HTTP/request error: {type(exc).__name__}: {exc}"

    raw = r.text.strip()
    if raw.lstrip().startswith("<!DOCTYPE html") or raw.lstrip().lower().startswith("<html"):
        return False, None, f"Unexpected HTML ({len(raw)} chars), starts: {raw[:120]!r}..."

    try:
        df = pd.read_csv(io.StringIO(raw))
    except Exception as exc:  # noqa: BLE001
        return False, None, f"pandas.parse error: {type(exc).__name__}: {exc}"

    return True, df, None


def explore_oaa_ss_min_variants_year_2025() -> None:
    """
    2025 SS (pos=6): row counts with min=1 vs no min parameter; plus all-position
    min=1 feed and duplicate player_id / primary_pos_formatted check.
    """
    year = 2025
    pos_ss = "6"
    sep_line(f"Savant OAA CSV probes | season={year} SS pos={pos_ss} min=1 vs no min")

    qs_min1_ss = urlencode(
        {
            "type": "Fielder",
            "year": str(year),
            "team": "",
            "range": "year",
            "min": "1",
            "pos": pos_ss,
            "roles": "",
            "viz": "hide",
            "csv": "true",
        }
    )
    url_min1_ss = f"https://baseballsavant.mlb.com/leaderboard/outs_above_average?{qs_min1_ss}"
    print("SS min=1")
    print(f"URL: {url_min1_ss}")
    ok, df_min1_ss, err = try_savant_csv(url_min1_ss)
    if ok and df_min1_ss is not None:
        print(f"row_count={len(df_min1_ss)}")
    else:
        print(f"row_count=N/A ({err})")

    qs_no_min_ss_pairs = (
        ("type", "Fielder"),
        ("year", str(year)),
        ("team", ""),
        ("range", "year"),
        ("pos", pos_ss),
        ("roles", ""),
        ("viz", "hide"),
        ("csv", "true"),
    )
    qs_no_min_ss = urlencode(qs_no_min_ss_pairs)
    url_no_min_ss = f"https://baseballsavant.mlb.com/leaderboard/outs_above_average?{qs_no_min_ss}"
    print("")
    print("SS with no min= parameter at all")
    print(f"URL: {url_no_min_ss}")
    ok, df_no_min_ss, err = try_savant_csv(url_no_min_ss)
    if ok and df_no_min_ss is not None:
        print(f"row_count={len(df_no_min_ss)}")
    else:
        print(f"row_count=N/A ({err})")

    sep_line(
        "Player-level OAA? | outs_above_average year=2025 min=1 empty pos="
        "(all positions in one CSV if supported)"
    )
    url_no_pos_min1 = (
        "https://baseballsavant.mlb.com/leaderboard/outs_above_average?"
        "type=Fielder&year=2025&team=&range=year&min=1&pos=&roles=&viz=hide&csv=true"
    )
    print(f"URL: {url_no_pos_min1}")
    ok, df_all, err = try_savant_csv(url_no_pos_min1)
    if not ok or df_all is None:
        print(f"row_count=N/A ({err})")
        return

    print(f"row_count={len(df_all)}")

    if "player_id" not in df_all.columns:
        print("primary_pos_multival_per_player=N/A (no player_id column)")
        print(f"columns={list(df_all.columns)}")
        return

    if "primary_pos_formatted" not in df_all.columns:
        print("primary_pos_multival_per_player=N/A (no primary_pos_formatted column)")
        print(f"columns={list(df_all.columns)}")
        return

    g = df_all.groupby("player_id", sort=False)["primary_pos_formatted"].nunique()
    n_players_any = int(g.size)
    n_players_multiple_pos_strings = int((g > 1).sum())
    n_dup_rows = (
        int(df_all["player_id"].duplicated().sum()) if len(df_all) else 0
    )
    multi = n_players_multiple_pos_strings > 0
    print(
        f"n_distinct_player_id={n_players_any} "
        f"n_duplicate_player_id_rows={n_dup_rows} "
        f"n_player_id_with_multiple_primary_pos_strings={n_players_multiple_pos_strings}"
    )
    print(
        "has_any_player_id_with_multiple_distinct_primary_pos_formatted: "
        f"{multi}"
    )


def print_oaa_position_year_probe(year: int, pos: str) -> None:
    """Single Savant Outs Above Average CSV probe; columns + row count only."""
    qs = urlencode(
        {
            "type": "Fielder",
            "year": str(year),
            "team": "",
            "range": "year",
            "min": "q",
            "pos": str(pos),
            "roles": "",
            "viz": "hide",
            "csv": "true",
        }
    )
    url = f"https://baseballsavant.mlb.com/leaderboard/outs_above_average?{qs}"
    sep_line(f"Savant OAA CSV unified leaderboard | year={year} pos={pos}")
    print(f"URL: {url}")
    ok, df, err = try_savant_csv(url)
    if not ok or df is None:
        print(f"rows=N/A cols=N/A — {err}")
        return
    cols = list(df.columns)
    print(f"rows: {len(df)}")
    print(f"cols ({len(cols)}): {cols}")


def explore_oaa_by_position_codes_for_seasons(
    *,
    seasons: tuple[int, ...],
    positions: tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7", "8", "9"),
) -> None:
    sep_line(
        "OAA availability matrix: Baseball Savant unified CSV "
        f"(leaderboard/outs_above_average) min=qualified seasons={seasons} "
        f"positions={'-'.join(positions)}"
    )
    print(
        "Numeric MLB position codes: 1=P, 2=C, 3=1B, 4=2B, 5=3B, 6=SS, "
        "7=LF, 8=CF, 9=RF (per MLB / Savant primary position filters)."
    )
    for y in seasons:
        for pos in positions:
            print_oaa_position_year_probe(y, pos)


def explore_infield_oaa_leaderboard_path(*, seasons: tuple[int, ...]) -> None:
    """
    Dedicated infield leaderboard page path on Savant. Historically SPA-only --
    probes whether csv=true yields parseable CSV (vs HTML) vs startYear/endYear form.
    """
    base = "https://baseballsavant.mlb.com/leaderboard/infield_outs_above_average"
    sep_line(f"Infield OAA dedicated path | {base} | seasons={seasons}")
    print(
        "Also reporting unified leaderboard row counts for SS (pos=6) with min=q for "
        "2015-2019 to localize when positional OAA CSV first has qualifying rows."
    )

    for year in seasons:
        for label, qs in (
            (
                "query style: year=&split implied",
                urlencode(
                    {
                        "type": "Fielder",
                        "year": str(year),
                        "team": "",
                        "range": "year",
                        "min": "q",
                        "pos": "6",
                        "roles": "",
                        "viz": "hide",
                        "csv": "true",
                    }
                ),
            ),
            (
                "query style: startYear=&endYear=&split=no",
                urlencode(
                    {
                        "type": "Fielder",
                        "startYear": str(year),
                        "endYear": str(year),
                        "split": "no",
                        "team": "",
                        "range": "year",
                        "min": "q",
                        "pos": "6",
                        "roles": "",
                        "viz": "hide",
                        "csv": "true",
                    }
                ),
            ),
        ):
            url = f"{base}?{qs}"
            print(f"\n--- year={year} | {label}")
            print(f"URL: {url}")
            ok, df, err = try_savant_csv(url)
            if ok and df is not None:
                cols = list(df.columns)
                print(f"Parsed CSV OK | rows={len(df)} cols ({len(cols)}): {cols}")
                print("(first row sample)")
                print(df.head(1).to_string(index=False))
            else:
                print(f"NOT parseable CSV: {err}")

    sep_line("Unified leaderboard /outs_above_average | SS pos=6 min=q (year sweep 2015-2019)")
    for year in range(2015, 2020):
        qs = urlencode(
            {
                "type": "Fielder",
                "year": str(year),
                "team": "",
                "range": "year",
                "min": "q",
                "pos": "6",
                "roles": "",
                "viz": "hide",
                "csv": "true",
            }
        )
        url = f"https://baseballsavant.mlb.com/leaderboard/outs_above_average?{qs}"
        ok, df, err = try_savant_csv(url)
        if ok and df is not None:
            print(f"year={year} rows={len(df)} cols={len(df.columns)} columns={list(df.columns)}")
        else:
            print(f"year={year} FAILED: {err}")

    sep_line(
        "Unified leaderboard /outs_above_average | IF corner (3B pos=5) min=q (year sweep 2015-2019)"
    )
    for year in range(2015, 2020):
        qs = urlencode(
            {
                "type": "Fielder",
                "year": str(year),
                "team": "",
                "range": "year",
                "min": "q",
                "pos": "5",
                "roles": "",
                "viz": "hide",
                "csv": "true",
            }
        )
        url = f"https://baseballsavant.mlb.com/leaderboard/outs_above_average?{qs}"
        ok, df, err = try_savant_csv(url)
        if ok and df is not None:
            print(f"year={year} rows={len(df)} cols={len(df.columns)} columns={list(df.columns)}")
        else:
            print(f"year={year} FAILED: {err}")

    sep_line(
        "Summary: CSV via dedicated infield leaderboard path vs unified outs_above_average"
    )
    print(
        "- If every attempt under /leaderboard/infield_outs_above_average returns HTML, "
        "Savant is not exposing that surface as a CSV for these query strings "
        "(see messages above)."
    )
    print(
        "- The unified /leaderboard/outs_above_average CSV returns positional OAA splits "
        "for each numeric pos=3..9; earliest non-empty qualified rows in this probe "
        "for SS / 3B appear when year>=2016 (see year sweep)."
    )
    print(
        "- Dedicated /leaderboard/infield_outs_above_average: CSV not returned "
        "(HTML app shell) for 2016-2019 above, so programmatic year-onset "
        "cannot be read from THAT path; use unified outs_above_average for CSV."
    )


def report_df(title: str, df: pd.DataFrame) -> None:
    sep_line(title)
    cols = list(df.columns)
    print(f"Columns ({len(cols)}): {cols}")
    print("\nSample (first 5 rows):")
    n = min(5, len(df))
    if n == 0:
        print("(empty frame)")
        return
    print(df.head(5).to_string())


def safe_call(title: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    try:
        out = fn(*args, **kwargs)
        if not isinstance(out, pd.DataFrame):
            sep_line(title)
            print(f"Returned type {type(out)!r} (expected DataFrame)")
            print(repr(out)[:2000])
            return
        report_df(title, out)
    except Exception as exc:  # noqa: BLE001 — exploration script
        sep_line(title)
        print(f"FAILED: {type(exc).__name__}: {exc}")
        print(traceback.format_exc())


def direct_savant_csv(title: str, url: str) -> None:
    ok, df, err = try_savant_csv(url)
    if not ok or df is None:
        sep_line(title)
        print(err)
        return
    report_df(title, df)


def main() -> None:
    explore_oaa_ss_min_variants_year_2025()

    # --- New probes (historical positions / infield leaderboard path) ---
    explore_oaa_by_position_codes_for_seasons(seasons=(2016, 2018))
    explore_infield_oaa_leaderboard_path(seasons=(2016, 2017, 2018, 2019))

    from pybaseball import (
        fielding_stats,
        statcast_catcher_framing,
        statcast_catcher_poptime,
        statcast_outfield_catch_prob,
        statcast_outfield_directional_oaa,
        statcast_outfielder_jump,
        statcast_outs_above_average,
    )

    print(f"\n\n{'#' * 80}\n# Earlier exploration snapshot (recent season={YEAR})\n{'#' * 80}")

    safe_call(
        f"pybaseball.statcast_outs_above_average({YEAR}, pos=8, min_att=\"q\")  # outfield",
        statcast_outs_above_average,
        YEAR,
        8,
        "q",
    )
    safe_call(
        f"pybaseball.statcast_outfield_directional_oaa({YEAR})",
        statcast_outfield_directional_oaa,
        YEAR,
    )
    safe_call(
        f"pybaseball.statcast_outfield_catch_prob({YEAR})",
        statcast_outfield_catch_prob,
        YEAR,
    )
    safe_call(
        f"pybaseball.statcast_outfielder_jump({YEAR})",
        statcast_outfielder_jump,
        YEAR,
    )
    safe_call(
        f"pybaseball.statcast_catcher_poptime({YEAR})",
        statcast_catcher_poptime,
        YEAR,
    )
    safe_call(
        f"pybaseball.statcast_catcher_framing({YEAR})",
        statcast_catcher_framing,
        YEAR,
    )

    safe_call(
        f"pybaseball.fielding_stats(start_season={YEAR}, end_season={YEAR}, qual=250)",
        fielding_stats,
        YEAR,
        YEAR,
        qual=250,
    )

    try:
        from pybaseball import fielding as lahman_fielding

        lah = lahman_fielding()
        sub = lah.loc[lah["yearID"] == YEAR].copy()
        report_df(f"pybaseball.fielding() filtered to yearID=={YEAR}", sub.head(500))
    except Exception as exc:  # noqa: BLE001
        sep_line("lahman fielding()")
        print(f"FAILED: {type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    oaa_url = (
        "https://baseballsavant.mlb.com/leaderboard/outs_above_average?"
        "type=Fielder&year={year}&team=&range=year&min=q&pos=6&roles=&viz=show&csv=true"
    ).format(year=YEAR)
    direct_savant_csv(
        "Direct Savant GET: OAA leaderboard (SS pos=6, qualified, Fielder view)",
        oaa_url,
    )

    extras = [
        (
            "Direct Savant GET: outfield jump leaderboard",
            f"https://baseballsavant.mlb.com/leaderboard/outfield_jump?year={YEAR}&min=q&csv=true",
        ),
        (
            "Direct Savant GET: catch probability (player)",
            f"https://baseballsavant.mlb.com/leaderboard/catch_probability?type=player&min=q&year={YEAR}&total=&csv=true",
        ),
        (
            "Direct Savant GET: catcher framing (pybaseball URL; historically csv=true)",
            f"https://baseballsavant.mlb.com/catcher_framing?year={YEAR}&team=&min=q&sort=4,1&csv=true",
        ),
        (
            "Direct Savant GET: directional OAA leaderboard",
            f"https://baseballsavant.mlb.com/directional_outs_above_average?year={YEAR}&min=q&team=&csv=true",
        ),
    ]
    for t, u in extras:
        direct_savant_csv(t, u)


if __name__ == "__main__":
    if "--oaa-min-probe-only" in sys.argv:
        explore_oaa_ss_min_variants_year_2025()
    else:
        main()
