"use client";

import { useId } from "react";

import type {
  TeamDiamondPosition,
  TeamPositionWprSummary,
  TeamWprDiamondData,
} from "@/types";

/** Shared field geometry (viewBox 0 0 100 100). Foul lines are 45° from home. */
const FIELD = {
  home: { x: 50, y: 92 },
  first: { x: 88, y: 54 },
  second: { x: 50, y: 16 },
  third: { x: 12, y: 54 },
  mound: { x: 50, y: 54 },
  /** Left/right foul poles — on 45° lines from home, y = 92 - (50 - x). */
  lfPole: { x: 8, y: 50 },
  rfPole: { x: 92, y: 50 },
  cfWall: { x: 50, y: 12 },
} as const;

const POSITION_ANCHORS: Record<TeamDiamondPosition | "P", { x: number; y: number }> = {
  LF: { x: 22, y: 30 },
  CF: { x: 50, y: 22 },
  RF: { x: 78, y: 30 },
  SS: { x: 26, y: 42 },
  "2B": { x: 74, y: 42 },
  "3B": { x: 18, y: 60 },
  "1B": { x: 82, y: 60 },
  C: { x: 50, y: 94 },
  P: { x: FIELD.mound.x, y: FIELD.mound.y },
};

const FIELD_POSITIONS: TeamDiamondPosition[] = [
  "LF",
  "CF",
  "RF",
  "SS",
  "2B",
  "3B",
  "1B",
  "C",
];

function formatWpr(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(1);
}

function DiamondMarker({
  x,
  y,
  children,
  className = "",
}: {
  x: number;
  y: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`absolute z-10 ${className}`}
      style={{
        left: `${x}%`,
        top: `${y}%`,
        transform: "translate(-50%, -50%)",
      }}
    >
      {children}
    </div>
  );
}

function WprMetricRow({
  label,
  value,
}: {
  label: string;
  value: number | null | undefined;
}) {
  return (
    <div className="flex items-center justify-between gap-4 leading-none">
      <span className="text-xs font-medium uppercase tracking-wide text-[#7a8fa8]">
        {label}
      </span>
      <span className="font-mono text-sm tabular-nums font-bold text-[#b8922a]">
        {formatWpr(value)}
      </span>
    </div>
  );
}

function PositionWprCard({
  position,
  summary,
}: {
  position: TeamDiamondPosition;
  summary: TeamPositionWprSummary | null | undefined;
}) {
  return (
    <div className="w-[9.5rem] rounded-xl border border-[#d0daea] bg-white px-3.5 py-3 shadow-lg sm:w-[10.25rem] lg:w-[10.75rem]">
      <p className="text-sm font-bold tracking-wide text-[#0f2044]">{position}</p>
      <div className="mt-3 space-y-2.5">
        <WprMetricRow label="bWPR" value={summary?.bwpr} />
        <WprMetricRow label="fWPR" value={summary?.fwpr} />
        <WprMetricRow label="brWPR" value={summary?.brwpr} />
      </div>
    </div>
  );
}

function PitchingWprBox({
  pwpr,
}: {
  pwpr: number | null | undefined;
}) {
  return (
    <div className="w-[9.5rem] rounded-xl border-2 border-[#1e3a6b]/20 bg-white px-3.5 py-3.5 shadow-lg sm:w-[10.25rem] lg:w-[10.75rem]">
      <p className="text-sm font-bold uppercase tracking-wide text-[#1e3a6b]">
        Pitching
      </p>
      <div className="mt-3 flex items-center justify-between gap-4">
        <span className="text-xs font-medium uppercase tracking-wide text-[#7a8fa8]">
          pWPR
        </span>
        <span className="font-mono text-lg tabular-nums font-bold text-[#b8922a]">
          {formatWpr(pwpr)}
        </span>
      </div>
    </div>
  );
}

