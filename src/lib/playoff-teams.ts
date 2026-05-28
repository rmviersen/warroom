const AL_LEAGUE_ID = 103;
const NL_LEAGUE_ID = 104;

/** Brand gold — playoff position row highlight. */
export const PLAYOFF_GOLD = "#b8922a";

export const playoffRowClass = (playoff: boolean): string =>
  playoff
    ? "bg-gradient-to-r from-[#b8922a]/12 via-[#b8922a]/5 to-transparent"
    : "";

export const playoffFirstCellClass = (playoff: boolean): string =>
  playoff ? "border-l-2 border-l-[#b8922a] pl-1.5" : "";

export type PlayoffDivisionRow = {
  teamId: number;
  gamesBack: string;
};

export type PlayoffWildCardRow = {
  teamId: number;
  wildCardGamesBack: string;
};

type LeaguePlayoffInput = {
  divisionRows: PlayoffDivisionRow[];
  wildCardRows: PlayoffWildCardRow[];
};

type RawStandingDivision = {
  league?: { id?: number };
  teamRecords?: Array<{
    team?: { id?: number };
    gamesBack?: string;
  }>;
};

type RawWildCardRecord = {
  league?: { id?: number };
  teamRecords?: Array<{
    team?: { id?: number };
    wildCardGamesBack?: string;
  }>;
};

export function isDivisionLeader(gamesBack: string): boolean {
  const t = gamesBack.trim();
  return t === "" || t === "-" || t === "—" || t === "0" || t === "0.0";
}

/**
 * MLB ``wildCardGamesBack`` encoding:
 * - ``+1.5`` → ahead of the last WC berth
 * - ``-`` / ``0`` → tied for a WC spot or division leader in WC view
 * - ``0.5`` / ``1.0`` (no plus) → games **behind** the WC cutoff
 */
export function isWildCardPlayoffPosition(wildCardGamesBack: string): boolean {
  const t = wildCardGamesBack.trim();
  if (t === "" || t === "-" || t === "—") return true;
  if (t.startsWith("+")) return true;
  if (t === "0" || t === "0.0") return true;
  return false;
}

export function getDivisionLeaderIds(
  divisionRows: PlayoffDivisionRow[],
): Set<number> {
  const ids = new Set<number>();
  for (const row of divisionRows) {
    if (isDivisionLeader(row.gamesBack)) {
      ids.add(row.teamId);
    }
  }
  return ids;
}

export function getWildCardHighlightTeamIds(
  wildCardRows: PlayoffWildCardRow[],
): Set<number> {
  const highlighted = new Set<number>();
  for (const row of wildCardRows) {
    if (isWildCardPlayoffPosition(row.wildCardGamesBack)) {
      highlighted.add(row.teamId);
    }
  }
  return highlighted;
}

function emptyLeagueInput(): LeaguePlayoffInput {
  return { divisionRows: [], wildCardRows: [] };
}

export function parseLeaguePlayoffInputs(
  standingsRecords: unknown,
  wildCardRecords: unknown,
): { al: LeaguePlayoffInput; nl: LeaguePlayoffInput } {
  const al = emptyLeagueInput();
  const nl = emptyLeagueInput();

  if (Array.isArray(standingsRecords)) {
    for (const rec of standingsRecords as RawStandingDivision[]) {
      const leagueId = rec.league?.id;
      const bucket =
        leagueId === AL_LEAGUE_ID ? al : leagueId === NL_LEAGUE_ID ? nl : null;
      if (!bucket) continue;

      for (const tr of rec.teamRecords ?? []) {
        const teamId = tr.team?.id;
        if (typeof teamId !== "number" || !Number.isFinite(teamId)) continue;
        bucket.divisionRows.push({
          teamId,
          gamesBack: tr.gamesBack ?? "—",
        });
      }
    }
  }

  if (Array.isArray(wildCardRecords)) {
    for (const rec of wildCardRecords as RawWildCardRecord[]) {
      const leagueId = rec.league?.id;
      const bucket =
        leagueId === AL_LEAGUE_ID ? al : leagueId === NL_LEAGUE_ID ? nl : null;
      if (!bucket) continue;

      for (const tr of rec.teamRecords ?? []) {
        const teamId = tr.team?.id;
        if (typeof teamId !== "number" || !Number.isFinite(teamId)) continue;
        bucket.wildCardRows.push({
          teamId,
          wildCardGamesBack: tr.wildCardGamesBack ?? "—",
        });
      }
    }
  }

  return { al, nl };
}

function buildLeaguePlayoffPositionIds(input: LeaguePlayoffInput): Set<number> {
  const divisionLeaderIds = getDivisionLeaderIds(input.divisionRows);
  const wildCardIds = getWildCardHighlightTeamIds(input.wildCardRows);
  return new Set([...divisionLeaderIds, ...wildCardIds]);
}

/** All teams in current playoff position for a league (teams page). */
export function buildPlayoffTeamIdsByLeague(
  standingsRecords: unknown,
  wildCardRecords: unknown,
): { al: Set<number>; nl: Set<number> } {
  const { al, nl } = parseLeaguePlayoffInputs(
    standingsRecords,
    wildCardRecords,
  );

  return {
    al: buildLeaguePlayoffPositionIds(al),
    nl: buildLeaguePlayoffPositionIds(nl),
  };
}

export function isTeamInPlayoffPosition(
  teamId: number,
  leagueId: number | null,
  playoffByLeague: { al: Set<number>; nl: Set<number> },
): boolean {
  if (leagueId === AL_LEAGUE_ID) return playoffByLeague.al.has(teamId);
  if (leagueId === NL_LEAGUE_ID) return playoffByLeague.nl.has(teamId);
  return false;
}
