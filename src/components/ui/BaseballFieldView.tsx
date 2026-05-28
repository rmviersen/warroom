"use client";

import Link from "next/link";
import { Fragment, useMemo, useState } from "react";

import type { TeamPositionWprPlayerRow, TeamPositionWprRow } from "@/types";

interface BaseballFieldViewProps {
  positions: TeamPositionWprRow[];
  playersByPosition: Map<string, TeamPositionWprPlayerRow[]>;
  season: number;
  loadError?: boolean;
}

const VIEW_W = 600;
const VIEW_H = 560;

const FOUL_POLES = {
  left: { x: 18, y: 218 },
  right: { x: 582, y: 218 },
} as const;

const FIELD = {
  home: { x: 300, y: 500 },
  /** On the right foul line (home → RF pole). */
  first: { x: 435, y: 365 },
  second: { x: 300, y: 236 },
  /** On the left foul line (home → LF pole). */
  third: { x: 165, y: 365 },
  mound: { x: 300, y: 358 },
} as const;

const CARD_W = 130;
const CARD_H = 80;

const POSITION_ANCHORS: Record<string, { x: number; y: number }> = {
  P: { x: 300, y: 358 },
  C: { x: 300, y: 492 },
  "1B": { x: 462, y: 378 },
  "2B": { x: 378, y: 288 },
  "3B": { x: 138, y: 378 },
  SS: { x: 222, y: 288 },
  LF: { x: 118, y: 200 },
  CF: { x: 300, y: 130 },
  RF: { x: 482, y: 200 },
};

const DEFAULT_POSITIONS = [
  "P",
  "C",
  "1B",
  "2B",
  "3B",
  "SS",
  "LF",
  "CF",
  "RF",
] as const;

/** Light platform palette for the field graphic */
const FIELD_COLORS = {
  canvas: "#f4f7fb",
  fair: "#eef2f8",
  outfieldBand: "#e4eaf2",
  infieldDirt: "#ebe7e2",
  infieldGrass: "#e8f0ea",
  line: "#7a8fa8",
  lineStrong: "#5a7090",
  outline: "#1e3a6b",
  base: "#ffffff",
  baseStroke: "#7a8fa8",
  mound: "#ebe7e2",
  moundStroke: "#7a8fa8",
  rubber: "#5a7090",
  fence: "#5a7090",
} as const;

function fmtWpr(v: number | null, digits = 1): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(digits);
}

function fmtInn(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(1);
}

