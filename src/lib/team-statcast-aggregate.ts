/** PA-weighted mean, or simple mean when no PA weights exist. */
export function weightedOrSimple<T>(
  list: T[],
  getMetric: (row: T) => number | null,
  getWeight: (row: T) => number | null = (row) =>
    (row as { pa?: number | null }).pa ?? null,
): number | null {
  let numerator = 0;
  let denom = 0;
  const unweighted: number[] = [];

  for (const row of list) {
    const metric = getMetric(row);
    if (metric == null || !Number.isFinite(metric)) continue;
    const weight = getWeight(row);
    if (weight != null && weight > 0 && Number.isFinite(weight)) {
      numerator += metric * weight;
      denom += weight;
    } else {
      unweighted.push(metric);
    }
  }

  if (denom > 0) return numerator / denom;
  if (unweighted.length > 0) {
    return unweighted.reduce((a, b) => a + b, 0) / unweighted.length;
  }
  return null;
}

export function maxOfMetrics<T>(
  list: T[],
  getMetric: (row: T) => number | null,
): number | null {
  const vals = list
    .map(getMetric)
    .filter((v): v is number => v != null && Number.isFinite(v));
  if (vals.length === 0) return null;
  return Math.max(...vals);
}

/** Convert baseball IP (e.g. 145.1) to total outs recorded. */
export function ipToOuts(value: unknown): number {
  if (value == null) return 0;
  const s = String(value).trim();
  if (!s) return 0;
  if (!s.includes(".")) {
    const whole = Number(s);
    return Number.isFinite(whole) ? Math.trunc(whole) * 3 : 0;
  }
  const dot = s.indexOf(".");
  const wholeS = s.slice(0, dot);
  const fracDigit = s[dot + 1] ?? "0";
  const whole = wholeS ? Number(wholeS) : 0;
  const third = Number(fracDigit);
  const thirds = third === 1 || third === 2 ? third : 0;
  return (Number.isFinite(whole) ? Math.trunc(whole) : 0) * 3 + thirds;
}

/** Rough batters faced for team pitching rate stats. */
export function estimateBattersFaced(
  ip: number | null,
  hits: number | null,
  walks: number | null,
  strikeouts: number | null,
): number | null {
  const outs = ipToOuts(ip);
  const h = hits ?? 0;
  const bb = walks ?? 0;
  const so = strikeouts ?? 0;
  const bf = outs + h + bb;
  if (bf <= 0 && so <= 0) return null;
  return Math.max(bf, so + bb);
}
