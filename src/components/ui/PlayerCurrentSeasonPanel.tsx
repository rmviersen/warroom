"use client";

import PercentileBar from "@/components/ui/PercentileBar";
import type {
  PlayerBattingSeasonRow,
  PlayerFieldingSeasonRow,
  PlayerPitchingSeasonRow,
  PlayerProfileApiResponse,
} from "@/types";

function fmtSlash(n: number | null | undefined, digits: number): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}

function fmtInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return String(Math.round(Number(n)));
}

function fmtOne(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(1);
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
  if (!o) return { raw: null, percentile: null, metricQualifies: false };
  return {
    raw: numOrNull(o.raw),
    percentile: numOrNull(o.percentile),
    metricQualifies: boolOr(o.qualifies, false),
  };
}

function parseBatterMetrics(
  batterPercentiles: Record<string, unknown> | null,
): {
  topQualifies: boolean;
  metrics: Record<string, ParsedMetric>;
} {
  const metricsObj = asRecord(batterPercentiles?.metrics);
  const topQualifies = boolOr(batterPercentiles?.qualifies, false);
  const keys = [
    "avg_exit_velocity",
    "barrel_rate",
    "hard_hit_rate",
    "avg_launch_angle",
    "xwoba",
    "sprint_speed",
    "cqi",
  ] as const;
  const metrics = Object.fromEntries(
    keys.map((k) => [k, parseMetric(metricsObj?.[k])]),
  ) as Record<(typeof keys)[number], ParsedMetric>;
  return { topQualifies, metrics };
}

function parsePitcherOverall(
  pitcherPercentiles: Record<string, unknown> | null,
): {
  topQualifies: boolean;
  metrics: Record<string, ParsedMetric>;
} {
  const overall = asRecord(pitcherPercentiles?.overall);
  const topQualifies = boolOr(pitcherPercentiles?.qualifies, false);
  const keys = [
    "stuff_plus",
    "avg_fastball_velo",
    "max_velo",
    "whiff_rate",
    "chase_rate",
  ] as const;
  const metrics = Object.fromEntries(
    keys.map((k) => [k, parseMetric(overall?.[k])]),
  ) as Record<(typeof keys)[number], ParsedMetric>;
  return { topQualifies, metrics };
}

function StatGrid({
  rows,
}: {
  rows: { label: string; value: string; gold?: boolean }[];
}) {
  return (
    <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-2.5 gap-y-1">
      {rows.map((row) => (
        <div key={row.label} className="min-w-0">
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-[#7a8fa8] truncate">
            {row.label}
          </dt>
          <dd
            className={`font-mono text-xs tabular-nums leading-tight ${
              row.gold ? "font-bold text-[#b8922a]" : "text-[#0f2044]"
            }`}
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function CategorySection({
  title,
  leftLabel = "Standard",
  rightLabel = "Advanced",
  left,
  right,
}: {
  title: string;
  leftLabel?: string;
  rightLabel?: string;
  left: React.ReactNode;
  right: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-[#d0daea] overflow-hidden">
      <div className="px-2 py-1 bg-[#f4f7fb] border-b border-[#d0daea]">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-[#1e3a6b]">
          {title}
        </h3>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 lg:divide-x divide-[#d0daea]">
        <div className="p-2 space-y-1 border-b lg:border-b-0 border-[#d0daea]">
          <p className="text-[9px] font-semibold uppercase tracking-wider text-[#7a8fa8]">
            {leftLabel}
          </p>
          {left}
        </div>
        <div className="p-2 space-y-1 min-w-0 overflow-hidden">
          <p className="text-[9px] font-semibold uppercase tracking-wider text-[#7a8fa8]">
            {rightLabel}
          </p>
          {right}
        </div>
      </div>
    </section>
  );
}

function BatterBarGroup({
  batterPercentiles,
  keys,
}: {
  batterPercentiles: Record<string, unknown> | null;
  keys: Array<
    | "avg_exit_velocity"
    | "barrel_rate"
    | "hard_hit_rate"
    | "avg_launch_angle"
    | "xwoba"
    | "sprint_speed"
    | "cqi"
  >;
}) {
  if (batterPercentiles == null) {
    return (
      <p className="text-xs text-[#7a8fa8] py-1">No Statcast data available.</p>
    );
  }

  const { topQualifies, metrics } = parseBatterMetrics(batterPercentiles);
  const barQualifies = (q: boolean) => topQualifies && q;

  const defs: Record<
    (typeof keys)[number],
    {
      label: string;
      fmt: (m: ParsedMetric) => string;
      warroom?: boolean;
    }
  > = {
    avg_exit_velocity: {
      label: "Exit Velocity",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)} mph`),
    },
    barrel_rate: {
      label: "Barrel Rate",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)}%`),
    },
    hard_hit_rate: {
      label: "Hard Hit %",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)}%`),
    },
    avg_launch_angle: {
      label: "Launch Angle",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)}°`),
    },
    xwoba: {
      label: "xwOBA",
      fmt: (m) => (m.raw == null ? "—" : m.raw.toFixed(3)),
    },
    sprint_speed: {
      label: "Sprint Speed",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)} ft/s`),
    },
    cqi: {
      label: "CQI",
      fmt: (m) => (m.raw == null ? "—" : m.raw.toFixed(1)),
      warroom: true,
    },
  };

  return (
    <div className="space-y-1.5">
      {keys.map((key) => {
        const m = metrics[key];
        const def = defs[key];
        return (
          <PercentileBar
            key={key}
            label={def.label}
            rawDisplay={def.fmt(m)}
            percentile={m.percentile}
            qualifies={barQualifies(m.metricQualifies)}
            isWarroomMetric={def.warroom}
          />
        );
      })}
    </div>
  );
}

function PitcherBarGroup({
  pitcherPercentiles,
}: {
  pitcherPercentiles: Record<string, unknown> | null;
}) {
  if (pitcherPercentiles == null) {
    return (
      <p className="text-xs text-[#7a8fa8] py-1">No Statcast data available.</p>
    );
  }

  const { topQualifies, metrics } = parsePitcherOverall(pitcherPercentiles);
  const barQualifies = (q: boolean) => topQualifies && q;

  const rows: {
    key: keyof typeof metrics;
    label: string;
    fmt: (m: ParsedMetric) => string;
    warroom?: boolean;
  }[] = [
    {
      key: "stuff_plus",
      label: "Stuff+",
      fmt: (m) => (m.raw == null ? "—" : m.raw.toFixed(1)),
      warroom: true,
    },
    {
      key: "avg_fastball_velo",
      label: "FB Velocity",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)} mph`),
    },
    {
      key: "max_velo",
      label: "Max Velocity",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)} mph`),
    },
    {
      key: "whiff_rate",
      label: "Whiff Rate",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)}%`),
    },
    {
      key: "chase_rate",
      label: "Chase Rate",
      fmt: (m) => (m.raw == null ? "—" : `${m.raw.toFixed(1)}%`),
    },
  ];

  return (
    <div className="space-y-1.5">
      {rows.map(({ key, label, fmt, warroom }) => {
        const m = metrics[key];
        return (
          <PercentileBar
            key={key}
            label={label}
            rawDisplay={fmt(m)}
            percentile={m.percentile}
            qualifies={barQualifies(m.metricQualifies)}
            isWarroomMetric={warroom}
          />
        );
      })}
    </div>
  );
}

