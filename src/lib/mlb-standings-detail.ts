import {
  buildPlayoffTeamIdsByLeague,
  isTeamInPlayoffPosition,
} from "@/lib/playoff-teams";

type RawStandingDivision = {
  league?: { id?: number };
  division?: { id?: number; name?: string; nameShort?: string };
  teamRecords?: Array<{
    team?: { id?: number };
    leagueRecord?: { wins?: number; losses?: number; pct?: string };
    gamesBack?: string;
  }>;
};

export type TeamStandingsDetail = {
  wins: number;
  losses: number;
  winPct: string;
  divisionRank: number | null;
  gamesBack: string;
  divisionName: string | null;
  leagueId: number | null;
  playoffPosition: boolean;
};

function winPctNumber(wins: number, losses: number): number {
  const games = wins + losses;
  if (games === 0) return 0;
  return wins / games;
}

function formatWinPct(wins: number, losses: number): string {
  const games = wins + losses;
  if (games === 0) return "—";
  return winPctNumber(wins, losses).toFixed(3).replace(/^0/, "");
}

function parseTeamId(raw: unknown): number | null {
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  return raw;
}

export function parseTeamStandingsDetail(
  teamId: number,
  standingsRecords: unknown,
  wildCardRecords: unknown,
): TeamStandingsDetail | null {
  if (!Array.isArray(standingsRecords)) return null;

  const playoffByLeague = buildPlayoffTeamIdsByLeague(
    standingsRecords,
    wildCardRecords,
  );

  for (const rec of standingsRecords as RawStandingDivision[]) {
    const teamRecords = rec.teamRecords ?? [];
    const divisionName =
      rec.division?.nameShort?.trim() ||
      rec.division?.name?.trim() ||
      null;
    const leagueId = rec.league?.id ?? null;

    const sorted = [...teamRecords]
      .map((tr) => {
        const id = parseTeamId(tr.team?.id);
        const wins = tr.leagueRecord?.wins ?? 0;
        const losses = tr.leagueRecord?.losses ?? 0;
        return {
          id,
          wins,
          losses,
          pct: winPctNumber(wins, losses),
          gamesBack: tr.gamesBack ?? "—",
        };
      })
      .filter((r): r is typeof r & { id: number } => r.id != null)
      .sort((a, b) => {
        if (b.pct !== a.pct) return b.pct - a.pct;
        if (b.wins !== a.wins) return b.wins - a.wins;
        return a.losses - b.losses;
      });

    const idx = sorted.findIndex((r) => r.id === teamId);
    if (idx < 0) continue;

    const row = sorted[idx];
    let rank = idx + 1;
    if (idx > 0 && row.pct === sorted[idx - 1].pct) {
      for (let i = idx - 1; i >= 0; i--) {
        if (sorted[i].pct !== row.pct) break;
        rank = i + 1;
      }
    }

    return {
      wins: row.wins,
      losses: row.losses,
      winPct: formatWinPct(row.wins, row.losses),
      divisionRank: rank,
      gamesBack: row.gamesBack,
      divisionName,
      leagueId,
      playoffPosition: isTeamInPlayoffPosition(
        teamId,
        leagueId,
        playoffByLeague,
      ),
    };
  }

  return null;
}
