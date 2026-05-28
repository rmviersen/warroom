"use client";

import { useId } from "react";

import type {
  TeamDiamondPosition,
  TeamPositionWprSummary,
  TeamWprDiamondData,
} from "@/types";

/**
 * Anchor points in the same 0–100 coordinate space as the field SVG.
 * Diamond: home (50,90) · 1B (92,52) · 2B (50,14) · 3B (8,52) · mound (50,52).
 */
const POSITION_ANCHORS: Record<TeamDiamondPosition | "P", { x: number; y: number }> = {
  LF: { x: 20, y: 22 },
  CF: { x: 50, y: 9 },
  RF: { x: 80, y: 22 },
  SS: { x: 28, y: 40 },
  "2B": { x: 72, y: 40 },
  "3B": { x: 16, y: 62 },
  "1B": { x: 84, y: 62 },
  C: { x: 50, y: 92 },
  P: { x: 50, y: 52 },
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
    <div className="flex items-center justify-between gap-3 leading-none">
      <span className="text-[11px] font-medium uppercase tracking-wide text-[#7a8fa8]">
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
    <div className="w-[8.5rem] rounded-lg border border-[#d0daea] bg-white px-3 py-2.5 shadow-md sm:w-[9rem]">
      <p className="text-xs font-bold tracking-wide text-[#0f2044]">{position}</p>
      <div className="mt-2.5 space-y-2">
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
    <div className="w-[8.5rem] rounded-lg border-2 border-[#1e3a6b]/25 bg-white px-3 py-3 shadow-md sm:w-[9rem]">
      <p className="text-xs font-bold uppercase tracking-wide text-[#1e3a6b]">
        Pitching
      </p>
      <div className="mt-2.5 flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium uppercase tracking-wide text-[#7a8fa8]">
          pWPR
        </span>
        <span className="font-mono text-base tabular-nums font-bold text-[#b8922a]">
          {formatWpr(pwpr)}
        </span>
      </div>
    </div>
  );
}

function FieldDiamondGraphic({ idPrefix }: { idPrefix: string }) {
  const outfieldGrad = `${idPrefix}-outfield`;
  const infieldGrad = `${idPrefix}-infield`;
  const wallGrad = `${idPrefix}-wall`;

  const home = { x: 50, y: 90 };
  const first = { x: 92, y: 52 };
  const second = { x: 50, y: 14 };
  const third = { x: 8, y: 52 };
  const mound = { x: 50, y: 52 };

  const lfWall = { x: 6, y: 10 };
  const cfWall = { x: 50, y: 3 };
  const rfWall = { x: 94, y: 10 };

  const outfieldPath = `
    M ${home.x} ${home.y}
    L ${third.x} ${third.y}
    L ${lfWall.x} ${lfWall.y}
    Q ${cfWall.x} ${cfWall.y} ${rfWall.x} ${rfWall.y}
    L ${first.x} ${first.y}
    Z
  `;

  const wallPath = `
    M ${lfWall.x} ${lfWall.y}
    Q ${cfWall.x} ${cfWall.y} ${rfWall.x} ${rfWall.y}
  `;

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox="0 0 100 100"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden
    >
      <defs>
        <linearGradient id={outfieldGrad} x1="0.5" y1="0" x2="0.5" y2="1">
          <stop offset="0%" stopColor="#e8f2ea" />
          <stop offset="55%" stopColor="#dce8df" />
          <stop offset="100%" stopColor="#d4e3d8" />
        </linearGradient>
        <linearGradient id={infieldGrad} x1="0.5" y1="0" x2="0.5" y2="1">
          <stop offset="0%" stopColor="#fafcfd" />
          <stop offset="100%" stopColor="#eef3f8" />
        </linearGradient>
        <linearGradient id={wallGrad} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1e3a6b" />
          <stop offset="100%" stopColor="#152a52" />
        </linearGradient>
      </defs>

      {/* Outfield grass */}
      <path d={outfieldPath} fill={`url(#${outfieldGrad})`} />

      {/* Foul lines */}
      <path
        d={`M ${home.x} ${home.y} L ${third.x} ${third.y} L ${lfWall.x} ${lfWall.y}`}
        fill="none"
        stroke="#ffffff"
        strokeWidth="0.65"
        opacity="0.85"
      />
      <path
        d={`M ${home.x} ${home.y} L ${first.x} ${first.y} L ${rfWall.x} ${rfWall.y}`}
        fill="none"
        stroke="#ffffff"
        strokeWidth="0.65"
        opacity="0.85"
      />

      {/* Outfield wall — pad + cap */}
      <path
        d={wallPath}
        fill="none"
        stroke={`url(#${wallGrad})`}
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <path
        d={wallPath}
        fill="none"
        stroke="#2a4470"
        strokeWidth="1.2"
        strokeLinecap="round"
        transform="translate(0, -1.2)"
      />

      {/* Warning track arc */}
      <path
        d={wallPath}
        fill="none"
        stroke="#c8d4ca"
        strokeWidth="0.8"
        strokeDasharray="2 1.5"
        transform="translate(0, 5)"
      />

      {/* Infield diamond */}
      <path
        d={`M ${home.x} ${home.y} L ${first.x} ${first.y} L ${second.x} ${second.y} L ${third.x} ${third.y} Z`}
        fill={`url(#${infieldGrad})`}
        stroke="#b8c8d8"
        strokeWidth="0.9"
        strokeLinejoin="round"
      />

      {/* Base paths */}
      <circle cx={first.x} cy={first.y} r="1.3" fill="#d0daea" />
      <circle cx={second.x} cy={second.y} r="1.3" fill="#d0daea" />
      <circle cx={third.x} cy={third.y} r="1.3" fill="#d0daea" />

      {/* Mound */}
      <circle
        cx={mound.x}
        cy={mound.y}
        r="4.8"
        fill="#eef3f8"
        stroke="#b8c8d8"
        strokeWidth="0.8"
      />

      {/* Home plate */}
      <path
        d={`M ${home.x} ${home.y} L ${home.x - 2.5} ${home.y + 3.5} L ${home.x} ${home.y + 6} L ${home.x + 2.5} ${home.y + 3.5} Z`}
        fill="#ffffff"
        stroke="#b8c8d8"
        strokeWidth="0.8"
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

      <div className="bg-[#f4f7fb]/30 px-3 py-4 sm:px-5 sm:py-5">
        <div className="relative mx-auto aspect-[5/6] w-full max-w-3xl min-h-[28rem] sm:min-h-[32rem] lg:max-w-4xl lg:min-h-[36rem]">
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