function pickCurrentBatting(
  rows: PlayerBattingSeasonRow[],
  season: number,
): PlayerBattingSeasonRow | null {
  return rows.find((r) => r.season === season) ?? null;
}

function pickCurrentPitching(
  rows: PlayerPitchingSeasonRow[],
  season: number,
): PlayerPitchingSeasonRow | null {
  return rows.find((r) => r.season === season) ?? null;
}

function pickCurrentFielding(
  rows: PlayerFieldingSeasonRow[],
  season: number,
): PlayerFieldingSeasonRow[] {
  return rows.filter((r) => r.season === season);
}

export default function PlayerCurrentSeasonPanel({
  profile,
  season,
  isPitcherPrimary,
}: {
  profile: PlayerProfileApiResponse;
  season: number;
  isPitcherPrimary: boolean;
}) {
  const batting = pickCurrentBatting(profile.historicalBatting ?? [], season);
  const pitching = pickCurrentPitching(profile.historicalPitching ?? [], season);
  const fielding = pickCurrentFielding(profile.historicalFielding ?? [], season);

  const showBatting = !isPitcherPrimary && batting != null;
  const showBattingTwoWay =
    isPitcherPrimary && batting != null && (batting.pa ?? 0) > 0;
  const showPitching = pitching != null;
  const showFielding = fielding.length > 0;
  const showBaserunning =
    batting != null && (showBatting || showBattingTwoWay || !isPitcherPrimary);

  const battingStatcastKeys = [
    "avg_exit_velocity",
    "barrel_rate",
    "hard_hit_rate",
    "avg_launch_angle",
    "xwoba",
    "cqi",
  ] as const;

  return (
    <div className="rounded-xl border border-[#d0daea] bg-white overflow-hidden">
      <div className="border-b border-[#f0f4f9] bg-[#f4f7fb] px-3 py-2">
        <h2 className="text-sm font-semibold text-[#0f2044]">
          {season} season
        </h2>
        <p className="text-[11px] text-[#7a8fa8]">
          Standard stats on the left · Statcast percentiles on the right.
        </p>
      </div>

      <div className="p-3 space-y-2">
        {(showBatting || showBattingTwoWay) && batting ? (
          <CategorySection
            title="Batting"
            left={
              <StatGrid
                rows={[
                  { label: "G", value: fmtInt(batting.g) },
                  { label: "PA", value: fmtInt(batting.pa) },
                  { label: "AVG", value: fmtSlash(batting.avg, 3) },
                  { label: "OBP", value: fmtSlash(batting.obp, 3) },
                  { label: "SLG", value: fmtSlash(batting.slg, 3) },
                  { label: "OPS", value: fmtSlash(batting.ops, 3) },
                  { label: "HR", value: fmtInt(batting.hr) },
                  { label: "RBI", value: fmtInt(batting.rbi) },
                  { label: "BB", value: fmtInt(batting.bb) },
                  { label: "SO", value: fmtInt(batting.so) },
                  { label: "wRC+", value: fmtInt(batting.wrc_plus) },
                  { label: "bWPR", value: fmtOne(batting.bwpr), gold: true },
                ]}
              />
            }
            right={
              <BatterBarGroup
                batterPercentiles={profile.batterPercentiles}
                keys={[...battingStatcastKeys]}
              />
            }
          />
        ) : null}

        {showBaserunning && batting ? (
          <CategorySection
            title="Baserunning"
            left={
              <StatGrid
                rows={[
                  { label: "SB", value: fmtInt(batting.sb) },
                  { label: "CS", value: fmtInt(batting.cs) },
                  {
                    label: "SB%",
                    value:
                      batting.sb != null &&
                      batting.cs != null &&
                      batting.sb + batting.cs > 0
                        ? `${((batting.sb / (batting.sb + batting.cs)) * 100).toFixed(1)}%`
                        : "—",
                  },
                  { label: "brWPR", value: fmtOne(batting.brwpr), gold: true },
                ]}
              />
            }
            right={
              <BatterBarGroup
                batterPercentiles={profile.batterPercentiles}
                keys={["sprint_speed"]}
              />
            }
          />
        ) : null}

        {showFielding ? (
          <CategorySection
            title="Fielding"
            left={
              <div className="space-y-1.5">
                {batting?.fwpr != null ? (
                  <StatGrid
                    rows={[
                      { label: "fWPR", value: fmtOne(batting.fwpr), gold: true },
                    ]}
                  />
                ) : null}
                {fielding.map((line) => (
                  <div key={`${line.id}-std`} className="space-y-1.5">
                    <p className="text-xs font-semibold text-[#0f2044]">
                      {line.position ?? "—"}
                      {line.team ? (
                        <span className="ml-1.5 font-normal text-[#7a8fa8]">
                          {line.team}
                        </span>
                      ) : null}
                    </p>
                    <StatGrid
                      rows={[
                        { label: "G", value: fmtInt(line.g) },
                        { label: "GS", value: fmtInt(line.gs) },
                        { label: "Inn", value: fmtOne(line.inn) },
                        { label: "PO", value: fmtInt(line.po) },
                        { label: "A", value: fmtInt(line.a) },
                        { label: "E", value: fmtInt(line.e) },
                        {
                          label: "Fld%",
                          value: fmtSlash(line.fld_pct, 3),
                        },
                      ]}
                    />
                  </div>
                ))}
              </div>
            }
            right={
              <div className="space-y-1.5">
                {fielding.map((line) => (
                  <div key={`${line.id}-adv`} className="space-y-1.5">
                    <p className="text-xs font-semibold text-[#0f2044]">
                      {line.position ?? "—"}
                    </p>
                    <StatGrid
                      rows={[
                        { label: "OAA", value: fmtOne(line.oaa) },
                        { label: "DRS", value: fmtInt(line.drs) },
                        { label: "RF/9", value: fmtOne(line.rf_per_9) },
                      ]}
                    />
                  </div>
                ))}
                <p className="text-[10px] text-[#7a8fa8]">
                  Fielding percentile bars are not available yet; OAA and DRS
                  shown as advanced metrics.
                </p>
              </div>
            }
            rightLabel="Advanced · Statcast"
          />
        ) : null}

        {showPitching && pitching ? (
          <CategorySection
            title="Pitching"
            left={
              <StatGrid
                rows={[
                  {
                    label: "W-L",
                    value: `${fmtInt(pitching.w)}-${fmtInt(pitching.l)}`,
                  },
                  { label: "G", value: fmtInt(pitching.g) },
                  { label: "GS", value: fmtInt(pitching.gs) },
                  { label: "IP", value: fmtOne(pitching.ip) },
                  { label: "ERA", value: fmtSlash(pitching.era, 2) },
                  { label: "WHIP", value: fmtSlash(pitching.whip, 3) },
                  { label: "SO", value: fmtInt(pitching.so) },
                  { label: "BB", value: fmtInt(pitching.bb) },
                  { label: "FIP", value: fmtSlash(pitching.fip, 2) },
                  { label: "pWPR", value: fmtOne(pitching.pwpr), gold: true },
                ]}
              />
            }
            right={<PitcherBarGroup pitcherPercentiles={profile.pitcherPercentiles} />}
          />
        ) : null}
      </div>
    </div>
  );
}