function FieldDiamondGraphic({ idPrefix }: { idPrefix: string }) {
  const outfieldFill = `${idPrefix}-outfield`;
  const { home, first, second, third, mound, lfPole, rfPole, cfWall } = FIELD;

  const outfieldPath = `
    M ${home.x} ${home.y}
    L ${lfPole.x} ${lfPole.y}
    Q ${cfWall.x} ${cfWall.y} ${rfPole.x} ${rfPole.y}
    Z
  `;

  const wallPath = `
    M ${lfPole.x} ${lfPole.y}
    Q ${cfWall.x} ${cfWall.y} ${rfPole.x} ${rfPole.y}
  `;

  const leftFoul = `M ${home.x} ${home.y} L ${lfPole.x} ${lfPole.y}`;
  const rightFoul = `M ${home.x} ${home.y} L ${rfPole.x} ${rfPole.y}`;
  const infieldPath = `
    M ${home.x} ${home.y}
    L ${first.x} ${first.y}
    L ${second.x} ${second.y}
    L ${third.x} ${third.y}
    Z
  `;

  const line = {
    stroke: "#c5d3e3",
    strokeWidth: 0.4,
    fill: "none" as const,
  };

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full opacity-90"
      viewBox="0 0 100 100"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden
    >
      <defs>
        <linearGradient id={outfieldFill} x1="0.5" y1="0" x2="0.5" y2="1">
          <stop offset="0%" stopColor="#eef4f0" />
          <stop offset="100%" stopColor="#f4f7fb" />
        </linearGradient>
      </defs>

      <path d={outfieldPath} fill={`url(#${outfieldFill})`} stroke="none" />

      <path d={leftFoul} {...line} />
      <path d={rightFoul} {...line} />

      <path
        d={wallPath}
        fill="none"
        stroke="#1e3a6b"
        strokeWidth={0.45}
        strokeLinecap="round"
        opacity={0.55}
      />

      <path
        d={infieldPath}
        fill="#ffffff"
        stroke="#c5d3e3"
        strokeWidth={0.4}
        strokeLinejoin="round"
      />

      <circle cx={first.x} cy={first.y} r={0.75} fill="#d0daea" />
      <circle cx={second.x} cy={second.y} r={0.75} fill="#d0daea" />
      <circle cx={third.x} cy={third.y} r={0.75} fill="#d0daea" />

      <circle
        cx={mound.x}
        cy={mound.y}
        r={3.2}
        fill="#f4f7fb"
        stroke="#c5d3e3"
        strokeWidth={0.35}
      />

      <path
        d={`M ${home.x} ${home.y} L ${home.x - 1.8} ${home.y + 2.4} L ${home.x} ${home.y + 4.2} L ${home.x + 1.8} ${home.y + 2.4} Z`}
        fill="#ffffff"
        stroke="#c5d3e3"
        strokeWidth={0.35}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function TeamWprDiamond({
  data,
  season,
}: {
  data?: TeamWprDiamondData | null;
  season: number;
}) {
  const displaySeason = data?.season ?? season;
  const svgId = useId().replace(/:/g, "");

  return (
    <section className="rounded-xl border border-[#d0daea] bg-white">
      <div className="border-b border-[#f0f4f9] bg-[#f4f7fb] px-4 py-2.5">
        <h2 className="text-sm font-semibold text-[#0f2044]">
          Team WPR · {displaySeason}
        </h2>
        <p className="mt-0.5 text-[11px] text-[#7a8fa8]">
          Position rollups by bWPR, fWPR, and brWPR — pitching staff pWPR on
          the mound.
        </p>
      </div>

      <div className="px-2 py-3 sm:px-4 sm:py-4">
        <div className="relative mx-auto aspect-[5/6] w-full max-w-4xl min-h-[30rem] lg:max-w-5xl lg:min-h-[34rem]">
          <FieldDiamondGraphic idPrefix={svgId} />

          {FIELD_POSITIONS.map((pos) => {
            const anchor = POSITION_ANCHORS[pos];
            return (
              <DiamondMarker key={pos} x={anchor.x} y={anchor.y}>
                <PositionWprCard
                  position={pos}
                  summary={data?.positions?.[pos]}
                />
              </DiamondMarker>
            );
          })}

          <DiamondMarker
            x={POSITION_ANCHORS.P.x}
            y={POSITION_ANCHORS.P.y}
            className="z-20"
          >
            <PitchingWprBox pwpr={data?.pitching?.pwpr} />
          </DiamondMarker>
        </div>
      </div>
    </section>
  );
}
