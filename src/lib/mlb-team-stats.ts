import type { TeamSeasonStats } from "@/types";

type MlbStatSplit = {
  season?: string | number;
  gameType?: string;
  stat?: Record<string, unknown>;
};

type MlbStatGroup = {
  type?: { displayName?: string };
  group?: { displayName?: string };
  splits?: MlbStatSplit[];
};

function pickTeamSeasonSplit(
  splits: MlbStatSplit[] | undefined,
  seasonYear: number,
): MlbStatSplit | null {
  if (!splits?.length) return null;
  const seasonStr = String(seasonYear);
  const matching = splits.filter((s) => String(s.season) === seasonStr);
  const pool = matching.length ? matching : splits;
  return pool[0] ?? null;
}

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

/**
 * Parse MLB ``/teams/{id}/stats`` ``stats`` array for one season (hitting + pitching).
 */
export function parseMlbTeamSeasonStats(
  stats: unknown,
  seasonYear: number,
): TeamSeasonStats | null {
  if (!Array.isArray(stats)) return null;

  const groups = stats as MlbStatGroup[];
  const isSeason = (g: MlbStatGroup) =>
    g.type?.displayName?.toLowerCase() === "season";

  const hittingGroup = groups.find(
    (g) => isSeason(g) && g.group?.displayName?.toLowerCase() === "hitting",
  );
  const pitchingGroup = groups.find(
    (g) => isSeason(g) && g.group?.displayName?.toLowerCase() === "pitching",
  );

  const hitSplit = pickTeamSeasonSplit(hittingGroup?.splits, seasonYear);
  const pitchSplit = pickTeamSeasonSplit(pitchingGroup?.splits, seasonYear);

  const hs = hitSplit?.stat as Record<string, unknown> | undefined;
  const ps = pitchSplit?.stat as Record<string, unknown> | undefined;

  const hitting = hs
    ? {
        avg: str(hs.avg),
        ops: str(hs.ops),
        homeRuns: num(hs.homeRuns),
        rbi: num(hs.rbi),
        runs: num(hs.runs),
      }
    : null;

  const pitching = ps
    ? {
        era: str(ps.era),
        whip: str(ps.whip),
        strikeOuts: num(ps.strikeOuts),
        baseOnBalls: num(ps.baseOnBalls),
        saves: num(ps.saves),
      }
    : null;

  if (!hitting && !pitching) return null;

  return {
    season: seasonYear,
    hitting,
    pitching,
  };
}
