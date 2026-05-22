import PercentileBar from "@/components/ui/PercentileBar";

export interface BatterStatcastSectionProps {
  batterPercentiles: Record<string, unknown> | null;
  season: number;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (v == null || typeof v !== "object" || Array.isArray(v)) return null;
  return v as Record<string, unknown>;
}

function numOrNull(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function boolOr(v: unknown, fallback: boolean): boolean {
  return typeof v === "boolean" ? v : fallback;
}

type ParsedMetric = {
  raw: number | null;
  percentile: number | null;
  metricQualifies: boolean;
};

function parseMetric(m: unknown): ParsedMetric {
  const o = asRecord(m);
  if (!o) {
    return { raw: null, percentile: null, metricQualifies: false };
  }
  return {
    raw: numOrNull(o.raw),
    percentile: numOrNull(o.percentile),
    metricQualifies: boolOr(o.qualifies, false),
  };
}

export default function BatterStatcastSection({
  batterPercentiles,
  season,
}: BatterStatcastSectionProps) {
  if (batterPercentiles == null) {
    return (
      <p className="text-center py-6 text-sm text-[#7a8fa8]">
        No Statcast batting data for {season}
      </p>
    );
  }

  const metricsObj = asRecord(batterPercentiles.metrics);
  if (metricsObj == null) {
    return (
      <p className="text-center py-6 text-sm text-[#7a8fa8]">
        No Statcast batting data for {season}
      </p>
    );
  }

  const topQualifies = boolOr(batterPercentiles.qualifies, false);
  const populationSize = numOrNull(batterPercentiles.population_size) ?? 0;
  const playerPa = numOrNull(batterPercentiles.player_pa);
  const minPa = numOrNull(batterPercentiles.min_pa_required);

  const mEv = parseMetric(metricsObj.avg_exit_velocity);
  const mBarrel = parseMetric(metricsObj.barrel_rate);
  const mHard = parseMetric(metricsObj.hard_hit_rate);
  const mLa = parseMetric(metricsObj.avg_launch_angle);
  const mXwoba = parseMetric(metricsObj.xwoba);
  const mSprint = parseMetric(metricsObj.sprint_speed);
  const mCqi = parseMetric(metricsObj.cqi);

  function barQualifies(metricQ: boolean): boolean {
    return topQualifies && metricQ;
  }

  function fmtMph(x: ParsedMetric): string {
    return x.raw == null ? "—" : `${x.raw.toFixed(1)} mph`;
  }
  function fmtPctPts(x: ParsedMetric): string {
    return x.raw == null ? "—" : `${x.raw.toFixed(1)}%`;
  }
  function fmtDeg(x: ParsedMetric): string {
    return x.raw == null ? "—" : `${x.raw.toFixed(1)}°`;
  }
  function fmtXwoba(x: ParsedMetric): string {
    return x.raw == null ? "—" : x.raw.toFixed(3);
  }
  function fts(x: ParsedMetric): string {
    return x.raw == null ? "—" : `${x.raw.toFixed(1)} ft/s`;
  }
  function fmtOne(x: ParsedMetric): string {
    return x.raw == null ? "—" : x.raw.toFixed(1);
  }

  return (
    <section className="space-y-3">
      <div className="space-y-1">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <h3 className="text-[#0f2044] font-semibold">
            Statcast · {season}
          </h3>
          <div className="flex flex-wrap items-center gap-2 justify-end">
            {!topQualifies ? (
              <span className="inline-flex items-center rounded-full border border-[#d0daea] bg-[#f4f7fb] px-2 py-0.5 text-xs text-[#7a8fa8]">
                Indicative
              </span>
            ) : null}
            <span className="text-xs text-[#7a8fa8] whitespace-nowrap">
              vs {populationSize} qualified batters
            </span>
          </div>
        </div>
        {!topQualifies ? (
          <p className="text-xs text-[#7a8fa8]">
            {playerPa == null ? "—" : playerPa} PA · min{" "}
            {minPa == null ? "—" : minPa} PA to qualify
          </p>
        ) : null}
      </div>

      <div className="rounded-xl border border-[#d0daea] bg-white px-4 py-3 space-y-3">
        <PercentileBar
          label="Exit Velocity"
          rawDisplay={fmtMph(mEv)}
          percentile={mEv.percentile}
          qualifies={barQualifies(mEv.metricQualifies)}
          isWarroomMetric={false}
        />
        <PercentileBar
          label="Barrel Rate"
          rawDisplay={fmtPctPts(mBarrel)}
          percentile={mBarrel.percentile}
          qualifies={barQualifies(mBarrel.metricQualifies)}
          isWarroomMetric={false}
        />
        <PercentileBar
          label="Hard Hit %"
          rawDisplay={fmtPctPts(mHard)}
          percentile={mHard.percentile}
          qualifies={barQualifies(mHard.metricQualifies)}
          isWarroomMetric={false}
        />
        <PercentileBar
          label="Launch Angle"
          rawDisplay={fmtDeg(mLa)}
          percentile={mLa.percentile}
          qualifies={barQualifies(mLa.metricQualifies)}
          isWarroomMetric={false}
        />
        <PercentileBar
          label="xwOBA"
          rawDisplay={fmtXwoba(mXwoba)}
          percentile={mXwoba.percentile}
          qualifies={barQualifies(mXwoba.metricQualifies)}
          isWarroomMetric={false}
        />
        <PercentileBar
          label="Sprint Speed"
          rawDisplay={fts(mSprint)}
          percentile={mSprint.percentile}
          qualifies={barQualifies(mSprint.metricQualifies)}
          isWarroomMetric={false}
        />
        <PercentileBar
          label="CQI"
          rawDisplay={fmtOne(mCqi)}
          percentile={mCqi.percentile}
          qualifies={barQualifies(mCqi.metricQualifies)}
          isWarroomMetric={true}
        />
      </div>
    </section>
  );
}
