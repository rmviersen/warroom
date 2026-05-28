import type { Team, TeamOverview, TeamOverviewStat } from "@/types";
import {
  buildPlayoffTeamIdsByLeague,
  isTeamInPlayoffPosition,
} from "@/lib/playoff-teams";

type MlbDivision = { id?: number; name?: string };
type MlbLeague = { id?: number; name?: string };

type MlbTeamRaw = {
  id: number;
  name?: string;
  abbreviation?: string;
  teamName?: string;
  locationName?: string;
  division?: MlbDivision;
  league?: MlbLeague;
};

type BulkStatSplit = {
  team?: { id?: number };
  stat?: Record<string, unknown>;
};

type BulkStatGroup = {
  splits?: BulkStatSplit[];
};

type StandingTeamRecord = {
  team?: { id?: number };
  leagueRecord?: { wins?: number; losses?: number };
};

type StandingRecord = {
  teamRecords?: StandingTeamRecord[];
};

function num(v: unknown): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function str(v: unknown): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s === "" ? null : s;
}

export function mapMlbTeam(team: MlbTeamRaw): Team {
  return {
    id: team.id,
    name: team.name ?? null,
    abbreviation: team.abbreviation ?? null,
    team_name: team.teamName ?? null,
    location_name: team.locationName ?? null,
    division: team.division?.name ?? null,
    division_id: team.division?.id ?? null,
    league: team.league?.name ?? null,
    league_id: team.league?.id ?? null,
  };
}

export function parseTeamRecordsFromStandings(
  records: unknown,
): Map<number, { wins: number; losses: number }> {
  const map = new Map<number, { wins: number; losses: number }>();
  if (!Array.isArray(records)) return map;

  for (const rec of records as StandingRecord[]) {
    for (const tr of rec.teamRecords ?? []) {
      const id = tr.team?.id;
      if (typeof id !== "number" || !Number.isFinite(id)) continue;
      map.set(id, {
        wins: tr.leagueRecord?.wins ?? 0,
        losses: tr.leagueRecord?.losses ?? 0,
      });
    }
  }

  return map;
}

function parseBulkTeamStats(raw: unknown): Map<number, Record<string, unknown>> {
  const map = new Map<number, Record<string, unknown>>();
  if (!raw || typeof raw !== "object") return map;

  const stats = (raw as { stats?: BulkStatGroup[] }).stats;
  const splits = stats?.[0]?.splits;
  if (!Array.isArray(splits)) return map;

  for (const split of splits) {
    const id = split.team?.id;
    if (typeof id !== "number" || !Number.isFinite(id)) continue;
    map.set(id, split.stat ?? {});
  }

  return map;
}

function rankByValue(
  entries: { id: number; value: number | null }[],
  lowerIsBetter: boolean,
): Map<number, number> {
  const valid = entries.filter(
    (e): e is { id: number; value: number } => e.value != null,
  );
  valid.sort((a, b) =>
    lowerIsBetter ? a.value - b.value : b.value - a.value,
  );

  const ranks = new Map<number, number>();
  let rank = 1;
  for (let i = 0; i < valid.length; i++) {
    if (i > 0 && valid[i].value !== valid[i - 1].value) {
      rank = i + 1;
    }
    ranks.set(valid[i].id, rank);
  }
  return ranks;
}

function statCell(
  value: string | null,
  rank: number | null | undefined,
): TeamOverviewStat {
  return { value, rank: rank ?? null };
}

function divisionSortKey(name: string | null): number {
  if (!name) return 99;
  if (name.includes("East")) return 0;
  if (name.includes("Central")) return 1;
  if (name.includes("West")) return 2;
  return 3;
}

function teamSortKey(team: TeamOverview): string {
  return team.name ?? "";
}

export function buildTeamOverviews(input: {
  teams: MlbTeamRaw[];
  standingsRecords: unknown;
  wildCardRecords: unknown;
  hittingStats: unknown;
  pitchingStats: unknown;
}): TeamOverview[] {
  const records = parseTeamRecordsFromStandings(input.standingsRecords);
  const playoffByLeague = buildPlayoffTeamIdsByLeague(
    input.standingsRecords,
    input.wildCardRecords,
  );
  const hitting = parseBulkTeamStats(input.hittingStats);
  const pitching = parseBulkTeamStats(input.pitchingStats);
  const mapped = input.teams.map(mapMlbTeam);

  const eraValues = mapped.map((t) => ({
    id: t.id,
    value: num(pitching.get(t.id)?.era),
  }));
  const whipValues = mapped.map((t) => ({
    id: t.id,
    value: num(pitching.get(t.id)?.whip),
  }));
  const avgValues = mapped.map((t) => ({
    id: t.id,
    value: num(hitting.get(t.id)?.avg),
  }));
  const slgValues = mapped.map((t) => ({
    id: t.id,
    value: num(hitting.get(t.id)?.slg),
  }));
  const opsValues = mapped.map((t) => ({
    id: t.id,
    value: num(hitting.get(t.id)?.ops),
  }));
  const hrValues = mapped.map((t) => ({
    id: t.id,
    value: num(hitting.get(t.id)?.homeRuns),
  }));
  const rsValues = mapped.map((t) => ({
    id: t.id,
    value: num(hitting.get(t.id)?.runs),
  }));
  const raValues = mapped.map((t) => ({
    id: t.id,
    value: num(pitching.get(t.id)?.runs),
  }));

  const eraRanks = rankByValue(eraValues, true);
  const whipRanks = rankByValue(whipValues, true);
  const avgRanks = rankByValue(avgValues, false);
  const slgRanks = rankByValue(slgValues, false);
  const opsRanks = rankByValue(opsValues, false);
  const hrRanks = rankByValue(hrValues, false);
  const rsRanks = rankByValue(rsValues, false);
  const raRanks = rankByValue(raValues, true);

  const overviews: TeamOverview[] = mapped.map((team) => {
    const hs = hitting.get(team.id);
    const ps = pitching.get(team.id);
    const rec = records.get(team.id);

    return {
      id: team.id,
      name: team.name,
      abbreviation: team.abbreviation,
      division: team.division,
      league: team.league,
      league_id: team.league_id ?? null,
      wins: rec?.wins ?? 0,
      losses: rec?.losses ?? 0,
      playoff_position: isTeamInPlayoffPosition(
        team.id,
        team.league_id ?? null,
        playoffByLeague,
      ),
      pitching: {
        era: statCell(str(ps?.era), eraRanks.get(team.id)),
        whip: statCell(str(ps?.whip), whipRanks.get(team.id)),
        runsAllowed: statCell(
          ps?.runs != null ? String(ps.runs) : null,
          raRanks.get(team.id),
        ),
      },
      hitting: {
        avg: statCell(str(hs?.avg), avgRanks.get(team.id)),
        slg: statCell(str(hs?.slg), slgRanks.get(team.id)),
        ops: statCell(str(hs?.ops), opsRanks.get(team.id)),
        homeRuns: statCell(
          hs?.homeRuns != null ? String(hs.homeRuns) : null,
          hrRanks.get(team.id),
        ),
        runsScored: statCell(
          hs?.runs != null ? String(hs.runs) : null,
          rsRanks.get(team.id),
        ),
      },
    };
  });

  return overviews.sort((a, b) => {
    const leagueDiff = (a.league_id ?? 999) - (b.league_id ?? 999);
    if (leagueDiff !== 0) return leagueDiff;
    const divDiff =
      divisionSortKey(a.division) - divisionSortKey(b.division);
    if (divDiff !== 0) return divDiff;
    return teamSortKey(a).localeCompare(teamSortKey(b));
  });
}
