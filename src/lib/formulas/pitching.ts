/**
 * Pitching formulas aligned with `player_pitching_seasons` and league JSON (`lgERA`, `FIP_constant`, pitch Statcast).
 * League values are caller-supplied (e.g. from `league_averages.json`).
 */

/** Subset of league row for ERA+ and Stuff+ denominators. */
export type LeaguePitchingContext = {
  lgERA?: number | null;
  lgAvgVelo?: number | null;
  lgAvgSpinRate?: number | null;
};

const STATCAST_MIN_SEASON = 2015;
const LG_HORIZONTAL_MOVEMENT_IN = 7.5;
const LG_VERTICAL_MOVEMENT_IN = 8.0;

/** K/9 = (SO / IP) × 9 */
export function calcKPer9(so: number | null, ip: number | null): number | null {
  if (so === null || ip === null || ip === 0) return null;
  return (so / ip) * 9;
}

/** BB/9 = (BB / IP) × 9 */
export function calcBBPer9(bb: number | null, ip: number | null): number | null {
  if (bb === null || ip === null || ip === 0) return null;
  return (bb / ip) * 9;
}

/** HR/9 = (HR / IP) × 9 */
export function calcHRPer9(hr: number | null, ip: number | null): number | null {
  if (hr === null || ip === null || ip === 0) return null;
  return (hr / ip) * 9;
}

/** K/BB = SO / BB */
export function calcKBB(so: number | null, bb: number | null): number | null {
  if (so === null || bb === null || bb === 0) return null;
  return so / bb;
}

/** WHIP = (H + BB) / IP */
export function calcWHIP(h: number | null, bb: number | null, ip: number | null): number | null {
  if (h === null || bb === null || ip === null || ip === 0) return null;
  return (h + bb) / ip;
}

/**
 * FIP = (13×HR + 3×BB − 2×SO) / IP + FIP_constant.
 * Constant is season-specific (`FIP_constant` in league JSON).
 */
export function calcFIP(
  hr: number | null,
  bb: number | null,
  so: number | null,
  ip: number | null,
  fipConstant: number | null
): number | null {
  if (hr === null || bb === null || so === null || ip === null || ip === 0) return null;
  if (fipConstant === null) return null;
  const core = (13 * hr + 3 * bb - 2 * so) / ip;
  return core + fipConstant;
}

/**
 * ERA+ = 100 × (lgERA / ERA) × parkFactor (WARroom convention; lgERA from league JSON).
 */
export function calcERAPlus(
  era: number | null,
  league: LeaguePitchingContext,
  parkFactor: number = 1.0
): number | null {
  if (era === null || era === 0) return null;
  const lg = league.lgERA;
  if (lg == null) return null;
  return 100 * (lg / era) * parkFactor;
}

/**
 * LOB% = (H + BB − R) / (H + BB − 1.4×HR). Classic strand rate denominator tweak.
 */
export function calcLOBPct(
  h: number | null,
  bb: number | null,
  hr: number | null,
  r: number | null
): number | null {
  if (h === null || bb === null || hr === null || r === null) return null;
  const den = h + bb - 1.4 * hr;
  if (den === 0) return null;
  return (h + bb - r) / den;
}

/**
 * Stuff+ style index: 100 = league average velo and spin; movement vs fixed 7.5″ / 8.0″ league baselines.
 * Weights: velo 40%, spin 30%, horizontal movement 15%, vertical 15%.
 */
export function calcStuffPlus(
  velo: number | null,
  spinRate: number | null,
  hMovement: number | null,
  vMovement: number | null,
  season: number,
  league: LeaguePitchingContext
): number | null {
  if (season < STATCAST_MIN_SEASON) return null;
  if (velo === null || spinRate === null || hMovement === null || vMovement === null) return null;
  const lgV = league.lgAvgVelo;
  const lgS = league.lgAvgSpinRate;
  if (lgV == null || lgS == null) return null;
  if (lgV === 0 || lgS === 0) return null;
  const rV = velo / lgV;
  const rS = spinRate / lgS;
  const rH = Math.abs(hMovement) / LG_HORIZONTAL_MOVEMENT_IN;
  const rZ = Math.abs(vMovement) / LG_VERTICAL_MOVEMENT_IN;
  return 100 * (0.4 * rV + 0.3 * rS + 0.15 * rH + 0.15 * rZ);
}
