import type {
  MlbSeasonHittingLine,
  MlbSeasonPitchingLine,
  PlayerProfileMlbStats,
} from "@/types";

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

function pickRegularSeasonSplit(
  splits: MlbStatSplit[] | undefined,
  seasonYear: number,
): MlbStatSplit | null {
  if (!splits?.length) return null;
  const seasonStr = String(seasonYear);
  const regular = splits.filter(
    (s) =>
      String(s.season) === seasonStr &&
      (s.gameType == null || s.gameType === "R"),
  );
  const pool = regular.length > 0 ? regular : splits.filter((s) => String(s.season) === seasonStr);
  if (pool.length === 0) return null;
  return pool.reduce((best, cur) => {
    const g = Number((cur.stat as { gamesPlayed?: number })?.gamesPlayed ?? 0);
    const bg = Number((best.stat as { gamesPlayed?: number })?.gamesPlayed ?? 0);
    return g >= bg ? cur : best;
  });
}

function asHittingLine(stat: Record<string, unknown> | undefined): MlbSeasonHittingLine | null {
  if (!stat) return null;
  return {
    gamesPlayed: num(stat.gamesPlayed),
    atBats: num(stat.atBats),
    runs: num(stat.runs),
    hits: num(stat.hits),
    doubles: num(stat.doubles),
    triples: num(stat.triples),
    homeRuns: num(stat.homeRuns),
    rbi: num(stat.rbi),
    baseOnBalls: num(stat.baseOnBalls),
    strikeOuts: num(stat.strikeOuts),
    stolenBases: num(stat.stolenBases),
    avg: str(stat.avg),
    obp: str(stat.obp),
    slg: str(stat.slg),
    ops: str(stat.ops),
  };
}

function asPitchingLine(stat: Record<string, unknown> | undefined): MlbSeasonPitchingLine | null {
  if (!stat) return null;
  return {
    gamesPlayed: num(stat.gamesPlayed),
    gamesStarted: num(stat.gamesStarted),
    wins: num(stat.wins),
    losses: num(stat.losses),
    saves: num(stat.saves),
    inningsPitched: str(stat.inningsPitched),
    earnedRuns: num(stat.earnedRuns),
    era: str(stat.era),
    strikeOuts: num(stat.strikeOuts),
    baseOnBalls: num(stat.baseOnBalls),
    whip: str(stat.whip),
  };
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
 * Parse hydrated ``people[0].stats`` for a single MLB season (regular game type preferred).
 */
export function parseMlbPlayerSeasonStats(
  stats: unknown,
  seasonYear: number,
  primaryPositionCode: string | undefined,
): PlayerProfileMlbStats | null {
  if (!Array.isArray(stats)) return null;

  const groups = stats as MlbStatGroup[];
  const isSeason = (g: MlbStatGroup) =>
    g.type?.displayName?.toLowerCase() === "season";

  const hittingGroup = groups.find(
    (g) =>
      isSeason(g) && g.group?.displayName?.toLowerCase() === "hitting",
  );
  const pitchingGroup = groups.find(
    (g) =>
      isSeason(g) && g.group?.displayName?.toLowerCase() === "pitching",
  );

  const hitSplit = pickRegularSeasonSplit(hittingGroup?.splits, seasonYear);
  const pitchSplit = pickRegularSeasonSplit(pitchingGroup?.splits, seasonYear);

  const hitting = hitSplit?.stat
    ? asHittingLine(hitSplit.stat as Record<string, unknown>)
    : null;
  const pitching = pitchSplit?.stat
    ? asPitchingLine(pitchSplit.stat as Record<string, unknown>)
    : null;

  const isPitcherPrimary = primaryPositionCode === "1";

  if (!hitting && !pitching) return null;

  return {
    season: seasonYear,
    isPitcherPrimary,
    hitting,
    pitching,
  };
}
