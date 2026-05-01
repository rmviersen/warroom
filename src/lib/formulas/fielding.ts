/**
 * Fielding rates from putouts, assists, errors, innings, and games (SCHEMA defensive counters).
 */

/** Fielding percentage = (PO + A) / (PO + A + E) */
export function calcFLDPct(po: number | null, a: number | null, e: number | null): number | null {
  if (po === null || a === null || e === null) return null;
  const den = po + a + e;
  if (den === 0) return null;
  return (po + a) / den;
}

/** Range factor per 9 innings = (PO + A) / (INN / 9) */
export function calcRFPer9(po: number | null, a: number | null, inn: number | null): number | null {
  if (po === null || a === null || inn === null || inn === 0) return null;
  return (po + a) / (inn / 9);
}

/** Range factor per game = (PO + A) / G */
export function calcRFPerG(po: number | null, a: number | null, g: number | null): number | null {
  if (po === null || a === null || g === null || g === 0) return null;
  return (po + a) / g;
}