function fmtShare(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${Math.round(Number(v) * 100)}%`;
}

function rankColorClass(rank: number): string {
  if (rank <= 5) return "text-[#b8922a] font-semibold";
  if (rank <= 10) return "text-[#1e3a6b] font-semibold";
  if (rank <= 20) return "text-[#7a8fa8]";
  return "text-[#a0b0c0]";
}

function RankBadge({
  rank,
  teamCount,
  variant = "inline",
}: {
  rank: number | null | undefined;
  teamCount: number | null | undefined;
  variant?: "inline" | "secondary" | "card";
}) {
  if (rank == null || Number.isNaN(Number(rank))) return null;
  if (teamCount == null || Number.isNaN(Number(teamCount))) return null;

  const colorClass = rankColorClass(rank);
  const showDenominator = teamCount < 25;

  const label = (
    <>
      #{rank}
      {showDenominator ? (
        <span className="font-normal text-[#a0b0c0]"> / {teamCount}</span>
      ) : null}
    </>
  );

  if (variant === "secondary") {
    return (
      <span className={`text-[9px] tabular-nums leading-none ${colorClass}`}>
        {label}
      </span>
    );
  }

  if (variant === "card") {
    return (
      <span
        className={`absolute bottom-1.5 right-2 text-[8px] tabular-nums leading-none ${colorClass}`}
      >
        {label}
      </span>
    );
  }

  return (
    <span className={`ml-1.5 text-[10px] tabular-nums ${colorClass}`}>
      {label}
    </span>
  );
}

function MetricWithRank({
  value,
  rank,
  teamCount,
  headline = false,
}: {
  value: string;
  rank: number | null | undefined;
  teamCount: number | null | undefined;
  headline?: boolean;
}) {
  if (headline) {
    return (
      <div className="flex items-baseline justify-end">
        <span className="font-mono tabular-nums font-semibold text-[#b8922a]">
          {value}
        </span>
        <RankBadge rank={rank} teamCount={teamCount} variant="inline" />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className="font-mono tabular-nums text-[#7a8fa8]">{value}</span>
      <RankBadge rank={rank} teamCount={teamCount} variant="secondary" />
    </div>
  );
}

function FieldGraphic() {
  const { home, first, second, third } = FIELD;
  const { left: lfPole, right: rfPole } = FOUL_POLES;

  const baseline = (a: { x: number; y: number }, b: { x: number; y: number }) =>
    `M ${a.x} ${a.y} L ${b.x} ${b.y}`;

  const base = (x: number, y: number) =>
    `M ${x} ${y - 8} L ${x + 8} ${y} L ${x} ${y + 8} L ${x - 8} ${y} Z`;

  const fairTerritoryPath = `M ${home.x} ${home.y} L ${lfPole.x} ${lfPole.y} Q 300 18 ${rfPole.x} ${rfPole.y} Z`;

  const infieldDirtPath = `M ${home.x} ${home.y} L ${first.x + 24} ${first.y - 7} L ${second.x} ${second.y - 18} L ${third.x - 24} ${third.y - 7} Z`;

  const infieldGrassPath = `M ${home.x} ${home.y - 6} L ${first.x - 3} ${first.y + 9} L ${second.x} ${second.y + 4} L ${third.x + 3} ${third.y + 9} Z`;

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="xMidYMid meet"
      className="absolute inset-0 h-full w-full"
      aria-hidden
    >
      {/* Layer 1 — Canvas background */}
      <rect
        x={0}
        y={0}
        width={VIEW_W}
        height={VIEW_H}
        fill={FIELD_COLORS.canvas}
      />

      {/* Layer 2 — Fair territory */}
      <path
        d={fairTerritoryPath}
        fill={FIELD_COLORS.fair}
        stroke={FIELD_COLORS.outline}
        strokeWidth={1.25}
        strokeLinejoin="round"
      />

      {/* Layer 3 — Outfield depth band */}
      <path
        d={`M ${lfPole.x} ${lfPole.y} Q 300 18 ${rfPole.x} ${rfPole.y} L 556 240 Q 300 42 44 240 Z`}
        fill={FIELD_COLORS.outfieldBand}
      />

      {/* Layer 4 — Infield diamond */}
      <path d={infieldDirtPath} fill={FIELD_COLORS.infieldDirt} />

      {/* Layer 5 — Infield grass */}
      <path d={infieldGrassPath} fill={FIELD_COLORS.infieldGrass} />

      {/* Layer 6 — Foul lines (home through 1B/3B to the foul poles) */}
      <line
        x1={home.x}
        y1={home.y}
        x2={lfPole.x}
        y2={lfPole.y}
        stroke={FIELD_COLORS.lineStrong}
        strokeWidth={1.75}
      />
      <line
        x1={home.x}
        y1={home.y}
        x2={rfPole.x}
        y2={rfPole.y}
        stroke={FIELD_COLORS.lineStrong}
        strokeWidth={1.75}
      />

      {/* Layer 7 — Infield baselines (1B↔2B↔3B↔home; foul lines cover home↔1B/3B) */}
      <path
        d={baseline(first, second)}
        fill="none"
        stroke={FIELD_COLORS.line}
        strokeWidth={1.5}
      />
      <path
        d={baseline(second, third)}
        fill="none"
        stroke={FIELD_COLORS.line}
        strokeWidth={1.5}
      />
      <path
        d={baseline(third, home)}
        fill="none"
        stroke={FIELD_COLORS.line}
        strokeWidth={1.5}
      />

      {/* Layer 8 — Bases */}
      <path
        d={base(first.x, first.y)}
        fill={FIELD_COLORS.base}
        stroke={FIELD_COLORS.baseStroke}
        strokeWidth={1.25}
      />
      <path
        d={base(second.x, second.y)}
        fill={FIELD_COLORS.base}
        stroke={FIELD_COLORS.baseStroke}
        strokeWidth={1.25}
      />
      <path
        d={base(third.x, third.y)}
        fill={FIELD_COLORS.base}
        stroke={FIELD_COLORS.baseStroke}
        strokeWidth={1.25}
      />

      {/* Layer 9 — Home plate */}
      <path
        d="M 300 492 L 308 500 L 308 508 L 292 508 L 292 500 Z"
        fill={FIELD_COLORS.base}
        stroke={FIELD_COLORS.baseStroke}
        strokeWidth={1.25}
      />

      {/* Layer 10 — Pitcher's mound */}
      <circle
        cx={FIELD.mound.x}
        cy={FIELD.mound.y}
        r={18}
        fill={FIELD_COLORS.mound}
        stroke={FIELD_COLORS.moundStroke}
        strokeWidth={1.25}
      />
      <rect
        x={294}
        y={355}
        width={12}
        height={4}
        rx={1}
        fill={FIELD_COLORS.rubber}
        opacity={0.55}
      />

      {/* Layer 11 — Outfield fence arc */}
      <path
        d={`M ${lfPole.x} ${lfPole.y} Q 300 18 ${rfPole.x} ${rfPole.y}`}
        fill="none"
        stroke={FIELD_COLORS.fence}
        strokeWidth={1.5}
      />
    </svg>
  );
}

function CardDivider() {
  return <div className="my-1.5 h-px shrink-0 bg-[#d0daea]" />;
}

function PositionCard({
  position,
  row,
  anchor,
}: {
  position: string;
  row: TeamPositionWprRow | null;
  anchor: { x: number; y: number };
}) {
  const empty = row == null;
  const isPitcher = position === "P";

  let body;

  if (empty) {
    body = (
      <>
        <div className="flex items-baseline justify-between gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wide text-[#7a8fa8]">
            {position}
          </span>
          <span className="font-mono text-[13px] tabular-nums font-bold leading-none text-[#7a8fa8]">
            —
          </span>
        </div>
        <p className="mt-1.5 text-[9px] text-[#7a8fa8]">no data</p>
      </>
    );
  } else if (isPitcher) {
    body = (
      <>
        <div className="flex items-baseline justify-between gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wide text-[#1e3a6b]">
            P
          </span>
          <span className="font-mono text-[13px] tabular-nums font-bold leading-none text-[#b8922a]">
            {row.pwpr != null ? `${fmtWpr(row.pwpr)} pWPR` : "—"}
          </span>
        </div>
        <CardDivider />
        <p className="text-[9px] text-[#7a8fa8]">
          · {row.player_count}{" "}
          {row.player_count === 1 ? "pitcher" : "pitchers"}
        </p>
      </>
    );
  } else {
    body = (
      <>
        <div className="flex items-baseline justify-between gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wide text-[#1e3a6b]">
            {position}
          </span>
          <span className="font-mono text-[13px] tabular-nums font-bold leading-none text-[#b8922a]">
            {row.wpr != null ? `${fmtWpr(row.wpr)} WPR` : "—"}
          </span>
        </div>
        <CardDivider />
        <p className="font-mono text-[9px] tabular-nums leading-tight text-[#7a8fa8]">
          b {fmtWpr(row.bwpr)}
          <span className="text-[#d0daea]"> · </span>
          f {fmtWpr(row.fwpr)}
          <span className="text-[#d0daea]"> · </span>
          br {fmtWpr(row.brwpr)}
        </p>
        <p className="mt-0.5 text-[9px] text-[#7a8fa8]">
          · {row.player_count} {row.player_count === 1 ? "player" : "players"}
        </p>
      </>
    );
  }

  return (
    <div
      className="absolute"
      style={{
        left: `${(anchor.x / VIEW_W) * 100}%`,
        top: `${(anchor.y / VIEW_H) * 100}%`,
        width: CARD_W,
        height: CARD_H,
        transform: "translate(-50%, -50%)",
      }}
    >
      <div
        className={`relative flex h-full w-full flex-col rounded-[6px] border px-2.5 py-2 text-left shadow-sm ${
          empty
            ? "border-[#d0daea] bg-[#f4f7fb]/95"
            : "border-[#d0daea] bg-white/95"
        }`}
      >
        {body}
        {!empty ? (
          <RankBadge
            rank={isPitcher ? row.pwpr_rank : row.wpr_rank}
            teamCount={row.team_count}
            variant="card"
          />
        ) : null}
      </div>
    </div>
  );
}

function PositionWprTable({
  positions,
  playersByPosition,
  loadError = false,
}: {
  positions: TeamPositionWprRow[];
  playersByPosition: Map<string, TeamPositionWprPlayerRow[]>;
  loadError?: boolean;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const positionsByCode = useMemo(() => {
    const map = new Map<string, TeamPositionWprRow>();
    for (const row of positions) {
      map.set(row.position, row);
    }
    return map;
  }, [positions]);

  const toggleExpanded = (pos: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(pos)) {
        next.delete(pos);
      } else {
        next.add(pos);
      }
      return next;
    });
  };

  return (
    <div className="flex h-full min-h-0 flex-col rounded-lg border border-[#d0daea] bg-white">
      <div className="border-b border-[#d0daea] bg-[#f4f7fb] px-3 py-2.5">
        <h3 className="text-xs font-bold uppercase tracking-widest text-[#1e3a6b]">
          Position breakdown
        </h3>
        {loadError ? (
          <p className="mt-1 text-[11px] text-red-600">
            Could not load position WPR data.
          </p>
        ) : positions.length === 0 ? (
          <p className="mt-1 text-[11px] text-[#7a8fa8]">
            No position WPR data for this team-season yet.
          </p>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-x-auto">
        <table className="w-full min-w-[280px] text-sm">
          <thead>
            <tr className="border-b border-[#f0f4f9] bg-[#f4f7fb] text-left text-[10px] uppercase tracking-wide text-[#7a8fa8]">
              <th className="px-3 py-2 font-semibold">Pos</th>
              <th className="px-2 py-2 font-semibold text-right">WPR</th>
              <th className="hidden px-2 py-2 font-semibold text-right sm:table-cell">
                b
              </th>
              <th className="hidden px-2 py-2 font-semibold text-right sm:table-cell">
                f
              </th>
              <th className="hidden px-2 py-2 font-semibold text-right md:table-cell">
                br
              </th>
              <th className="px-3 py-2 font-semibold text-right">Players</th>
            </tr>
          </thead>
          <tbody>
            {DEFAULT_POSITIONS.map((pos) => {
              const row = positionsByCode.get(pos) ?? null;
              const isPitcher = pos === "P";
              const empty = row == null;
              const players = playersByPosition?.get(pos) ?? [];
              const canExpand = !empty && players.length > 0;
              const isExpanded = expanded.has(pos);

              return (
                <Fragment key={pos}>
                  <tr className="border-b border-[#f0f4f9] last:border-b-0">
                    <td className="px-3 py-2 font-semibold text-[#1e3a6b]">
                      <div className="flex items-center gap-1.5">
                        {canExpand ? (
                          <button
                            type="button"
                            onClick={() => toggleExpanded(pos)}
                            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] text-[#7a8fa8] transition-colors hover:bg-[#f4f7fb] hover:text-[#1e3a6b]"
                            aria-expanded={isExpanded}
                            aria-label={`${isExpanded ? "Collapse" : "Expand"} ${pos} player breakdown`}
                          >
                            {isExpanded ? "▼" : "▶"}
                          </button>
                        ) : (
                          <span className="inline-block w-5 shrink-0" aria-hidden />
                        )}
                        <span>{pos}</span>
                      </div>
                    </td>
                    <td className="px-2 py-2 text-right">
                      {empty ? (
                        "—"
                      ) : (
                        <MetricWithRank
                          value={
                            isPitcher
                              ? row.pwpr != null
                                ? fmtWpr(row.pwpr)
                                : "—"
                              : row.wpr != null
                                ? fmtWpr(row.wpr)
                                : "—"
                          }
                          rank={isPitcher ? row.pwpr_rank : row.wpr_rank}
                          teamCount={row.team_count}
                          headline
                        />
                      )}
                    </td>
                    <td className="hidden px-2 py-2 text-right sm:table-cell">
                      {empty || isPitcher ? (
                        "—"
                      ) : (
                        <MetricWithRank
                          value={fmtWpr(row.bwpr)}
                          rank={row.bwpr_rank}
                          teamCount={row.team_count}
                        />
                      )}
                    </td>
                    <td className="hidden px-2 py-2 text-right sm:table-cell">
                      {empty || isPitcher ? (
                        "—"
                      ) : (
                        <MetricWithRank
                          value={fmtWpr(row.fwpr)}
                          rank={row.fwpr_rank}
                          teamCount={row.team_count}
                        />
                      )}
                    </td>
                    <td className="hidden px-2 py-2 text-right md:table-cell">
                      {empty || isPitcher ? (
                        "—"
                      ) : (
                        <MetricWithRank
                          value={fmtWpr(row.brwpr)}
                          rank={row.brwpr_rank}
                          teamCount={row.team_count}
                        />
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-[#7a8fa8]">
                      {empty ? "—" : row.player_count}
                    </td>
                  </tr>
                  {isExpanded && canExpand ? (
                    <tr>
                      <td colSpan={6} className="bg-[#f4f7fb] p-0">
                        <div className="border-l-2 border-[#b8922a] pl-8">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left text-[10px] uppercase tracking-wide text-[#7a8fa8]">
                                <th className="py-2 pr-3 font-semibold">Player</th>
                                <th className="px-2 py-2 font-semibold text-right">
                                  {isPitcher ? "IP" : "Inn"}
                                </th>
                                <th className="px-2 py-2 font-semibold text-right">
                                  {isPitcher ? "IP%" : "Share"}
                                </th>
                                {!isPitcher ? (
                                  <>
                                    <th className="hidden px-2 py-2 font-semibold text-right sm:table-cell">
                                      bWPR
                                    </th>
                                    <th className="hidden px-2 py-2 font-semibold text-right sm:table-cell">
                                      fWPR
                                    </th>
                                    <th className="hidden px-2 py-2 font-semibold text-right md:table-cell">
                                      brWPR
                                    </th>
                                  </>
                                ) : null}
                                <th className="px-3 py-2 font-semibold text-right">
                                  {isPitcher ? "pWPR" : "WPR"}
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {players.map((player, index) => (
                                <tr
                                  key={player.player_id}
                                  className={`border-t border-[#f0f4f9] ${
                                    index === players.length - 1
                                      ? "border-b border-[#d0daea]"
                                      : ""
                                  }`}
                                >
                                  <td className="py-2 pr-3">
                                    <Link
                                      href={`/players/${player.player_id}`}
                                      className="font-medium text-[#1e3a6b] hover:underline"
                                    >
                                      {player.player_name ?? `#${player.player_id}`}
                                    </Link>
                                  </td>
                                  <td className="px-2 py-2 text-right font-mono tabular-nums text-[#7a8fa8]">
                                    {fmtInn(player.inn)}
                                  </td>
                                  <td className="px-2 py-2 text-right font-mono tabular-nums text-[#7a8fa8]">
                                    {fmtShare(player.inn_share)}
                                  </td>
                                  {!isPitcher ? (
                                    <>
                                      <td className="hidden px-2 py-2 text-right font-mono tabular-nums text-[#7a8fa8] sm:table-cell">
                                        {fmtWpr(player.bwpr_attr)}
                                      </td>
                                      <td className="hidden px-2 py-2 text-right font-mono tabular-nums text-[#7a8fa8] sm:table-cell">
                                        {fmtWpr(player.fwpr_attr)}
                                      </td>
                                      <td className="hidden px-2 py-2 text-right font-mono tabular-nums text-[#7a8fa8] md:table-cell">
                                        {fmtWpr(player.brwpr_attr)}
                                      </td>
                                    </>
                                  ) : null}
                                  <td className="px-3 py-2 text-right font-mono tabular-nums font-semibold text-[#b8922a]">
                                    {isPitcher
                                      ? fmtWpr(player.pwpr_attr)
                                      : fmtWpr(player.wpr_attr)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function BaseballFieldView({
  positions,
  playersByPosition,
  season,
  loadError = false,
}: BaseballFieldViewProps) {
  const positionsByCode = useMemo(() => {
    const map = new Map<string, TeamPositionWprRow>();
    for (const row of positions) {
      map.set(row.position, row);
    }
    return map;
  }, [positions]);

  return (
    <section className="overflow-hidden rounded-xl border border-[#d0daea] bg-white">
      <div className="border-b border-[#d0daea] bg-[#f4f7fb] px-4 py-3">
        <h2 className="text-sm font-semibold text-[#0f2044]">
          WPR by position · {season}
        </h2>
        <p className="mt-0.5 text-[11px] text-[#7a8fa8]">
          Innings-weighted team WPR allocated to each defensive position.
        </p>
      </div>

      <div className="grid grid-cols-1 items-start gap-4 p-3 sm:p-4 lg:grid-cols-2 lg:gap-6">
        <div
          className="relative w-full overflow-hidden rounded-lg border border-[#d0daea] bg-[#f4f7fb]"
          style={{ aspectRatio: `${VIEW_W} / ${VIEW_H}` }}
        >
          <FieldGraphic />

          {DEFAULT_POSITIONS.map((pos) => {
            const anchor = POSITION_ANCHORS[pos];
            if (!anchor) return null;
            return (
              <PositionCard
                key={pos}
                position={pos}
                row={positionsByCode.get(pos) ?? null}
                anchor={anchor}
              />
            );
          })}
        </div>

        <PositionWprTable
          positions={positions}
          playersByPosition={playersByPosition}
          loadError={loadError}
        />
      </div>
    </section>
  );
}
