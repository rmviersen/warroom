/**
 * Batting formulas mirroring `player_batting_seasons` and league JSON keys (`lgOBP`, `lgSLG`, Statcast).
 * League lines and wOBA weights are passed in (e.g. from `league_averages.json` / API).
 */

/** Linear weights for wOBA (same shape as Python `get_woba_weights`). */
export type WobaWeights = {
  uBB: number;
  HBP: number;
  single: number;
  double: number;
  triple: number;
  HR: number;
};

/** Subset of league batting row used by index stats (see SCHEMA / `league_averages.json`). */
export type LeagueBattingContext = {
  lgOBP?: number | null;
  lgSLG?: number | null;
  lgAvgEV?: number | null;
  lgBarrelRate?: number | null;
  lgHardHitRate?: number | null;
};

const STATCAST_MIN_SEASON = 2015;

/** ISO = SLG − AVG */
export function calcISO(slg: number | null, avg: number | null): number | null {
  if (slg === null || avg === null) return null;
  return slg - avg;
}

/** BB% = BB / PA */
export function calcBBPct(bb: number | null, pa: number | null): number | null {
  if (bb === null || pa === null || pa === 0) return null;
  return bb / pa;
}

/** K% = SO / PA */
export function calcKPct(so: number | null, pa: number | null): number | null {
  if (so === null || pa === null || pa === 0) return null;
  return so / pa;
}

/**
 * BABIP = (H − HR) / (AB − SO − HR + SF).
 * Matches league `lgBABIP` construction in pipeline league JSON.
 */
export function calcBABIP(
  h: number | null,
  hr: number | null,
  ab: number | null,
  so: number | null,
  sf: number | null = 0
): number | null {
  if (h === null || hr === null || ab === null || so === null) return null;
  const sfn = sf === null ? 0 : sf;
  const den = ab - so - hr + sfn;
  if (den === 0) return null;
  return (h - hr) / den;
}

/** 1B = H − 2B − 3B − HR */
export function calcSingles(
  h: number | null,
  doubles: number | null,
  triples: number | null,
  hr: number | null
): number | null {
  if (h === null || doubles === null || triples === null || hr === null) return null;
  return h - doubles - triples - hr;
}

/** TB = 1B + 2×2B + 3×3B + 4×HR */
export function calcTB(
  singles: number | null,
  doubles: number | null,
  triples: number | null,
  hr: number | null
): number | null {
  if (singles === null || doubles === null || triples === null || hr === null) return null;
  return singles + 2 * doubles + 3 * triples + 4 * hr;
}

/**
 * wOBA from linear weights and PA (numerator excludes ROE; PA should match warehouse definition).
 */
export function calcWOBA(
  bb: number | null,
  hbp: number | null,
  singles: number | null,
  doubles: number | null,
  triples: number | null,
  hr: number | null,
  pa: number | null,
  weights: WobaWeights
): number | null {
  if (
    bb === null ||
    hbp === null ||
    singles === null ||
    doubles === null ||
    triples === null ||
    hr === null ||
    pa === null ||
    pa === 0
  ) {
    return null;
  }
  const num =
    weights.uBB * bb +
    weights.HBP * hbp +
    weights.single * singles +
    weights.double * doubles +
    weights.triple * triples +
    weights.HR * hr;
  return num / pa;
}

/**
 * OPS+ style index: 100 × (OBP/lgOBP + SLG/lgSLG − 1) / parkFactor.
 * lgOBP / lgSLG from `get_league_averages` / JSON.
 */
export function calcOPSPlus(
  obp: number | null,
  slg: number | null,
  league: LeagueBattingContext,
  parkFactor: number = 1.0
): number | null {
  if (obp === null || slg === null) return null;
  const lo = league.lgOBP;
  const ls = league.lgSLG;
  if (lo == null || ls == null) return null;
  if (lo === 0 || ls === 0 || parkFactor === 0) return null;
  return (100 * (obp / lo + slg / ls - 1)) / parkFactor;
}

/** Basic RC = (H + BB) × TB / (AB + BB) */
export function calcRC(
  h: number | null,
  bb: number | null,
  tb: number | null,
  ab: number | null
): number | null {
  if (h === null || bb === null || tb === null || ab === null) return null;
  const den = ab + bb;
  if (den === 0) return null;
  return ((h + bb) * tb) / den;
}

/**
 * Contact Quality Index: 100 = league average.
 * Weights: 40% avg EV, 40% barrel rate, 20% hard-hit vs league (same scale as Savant / JSON).
 */
export function calcCQI(
  avgEV: number | null,
  barrelRate: number | null,
  hardHitRate: number | null,
  season: number,
  league: LeagueBattingContext
): number | null {
  if (season < STATCAST_MIN_SEASON) return null;
  if (avgEV === null || barrelRate === null || hardHitRate === null) return null;
  const lgEv = league.lgAvgEV;
  const lgBr = league.lgBarrelRate;
  const lgHh = league.lgHardHitRate;
  if (lgEv == null || lgBr == null || lgHh == null) return null;
  if (lgEv === 0 || lgBr === 0 || lgHh === 0) return null;
  return (
    100 *
    (0.4 * (avgEV / lgEv) + 0.4 * (barrelRate / lgBr) + 0.2 * (hardHitRate / lgHh))
  );
}
