import PercentileBar from "@/components/ui/PercentileBar";

export interface PitcherStatcastSectionProps {
  pitcherPercentiles: Record<string, unknown> | null;
  season: number;
  showOverall?: boolean;
  showArsenal?: boolean;
}

const PITCH_DISPLAY: Record<string, string> = {
  FF: "Four-Seam",
  SI: "Sinker",
  FC: "Cutter",
  FA: "Fastball",
  SL: "Slider",
  ST: "Sweeper",
  CU: "Curveball",
  KC: "Knuckle-Curve",
  CH: "Changeup",
  FS: "Splitter",
  KN: "Knuckleball",
  EP: "Eephus",
};

function pitchDisplayName(code: unknown): string {
  if (code == null) return "—";
  const s = String(code).trim().toUpperCase();
  return PITCH_DISPLAY[s] ?? String(code);
}

function throwsSideLabel(pThrows: unknown): string {
  if (pThrows == null) return "pitchers";
  const ch = String(pThrows).trim().toUpperCase().charAt(0);
  if (ch === "R") return "RHP";
  if (ch === "L") return "LHP";
  return String(pThrows);
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

type ParsedOverallMetric = {
  raw: number | null;
  percentile: number | null;
  metricQualifies: boolean;
};

function parseOverallMetric(m: unknown): ParsedOverallMetric {
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

type ParsedArsenalMetric = {
  raw: number | null;
  percentile: number | null;
};

function parseArsenalMetric(m: unknown): ParsedArsenalMetric {
  const o = asRecord(m);
  if (!o) {
    return { raw: null, percentile: null };
  }
  return {
    raw: numOrNull(o.raw),
    percentile: numOrNull(o.percentile),
  };
}

function unknownArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

type ParsedPitchRow = {
  pitch_type: string;
  p_throws: string;
  pitches: number;
  usage_rate: number | null;
  pitchQualifies: boolean;
  population_size: number;
  avg_velo: ParsedArsenalMetric;
  avg_spin_rate: ParsedArsenalMetric;
  avg_h_movement: ParsedArsenalMetric;
  avg_v_movement: ParsedArsenalMetric;
  whiff_rate: ParsedArsenalMetric;
  chase_rate: ParsedArsenalMetric;
  stuff_plus_pitch: ParsedArsenalMetric;
};

function parsePitchRow(row: unknown): ParsedPitchRow | null {
  const o = asRecord(row);
  if (!o) return null;
  const pitches = numOrNull(o.pitches);
  return {
    pitch_type:
      o.pitch_type == null ? "" : String(o.pitch_type),
    p_throws: o.p_throws == null ? "" : String(o.p_throws),
    pitches:
      pitches != null ? Math.round(pitches) : 0,
    usage_rate: numOrNull(o.usage_rate),
    pitchQualifies: boolOr(o.qualifies, false),
    population_size: numOrNull(o.population_size) ?? 0,
    avg_velo: parseArsenalMetric(o.avg_velo),
    avg_spin_rate: parseArsenalMetric(o.avg_spin_rate),
    avg_h_movement: parseArsenalMetric(o.avg_h_movement),
    avg_v_movement: parseArsenalMetric(o.avg_v_movement),
    whiff_rate: parseArsenalMetric(o.whiff_rate),
    chase_rate: parseArsenalMetric(o.chase_rate),
    stuff_plus_pitch: parseArsenalMetric(o.stuff_plus_pitch),
  };
}

export default function PitcherStatcastSection({
  pitcherPercentiles,
  season,
  showOverall = true,
  showArsenal = true,
}: PitcherStatcastSectionProps) {
  if (pitcherPercentiles == null) {
    return (
      <p className="text-center py-6 text-sm text-[#7a8fa8]">
        No Statcast pitching data for {season}
      </p>
    );
  }

  const overallRaw = asRecord(pitcherPercentiles.overall);
  if (overallRaw == null) {
    return (
      <p className="text-center py-6 text-sm text-[#7a8fa8]">
        No Statcast pitching data for {season}
      </p>
    );
  }

  const topQualifies = boolOr(pitcherPercentiles.qualifies, false);
  const populationSize = numOrNull(pitcherPercentiles.population_size) ?? 0;
  const pitcherIp = numOrNull(pitcherPercentiles.pitcher_ip);
  const floorIp = numOrNull(pitcherPercentiles.floor_ip);

  const mStuff = parseOverallMetric(overallRaw.stuff_plus);
  const mFb = parseOverallMetric(overallRaw.avg_fastball_velo);
  const mMax = parseOverallMetric(overallRaw.max_velo);
  const mWhiff = parseOverallMetric(overallRaw.whiff_rate);
  const mChase = parseOverallMetric(overallRaw.chase_rate);

  function barOverallQual(metricQ: boolean): boolean {
    return topQualifies && metricQ;
  }

  function fmtStuff(x: ParsedOverallMetric): string {
    return x.raw == null ? "—" : x.raw.toFixed(1);
  }
  function fmtMph(x: ParsedOverallMetric): string {
    return x.raw == null ? "—" : `${x.raw.toFixed(1)} mph`;
  }
  function fmtPctPts(x: ParsedOverallMetric): string {
    return x.raw == null ? "—" : `${x.raw.toFixed(1)}%`;
  }

  const arsenalIn = unknownArray(pitcherPercentiles.arsenal);
  const arsenalRows = arsenalIn
    .map(parsePitchRow)
    .filter((r): r is ParsedPitchRow => r != null);

  function fmtPitchMphRow(m: ParsedArsenalMetric): string {
    return m.raw == null ? "—" : `${m.raw.toFixed(1)} mph`;
  }
  function fmtRpmRow(m: ParsedArsenalMetric): string {
    return m.raw == null ? "—" : `${m.raw.toFixed(0)} rpm`;
  }
  function fmtBreakInRow(m: ParsedArsenalMetric): string {
    return m.raw == null ? "—" : `${m.raw.toFixed(1)}"`;
  }
  function fmtPitchPctRow(m: ParsedArsenalMetric): string {
    return m.raw == null ? "—" : `${m.raw.toFixed(1)}%`;
  }
  function fmtPitchStuffRow(m: ParsedArsenalMetric): string {
    return m.raw == null ? "—" : m.raw.toFixed(1);
  }

  return (
    <section>
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
              vs {populationSize} qualified pitchers
            </span>
          </div>
        </div>
        {!topQualifies ? (
          <p className="text-xs text-[#7a8fa8]">
            {pitcherIp == null ? "—" : pitcherIp.toFixed(1)} IP · min{" "}
            {floorIp == null ? "—" : floorIp.toFixed(1)} IP to qualify
          </p>
        ) : null}
      </div>

      {showOverall ? (
        <div className="rounded-xl border border-[#d0daea] bg-white px-4 py-3 space-y-3 mt-3">
          <PercentileBar
            label="Stuff+"
            rawDisplay={fmtStuff(mStuff)}
            percentile={mStuff.percentile}
            qualifies={barOverallQual(mStuff.metricQualifies)}
            isWarroomMetric={true}
          />
          <PercentileBar
            label="FB Velocity"
            rawDisplay={fmtMph(mFb)}
            percentile={mFb.percentile}
            qualifies={barOverallQual(mFb.metricQualifies)}
            isWarroomMetric={false}
          />
          <PercentileBar
            label="Max Velocity"
            rawDisplay={fmtMph(mMax)}
            percentile={mMax.percentile}
            qualifies={barOverallQual(mMax.metricQualifies)}
            isWarroomMetric={false}
          />
          <PercentileBar
            label="Whiff Rate"
            rawDisplay={fmtPctPts(mWhiff)}
            percentile={mWhiff.percentile}
            qualifies={barOverallQual(mWhiff.metricQualifies)}
            isWarroomMetric={false}
          />
          <PercentileBar
            label="Chase Rate"
            rawDisplay={fmtPctPts(mChase)}
            percentile={mChase.percentile}
            qualifies={barOverallQual(mChase.metricQualifies)}
            isWarroomMetric={false}
          />
        </div>
      ) : null}

      {showArsenal && arsenalRows.length > 0 ? (
        <>
          <h4 className="text-sm font-semibold text-[#0f2044] mt-4 mb-2">
            Arsenal
          </h4>
          {arsenalRows.map((pitch, idx) => {
            const name = pitchDisplayName(pitch.pitch_type);
            const throwsWord = throwsSideLabel(pitch.p_throws);

            const usageStr =
              pitch.usage_rate == null
                ? "—"
                : pitch.usage_rate.toFixed(1);

            return (
              <div
                key={`${pitch.pitch_type}-${pitch.p_throws}-${idx}`}
                className="rounded-xl border border-[#d0daea] bg-white px-4 py-3 mb-3"
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-2">
                  <span className="text-sm font-semibold text-[#0f2044]">
                    {name}
                  </span>
                  <span className="inline-flex rounded bg-[#f4f7fb] px-1.5 py-0.5 text-xs text-[#7a8fa8]">
                    {pitch.pitch_type || "—"}
                  </span>
                  <div className="ml-auto flex flex-wrap items-center gap-2">
                    <span className="text-xs text-[#7a8fa8] whitespace-nowrap">
                      {pitch.pitches} pitches · {usageStr}% usage
                    </span>
                    {!pitch.pitchQualifies ? (
                      <span className="inline-flex items-center rounded-full border border-[#d0daea] bg-[#f4f7fb] px-2 py-0.5 text-xs text-[#7a8fa8]">
                        Indicative
                      </span>
                    ) : null}
                  </div>
                </div>
                <p className="mb-2 text-[10px] text-[#7a8fa8]">
                  vs {pitch.population_size} {throwsWord} {name} throwers
                </p>
                <div className="space-y-3">
                  <PercentileBar
                    label="Velocity"
                    rawDisplay={fmtPitchMphRow(pitch.avg_velo)}
                    percentile={pitch.avg_velo.percentile}
                    qualifies={pitch.pitchQualifies}
                    isWarroomMetric={false}
                  />
                  <PercentileBar
                    label="Spin Rate"
                    rawDisplay={fmtRpmRow(pitch.avg_spin_rate)}
                    percentile={pitch.avg_spin_rate.percentile}
                    qualifies={pitch.pitchQualifies}
                    isWarroomMetric={false}
                  />
                  <PercentileBar
                    label="H-Break"
                    rawDisplay={fmtBreakInRow(pitch.avg_h_movement)}
                    percentile={pitch.avg_h_movement.percentile}
                    qualifies={pitch.pitchQualifies}
                    isWarroomMetric={false}
                  />
                  <PercentileBar
                    label="V-Break"
                    rawDisplay={fmtBreakInRow(pitch.avg_v_movement)}
                    percentile={pitch.avg_v_movement.percentile}
                    qualifies={pitch.pitchQualifies}
                    isWarroomMetric={false}
                  />
                  <PercentileBar
                    label="Whiff%"
                    rawDisplay={fmtPitchPctRow(pitch.whiff_rate)}
                    percentile={pitch.whiff_rate.percentile}
                    qualifies={pitch.pitchQualifies}
                    isWarroomMetric={false}
                  />
                  <PercentileBar
                    label="Chase%"
                    rawDisplay={fmtPitchPctRow(pitch.chase_rate)}
                    percentile={pitch.chase_rate.percentile}
                    qualifies={pitch.pitchQualifies}
                    isWarroomMetric={false}
                  />
                  <PercentileBar
                    label="Stuff+"
                    rawDisplay={fmtPitchStuffRow(pitch.stuff_plus_pitch)}
                    percentile={pitch.stuff_plus_pitch.percentile}
                    qualifies={pitch.pitchQualifies}
                    isWarroomMetric={true}
                  />
                </div>
              </div>
            );
          })}
        </>
      ) : null}
    </section>
  );
}
