"""
Temporary probe: MLB Stats API ``sitCodes`` / positional league & player endpoints.

No config/db — urllib only. Safe to delete after investigation.
"""

from __future__ import annotations

import json
import urllib.request

URL1 = (
    "https://statsapi.mlb.com/api/v1/stats"
    "?stats=season&group=hitting&season=2024&sportId=1&playerPool=all"
    "&gameType=R&sitCodes=1&limit=500"
)

URL2 = (
    "https://statsapi.mlb.com/api/v1/stats"
    "?stats=season&group=hitting&season=2024&sportId=1&playerPool=all"
    "&gameType=R&sitCodes=vs_pos&limit=500"
)

URL3 = (
    "https://statsapi.mlb.com/api/v1/people/592450/stats"
    "?stats=season&group=hitting&season=2024&sportId=1&gameType=R&sitCodes=pos"
)

URL4 = (
    "https://statsapi.mlb.com/api/v1/people/592450/stats"
    "?stats=byDayOfWeek&group=hitting&season=2024"
)


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "WARroom-test-stat-splits/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _split_name_pa_pos(sp: dict) -> tuple[str | None, object | None, str | None]:
    pl = sp.get("player") or {}
    st = sp.get("stat") or {}
    pos = sp.get("position") or {}
    return (
        pl.get("fullName") if isinstance(pl.get("fullName"), str) else None,
        st.get("plateAppearances"),
        pos.get("abbreviation") if isinstance(pos, dict) else None,
    )


def probe_url_1_to_3(url: str, title: str) -> None:
    print("=" * 72)
    print(title)
    print(url)
    print("=" * 72)

    data = _fetch_json(url)
    stats_blocks = data.get("stats") or []
    if not stats_blocks:
        print("(no stats blocks)\n")
        return
    block0 = stats_blocks[0]
    total = block0.get("totalSplits")
    splits = block0.get("splits") or []
    print(f"totalSplits (first block): {total!r}")
    print(f"splits len (this payload): {len(splits)}")
    print("\nFirst 3 splits: player | PA | position abbrev:\n")
    for i, sp in enumerate(splits[:3]):
        name, pa, pos_a = _split_name_pa_pos(sp)
        print(f"  [{i}] {name!r} | PA={pa!r} | pos={pos_a!r}")
    print()


def probe_url_4_judge_by_day(url: str, title: str) -> None:
    print("=" * 72)
    print(title)
    print(url)
    print("=" * 72)

    data = _fetch_json(url)
    stats_blocks = data.get("stats") or []
    if not stats_blocks:
        print("(no stats blocks)\n")
        return
    for bi, block in enumerate(stats_blocks):
        total = block.get("totalSplits")
        typ = block.get("type") or {}
        grp = block.get("group") or {}
        print(
            f"\nstats[{bi}] type={typ.get('displayName')!r} "
            f"group={grp.get('displayName')!r} totalSplits={total!r}"
        )
        splits = block.get("splits") or []
        print(f"splits len (this payload): {len(splits)}")
        print("First 2 splits (full JSON):")
        for i, sp in enumerate(splits[:2]):
            print(f"--- split [{i}] ---")
            print(json.dumps(sp, indent=2))
    print()


def main() -> None:
    probe_url_1_to_3(URL1, "URL1: league season hitting, sitCodes=1, limit=500")
    probe_url_1_to_3(URL2, "URL2: league season hitting, sitCodes=vs_pos, limit=500")
    probe_url_1_to_3(URL3, "URL3: Aaron Judge (592450) season hitting, sitCodes=pos")
    probe_url_4_judge_by_day(URL4, "URL4: Aaron Judge byDayOfWeek (split types smoke test)")


if __name__ == "__main__":
    main()
