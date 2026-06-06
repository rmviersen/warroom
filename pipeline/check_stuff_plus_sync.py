"""
Spot-check: verify statcast_pitching.stuff_plus matches player_pitching_seasons.stuff_plus
for the same pitcher-seasons, and flag any divergence.
"""
from __future__ import annotations
import config  # noqa: F401
from db import get_client

client = get_client()
SEP = "-" * 70

# Pull statcast_pitching stuff_plus for 2024/2025
sp = (
    client.table("statcast_pitching")
    .select("pitcher_id,season,stuff_plus")
    .in_("season", [2024, 2025])
    .not_.is_("stuff_plus", "null")
    .limit(2000)
    .execute()
)
sp_map = {(r["pitcher_id"], r["season"]): float(r["stuff_plus"]) for r in (sp.data or [])}

# Pull player_pitching_seasons stuff_plus for same seasons
pps = (
    client.table("player_pitching_seasons")
    .select("player_id,season,stuff_plus")
    .in_("season", [2024, 2025])
    .not_.is_("stuff_plus", "null")
    .limit(2000)
    .execute()
)
pps_map = {(r["player_id"], r["season"]): float(r["stuff_plus"]) for r in (pps.data or [])}

print(SEP)
print("SYNC CHECK: statcast_pitching vs player_pitching_seasons (2024-2025)")
print(SEP)
print(f"  statcast_pitching rows:       {len(sp_map)}")
print(f"  player_pitching_seasons rows: {len(pps_map)}")

# In sp but not pps
missing_from_pps = [k for k in sp_map if k not in pps_map]
print(f"  In statcast_pitching but NOT player_pitching_seasons: {len(missing_from_pps)}")
if missing_from_pps[:5]:
    print(f"    examples: {missing_from_pps[:5]}")

# In pps but not sp
missing_from_sp = [k for k in pps_map if k not in sp_map]
print(f"  In player_pitching_seasons but NOT statcast_pitching: {len(missing_from_sp)}")

# Diverged values (present in both but different)
diverged = []
for k in sp_map:
    if k in pps_map:
        diff = abs(sp_map[k] - pps_map[k])
        if diff > 0.01:
            diverged.append((k, sp_map[k], pps_map[k], diff))
diverged.sort(key=lambda x: -x[3])
print(f"  Value divergence (diff > 0.01): {len(diverged)}")
if diverged:
    print("  Top diverged pitcher-seasons:")
    for k, sv, pv, d in diverged[:10]:
        print(f"    pitcher={k[0]}  season={k[1]}  statcast={sv}  pps={pv}  diff={round(d,4)}")

# Check Skenes specifically
print()
print(SEP)
print("SKENES (694973) across all sources")
print(SEP)
for season in [2024, 2025, 2026]:
    sv = sp_map.get((694973, season))
    pv = pps_map.get((694973, season))
    # Also fetch arsenal pitch-level
    ar = (
        client.table("statcast_pitching_arsenal")
        .select("pitch_type,stuff_plus_pitch,pitches")
        .eq("pitcher_id", 694973)
        .eq("season", season)
        .not_.is_("stuff_plus_pitch", "null")
        .execute()
    )
    ar_rows = sorted(ar.data or [], key=lambda r: -(r["pitches"] or 0))
    print(f"  {season}  statcast_pitching.stuff_plus={sv}  "
          f"player_pitching_seasons.stuff_plus={pv}")
    for r in ar_rows:
        print(f"         arsenal: {r['pitch_type']:<4} stuff_plus_pitch={r['stuff_plus_pitch']}  "
              f"pitches={r['pitches']}")
