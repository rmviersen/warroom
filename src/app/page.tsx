"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { getTeamLogoUrl } from "@/lib/mlb-images";
import {
  isDivisionLeader,
  isWildCardPlayoffPosition,
  playoffFirstCellClass,
  playoffRowClass,
} from "@/lib/playoff-teams";
import type { StandingRow } from "@/types";

const AL_LEAGUE_ID = 103;
const NL_LEAGUE_ID = 104;

type ScheduleLinescoreOffense = {
  first?: unknown;
  second?: unknown;
  third?: unknown;
};

type ScheduleLinescore = {
  currentInning?: number;
  currentInningOrdinal?: string;
  inningState?: string;
  inningHalf?: string;
  isTopInning?: boolean;
  outs?: number;
  offense?: ScheduleLinescoreOffense;
};

type ScheduleProbablePitcher = {
  id?: number;
  fullName?: string;
  seasonPitching?: {
    wins: number;
    losses: number;
    era: string | null;
  };
};

type ScheduleTeamSide = {
  team?: {
    id?: number;
    name?: string;
    abbreviation?: string;
    fileCode?: string;
  };
  probablePitcher?: ScheduleProbablePitcher;
  score?: number;
  leagueRecord?: { wins?: number; losses?: number; pct?: string };
};

type ScheduleGame = {
  gamePk?: number;
  gameDate?: string;
  status?: { detailedState?: string; abstractGameState?: string };
  linescore?: ScheduleLinescore;
  teams?: {
    away?: ScheduleTeamSide;
    home?: ScheduleTeamSide;
  };
};

type ScheduleDate = { games?: ScheduleGame[] };

type RawStandingDivision = {
  league?: { id?: number; name?: string };
  /** Populated when standings request uses ``hydrate=...,division`` (e.g. ``nameShort``: ``AL East``). */
  division?: { id?: number; name?: string; nameShort?: string };
  teamRecords?: Array<{
    team?: { id?: number; name?: string };
    leagueRecord?: { wins?: number; losses?: number; pct?: string };
    gamesBack?: string;
  }>;
};

type WildCardRow = {
  teamId: number;
  teamName: string;
  wins: number;
  losses: number;
  pct: string;
  wildCardGamesBack: string;
};

type WildCardApiRecord = {
  league?: { id?: number };
  teamRecords?: Array<{
    team?: { id?: number; name?: string };
    leagueRecord?: { wins?: number; losses?: number; pct?: string };
    wildCardGamesBack?: string;
  }>;
};

/** One division’s standings (local grouping for layout only). */
type DivisionStandingsGroup = {
  divisionName: string;
  rows: StandingRow[];
};

function divisionSortKey(name: string): number {
  if (name.includes("East")) return 0;
  if (name.includes("Central")) return 1;
  if (name.includes("West")) return 2;
  return 3;
}

function parseStandingsRecords(records: unknown[]): {
  al: DivisionStandingsGroup[];
  nl: DivisionStandingsGroup[];
} {
  const al: DivisionStandingsGroup[] = [];
  const nl: DivisionStandingsGroup[] = [];

  for (const rec of records as RawStandingDivision[]) {
    const leagueId = rec.league?.id;
    const bucket =
      leagueId === AL_LEAGUE_ID ? al : leagueId === NL_LEAGUE_ID ? nl : null;
    if (!bucket) continue;

    const divisionName =
      (rec.division?.nameShort && rec.division.nameShort.trim()) ||
      (rec.division?.name && rec.division.name.trim()) ||
      "Division";
    const rows: StandingRow[] = [];

    for (const tr of rec.teamRecords ?? []) {
      const tid =
        typeof tr.team?.id === "number" && Number.isFinite(tr.team.id)
          ? tr.team.id
          : 0;
      rows.push({
        teamId: tid,
        teamName: tr.team?.name ?? "—",
        wins: tr.leagueRecord?.wins ?? 0,
        losses: tr.leagueRecord?.losses ?? 0,
        pct: tr.leagueRecord?.pct ?? "—",
        gamesBack: tr.gamesBack ?? "—",
        divisionName,
      });
    }

    bucket.push({ divisionName, rows });
  }

  const sortGroups = (groups: DivisionStandingsGroup[]) =>
    groups.sort(
      (a, b) =>
        divisionSortKey(a.divisionName) - divisionSortKey(b.divisionName),
    );

  sortGroups(al);
  sortGroups(nl);

  return { al, nl };
}

function parseWildCardStandings(records: unknown[]): {
  al: WildCardRow[];
  nl: WildCardRow[];
} {
  const al: WildCardRow[] = [];
  const nl: WildCardRow[] = [];

  for (const rec of records as WildCardApiRecord[]) {
    const leagueId = rec.league?.id;
    const bucket =
      leagueId === AL_LEAGUE_ID ? al : leagueId === NL_LEAGUE_ID ? nl : null;
    if (!bucket) continue;

    for (const tr of rec.teamRecords ?? []) {
      const tid =
        typeof tr.team?.id === "number" && Number.isFinite(tr.team.id)
          ? tr.team.id
          : 0;
      bucket.push({
        teamId: tid,
        teamName: tr.team?.name ?? "—",
        wins: tr.leagueRecord?.wins ?? 0,
        losses: tr.leagueRecord?.losses ?? 0,
        pct: tr.leagueRecord?.pct ?? "—",
        wildCardGamesBack: tr.wildCardGamesBack ?? "—",
      });
    }
  }

  return { al, nl };
}

function flattenGames(dates: ScheduleDate[]): ScheduleGame[] {
  const games: ScheduleGame[] = [];
  for (const d of dates) {
    for (const g of d.games ?? []) games.push(g);
  }
  return games.sort(
    (a, b) =>
      new Date(a.gameDate ?? 0).getTime() -
      new Date(b.gameDate ?? 0).getTime(),
  );
}

function formatGameTime(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return "—";
  }
}

function formatWL(side?: ScheduleTeamSide): string {
  const lr = side?.leagueRecord;
  if (!lr || lr.wins == null || lr.losses == null) return "—";
  return `${lr.wins}-${lr.losses}`;
}

function teamDisplayAbbrev(side?: ScheduleTeamSide): string {
  const t = side?.team;
  const abbr = t?.abbreviation?.trim();
  if (abbr) return abbr.toUpperCase();
  const code = t?.fileCode?.trim();
  if (code) return code.toUpperCase();
  return "—";
}

function probableStarterLabel(side?: ScheduleTeamSide): string | null {
  const name = side?.probablePitcher?.fullName?.trim();
  return name || null;
}

function probablePitcherSeasonSuffix(
  pitcher: ScheduleProbablePitcher | undefined,
): string {
  const sp = pitcher?.seasonPitching;
  if (!sp) return "";
  const era = sp.era ?? "—";
  return ` · ${sp.wins}-${sp.losses}, ${era} ERA`;
}

function getGameVisualState(
  game: ScheduleGame,
): "live" | "final" | "scheduled" {
  const abstract = game.status?.abstractGameState ?? "";
  const detailed = game.status?.detailedState ?? "";

  if (
    abstract === "Live" ||
    detailed === "In Progress" ||
    detailed.startsWith("Delayed")
  ) {
    return "live";
  }

  if (
    abstract === "Final" ||
    detailed === "Final" ||
    detailed === "Game Over" ||
    detailed === "Completed Early"
  ) {
    return "final";
  }

  return "scheduled";
}

function formatRunnersSituation(
  offense: ScheduleLinescoreOffense | undefined,
): string {
  if (!offense) return "Bases empty";
  const on: string[] = [];
  if (offense.first) on.push("1st");
  if (offense.second) on.push("2nd");
  if (offense.third) on.push("3rd");
  if (on.length === 0) return "Bases empty";
  return `Runners on ${on.join(", ")}`;
}

function formatLiveSituation(game: ScheduleGame): string {
  const lc = game.linescore;
  if (!lc?.currentInningOrdinal) return "—";
  const top = lc.isTopInning === true;
  const half = `${top ? "Top" : "Bot"} ${lc.currentInningOrdinal}`;
  const outs =
    lc.outs != null
      ? `${lc.outs} out${lc.outs === 1 ? "" : "s"}`
      : null;
  const bases = formatRunnersSituation(lc.offense);
  return [half, outs, bases].filter(Boolean).join(" · ");
}

function TeamLogoImage({
  teamId,
  size,
  teamName,
}: {
  teamId: number;
  size: number;
  teamName: string;
}) {
  const [hide, setHide] = useState(false);
  if (!teamId || hide) return null;
  return (
    <span
      className="relative inline-flex shrink-0 overflow-hidden"
      style={{ width: size, height: size }}
    >
      <Image
        src={getTeamLogoUrl(teamId)}
        alt={`${teamName} logo`}
        fill
        className="object-contain"
        sizes={`${size}px`}
        onError={() => setHide(true)}
      />
    </span>
  );
}

function GamesBanner({ games }: { games: ScheduleGame[] }) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const [overflowing, setOverflowing] = useState(false);

  const updateScrollState = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    const epsilon = 2;
    const isOverflowing = scrollWidth > clientWidth + epsilon;
    setOverflowing(isOverflowing);
    setCanScrollLeft(isOverflowing && scrollLeft > epsilon);
    setCanScrollRight(
      isOverflowing && scrollLeft + clientWidth < scrollWidth - epsilon,
    );
  }, []);

  useEffect(() => {
    updateScrollState();
    const el = scrollerRef.current;
    if (!el) return;
    const onScroll = () => updateScrollState();
    el.addEventListener("scroll", onScroll, { passive: true });
    const ro = new ResizeObserver(() => updateScrollState());
    ro.observe(el);
    const t = window.setTimeout(updateScrollState, 150);
    return () => {
      window.clearTimeout(t);
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
    };
  }, [games, updateScrollState]);

  const scrollByDirection = useCallback((dir: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    const amount = Math.max(200, Math.floor(el.clientWidth * 0.75)) * dir;
    el.scrollBy({ left: amount, behavior: "smooth" });
  }, []);

  if (games.length === 0) {
    return (
      <p className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] py-8 text-center text-sm text-[#7a8fa8]">
        No games on the schedule for today.
      </p>
    );
  }

  const showArrows = overflowing;

  return (
    <div className="relative rounded-xl border border-[#d0daea] bg-[#f4f7fb] px-0.5 py-1">
      {showArrows ? (
        <>
          <div
            className="pointer-events-none absolute inset-y-1 left-0 z-10 w-14 rounded-l-xl bg-gradient-to-r from-[#f4f7fb] from-25% via-[#f4f7fb]/75 to-transparent"
            aria-hidden
          />
          <div
            className="pointer-events-none absolute inset-y-1 right-0 z-10 w-14 rounded-r-xl bg-gradient-to-l from-[#f4f7fb] from-25% via-[#f4f7fb]/75 to-transparent"
            aria-hidden
          />
          <button
            type="button"
            aria-label="Scroll games left"
            disabled={!canScrollLeft}
            onClick={() => scrollByDirection(-1)}
            className="absolute left-1 top-1/2 z-20 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-[#d0daea] bg-white text-[#1e3a6b] shadow-md transition hover:border-[#1e3a6b] hover:bg-[#f4f7fb] disabled:pointer-events-none disabled:opacity-20"
          >
            <ChevronLeft className="h-5 w-5" strokeWidth={2.25} />
          </button>
          <button
            type="button"
            aria-label="Scroll games right"
            disabled={!canScrollRight}
            onClick={() => scrollByDirection(1)}
            className="absolute right-1 top-1/2 z-20 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-[#d0daea] bg-white text-[#1e3a6b] shadow-md transition hover:border-[#1e3a6b] hover:bg-[#f4f7fb] disabled:pointer-events-none disabled:opacity-20"
          >
            <ChevronRight className="h-5 w-5" strokeWidth={2.25} />
          </button>
        </>
      ) : null}

      <div
        ref={scrollerRef}
        className={`scroll-smooth flex min-h-[168px] gap-2 overflow-x-auto overflow-y-hidden py-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${
          showArrows ? "px-12" : "px-1"
        } `}
      >
        {games.map((game, idx) => (
          <CompactGameCard
            key={game.gamePk ?? `${game.gameDate ?? "g"}-${idx}`}
            game={game}
          />
        ))}
      </div>
    </div>
  );
}

function CompactGameCard({ game }: { game: ScheduleGame }) {
  const visual = getGameVisualState(game);
  const away = game.teams?.away;
  const home = game.teams?.home;
  const awayAbbr = teamDisplayAbbrev(away);
  const homeAbbr = teamDisplayAbbrev(home);
  const awayTeamName = away?.team?.name ?? "Away";
  const homeTeamName = home?.team?.name ?? "Home";
  const awayTeamId =
    typeof away?.team?.id === "number" && Number.isFinite(away.team.id)
      ? away.team.id
      : 0;
  const homeTeamId =
    typeof home?.team?.id === "number" && Number.isFinite(home.team.id)
      ? home.team.id
      : 0;
  const awayProbable = probableStarterLabel(away);
  const homeProbable = probableStarterLabel(home);
  const aScore = away?.score;
  const hScore = home?.score;
  const awayWL = formatWL(away);
  const homeWL = formatWL(home);
  const timeLabel = formatGameTime(game.gameDate);
  const liveLine = formatLiveSituation(game);

  const hasScore =
    aScore !== undefined &&
    hScore !== undefined &&
    (visual === "live" || visual === "final");

  const shell =
    visual === "live"
      ? "border-red-400/60 bg-gradient-to-b from-red-50 to-white ring-1 ring-red-500/15"
      : visual === "final"
        ? "border-[#d0daea] bg-[#f4f7fb]/80 saturate-90 opacity-95"
        : "border-[#d0daea] bg-white";

  return (
    <article
      className={`flex min-w-[152px] max-w-[176px] shrink-0 flex-col rounded-lg border px-2 py-2 shadow-sm shadow-[#1e3a6b]/5 transition-colors ${shell}`}
    >
      <div className="mb-1.5 flex items-center gap-1">
        {visual === "live" ? (
          <span
            className="relative flex h-1.5 w-1.5 shrink-0"
            title="Live"
            aria-hidden
          >
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500/70" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500" />
          </span>
        ) : null}
        <span className="text-[8px] font-bold uppercase tracking-widest text-[#7a8fa8]">
          {visual === "live"
            ? "Live"
            : visual === "final"
              ? "Final"
              : "Next"}
        </span>
      </div>

      <div className="space-y-1 text-[11px]">
        <div className="flex items-start justify-between gap-1.5">
          <div className="flex min-w-0 flex-1 items-start gap-1.5">
            <TeamLogoImage
              size={28}
              teamId={awayTeamId}
              teamName={awayTeamName}
            />
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold leading-tight text-[#0f2044]">
                {awayAbbr}
              </p>
              <p className="tabular-nums text-[9px] text-[#7a8fa8]">{awayWL}</p>
            </div>
          </div>
          {hasScore ? (
            <span
              className={`shrink-0 tabular-nums text-sm font-bold leading-none ${
                visual === "live" ? "text-[#0f2044]" : "text-[#7a8fa8]"
              }`}
            >
              {aScore}
            </span>
          ) : null}
        </div>
        <div className="flex items-start justify-between gap-1.5">
          <div className="flex min-w-0 flex-1 items-start gap-1.5">
            <TeamLogoImage
              size={28}
              teamId={homeTeamId}
              teamName={homeTeamName}
            />
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold leading-tight text-[#0f2044]">
                {homeAbbr}
              </p>
              <p className="tabular-nums text-[9px] text-[#7a8fa8]">{homeWL}</p>
            </div>
          </div>
          {hasScore ? (
            <span
              className={`shrink-0 tabular-nums text-sm font-bold leading-none ${
                visual === "live" ? "text-[#0f2044]" : "text-[#7a8fa8]"
              }`}
            >
              {hScore}
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-auto border-t border-[#f0f4f9] pt-1.5">
        {visual === "scheduled" ? (
          <>
            <time
              className="text-[10px] font-medium tabular-nums text-[#7a8fa8]"
              dateTime={game.gameDate}
            >
              {timeLabel}
            </time>
            <div className="mt-1.5 space-y-0.5">
              <p
                className="truncate text-[9px] leading-snug text-[#7a8fa8]"
                title={`${awayAbbr}: ${awayProbable ?? "TBA"}${probablePitcherSeasonSuffix(away?.probablePitcher)}`}
              >
                <span className="font-semibold tabular-nums text-[#1e3050]">
                  {awayAbbr}
                </span>{" "}
                <span className="text-[#7a8fa8]">
                  {awayProbable ?? "TBA"}
                  <span className="tabular-nums text-[#7a8fa8]">
                    {probablePitcherSeasonSuffix(away?.probablePitcher)}
                  </span>
                </span>
              </p>
              <p
                className="truncate text-[9px] leading-snug text-[#7a8fa8]"
                title={`${homeAbbr}: ${homeProbable ?? "TBA"}${probablePitcherSeasonSuffix(home?.probablePitcher)}`}
              >
                <span className="font-semibold tabular-nums text-[#1e3050]">
                  {homeAbbr}
                </span>{" "}
                <span className="text-[#7a8fa8]">
                  {homeProbable ?? "TBA"}
                  <span className="tabular-nums text-[#7a8fa8]">
                    {probablePitcherSeasonSuffix(home?.probablePitcher)}
                  </span>
                </span>
              </p>
            </div>
          </>
        ) : null}
        {visual === "live" ? (
          <p className="line-clamp-2 text-[9px] leading-snug text-[#7a8fa8]">
            {liveLine}
          </p>
        ) : null}
        {visual === "final" ? (
          <p className="text-[9px] text-[#7a8fa8]">Final</p>
        ) : null}
      </div>
    </article>
  );
}

/** Team name in standings: links to ``/teams/[id]`` with a subtle hover underline. */
function StandingsTeamNameCell({
  teamId,
  teamName,
}: {
  teamId: number;
  teamName: string;
}) {
  const nameEl = !teamId ? (
    <span className="text-[#1e3050]">{teamName}</span>
  ) : (
    <Link
      href={`/teams/${teamId}`}
      className="inline-block text-[#1e3050] underline-offset-2 decoration-[#7a8fa8]/75 hover:text-[#1e3a6b] hover:underline"
    >
      {teamName}
    </Link>
  );

  return (
    <span className="inline-flex max-w-full items-center gap-1.5">
      <TeamLogoImage size={20} teamId={teamId} teamName={teamName} />
      <span className="min-w-0">{nameEl}</span>
    </span>
  );
}

function DivisionStandingsTable({ rows }: { rows: StandingRow[] }) {
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-[#f0f4f9] text-[10px] text-[#7a8fa8] uppercase tracking-wider">
          <th className="px-2 py-1.5 font-medium">Team</th>
          <th className="px-1 py-1.5 font-medium text-right">W</th>
          <th className="px-1 py-1.5 font-medium text-right">L</th>
          <th className="px-1 py-1.5 font-medium text-right">PCT</th>
          <th className="px-2 py-1.5 font-medium text-right">GB</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => {
          const playoff = isDivisionLeader(row.gamesBack);
          return (
            <tr
              key={`${row.teamId}-${row.teamName}-${row.divisionName}-${i}`}
              className={`border-b border-[#f0f4f9] transition-colors hover:bg-[#f4f7fb] ${playoffRowClass(playoff)}`}
            >
              <td
                className={`relative px-2 py-1 text-xs whitespace-nowrap ${playoffFirstCellClass(playoff)}`}
              >
                <StandingsTeamNameCell
                  teamId={row.teamId}
                  teamName={row.teamName}
                />
              </td>
              <td className="px-1 py-1 text-right text-xs tabular-nums text-[#1e3050]">
                {row.wins}
              </td>
              <td className="px-1 py-1 text-right text-xs tabular-nums text-[#1e3050]">
                {row.losses}
              </td>
              <td className="px-1 py-1 text-right text-xs tabular-nums text-[#1e3050]">
                {row.pct}
              </td>
              <td className="px-2 py-1 text-right text-xs tabular-nums text-[#7a8fa8]">
                {row.gamesBack}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function DivisionStandingsSection({
  divisionName,
  rows,
}: {
  divisionName: string;
  rows: StandingRow[];
}) {
  return (
    <div className="border-b border-[#f0f4f9] pb-2.5 last:border-b-0 last:pb-0">
      <h4 className="mb-1 text-xs font-semibold tracking-tight text-[#1e3a6b]">
        {divisionName}
      </h4>
      <div className="overflow-x-auto rounded-md border border-[#d0daea] bg-white">
        <DivisionStandingsTable rows={rows} />
      </div>
    </div>
  );
}

function WildCardStandingsTable({ rows }: { rows: WildCardRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="px-2 py-2 text-center text-xs text-[#7a8fa8]">
        No wild card data
      </p>
    );
  }

  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-[#f0f4f9] text-[10px] text-[#7a8fa8] uppercase tracking-wider">
          <th className="px-2 py-1.5 font-medium">Team</th>
          <th className="px-1 py-1.5 font-medium text-right">W</th>
          <th className="px-1 py-1.5 font-medium text-right">L</th>
          <th className="px-1 py-1.5 font-medium text-right">PCT</th>
          <th className="px-2 py-1.5 font-medium text-right">WC GB</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => {
          const playoff = isWildCardPlayoffPosition(row.wildCardGamesBack);
          return (
            <tr
              key={`${row.teamId}-${row.teamName}-wc-${i}`}
              className={`border-b border-[#f0f4f9] transition-colors hover:bg-[#f4f7fb] ${playoffRowClass(playoff)}`}
            >
              <td
                className={`relative px-2 py-1 text-xs whitespace-nowrap ${playoffFirstCellClass(playoff)}`}
              >
                <StandingsTeamNameCell
                  teamId={row.teamId}
                  teamName={row.teamName}
                />
              </td>
              <td className="px-1 py-1 text-right text-xs tabular-nums text-[#1e3050]">
                {row.wins}
              </td>
              <td className="px-1 py-1 text-right text-xs tabular-nums text-[#1e3050]">
                {row.losses}
              </td>
              <td className="px-1 py-1 text-right text-xs tabular-nums text-[#1e3050]">
                {row.pct}
              </td>
              <td className="px-2 py-1 text-right text-xs tabular-nums text-[#7a8fa8]">
                {row.wildCardGamesBack}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function LeagueStandingsColumn({
  title,
  divisionGroups,
  wildCardRows,
}: {
  title: string;
  divisionGroups: DivisionStandingsGroup[];
  wildCardRows: WildCardRow[];
}) {
  return (
    <div className="min-w-0 overflow-hidden rounded-lg border border-[#d0daea] bg-white">
      <div className="border-b border-[#d0daea] bg-[#f4f7fb] px-2.5 py-2">
        <h3 className="text-sm font-semibold tracking-wide text-[#0f2044]">
          {title}
        </h3>
      </div>
      <div className="space-y-0 px-2 py-2">
        {divisionGroups.map((group) => (
          <DivisionStandingsSection
            key={group.divisionName}
            divisionName={group.divisionName}
            rows={group.rows}
          />
        ))}
      </div>
      <div className="border-t border-[#d0daea] bg-[#f4f7fb] px-2 pb-2 pt-1.5">
        <div className="mb-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0 border-b border-[#f0f4f9] pb-1.5">
          <span
            className="h-4 w-0.5 shrink-0 self-center rounded-full bg-red-500"
            aria-hidden
          />
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-[#0f2044]">
            Wild card
          </h4>
          <span className="text-[10px] text-[#7a8fa8]">WC GB</span>
        </div>
        <div className="overflow-x-auto rounded-md border border-[#d0daea] bg-white">
          <WildCardStandingsTable rows={wildCardRows} />
        </div>
      </div>
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="flex min-h-[200px] flex-col items-center justify-center gap-3 rounded-xl border border-[#d0daea] bg-[#f4f7fb] p-8">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#1e3a6b] border-t-transparent" />
      <p className="text-sm text-[#7a8fa8]">Loading MLB data…</p>
    </div>
  );
}

export default function HomePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [games, setGames] = useState<ScheduleGame[]>([]);
  const [standings, setStandings] = useState<{
    al: DivisionStandingsGroup[];
    nl: DivisionStandingsGroup[];
  }>({
    al: [],
    nl: [],
  });
  const [wildCard, setWildCard] = useState<{
    al: WildCardRow[];
    nl: WildCardRow[];
  }>({
    al: [],
    nl: [],
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [schedRes, standRes] = await Promise.all([
        fetch("/api/schedule"),
        fetch("/api/standings"),
      ]);

      if (!schedRes.ok) {
        throw new Error("Could not load today’s schedule.");
      }
      if (!standRes.ok) {
        throw new Error("Could not load standings.");
      }

      const schedJson = (await schedRes.json()) as { dates?: ScheduleDate[] };
      const standJson = (await standRes.json()) as {
        records?: unknown[];
        wildCard?: unknown[];
      };

      setGames(flattenGames(schedJson.dates ?? []));
      setStandings(parseStandingsRecords(standJson.records ?? []));
      setWildCard(parseWildCardStandings(standJson.wildCard ?? []));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setGames([]);
      setStandings({ al: [], nl: [] });
      setWildCard({ al: [], nl: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="-mt-8 space-y-10">
      {error ? (
        <div
          className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <LoadingPanel />
      ) : (
        <>
          <section>
            <GamesBanner games={games} />
          </section>

          <section className="space-y-4">
            <h2 className="flex items-center gap-2 text-lg font-bold text-[#0f2044]">
              <span className="h-1 w-6 rounded-full bg-red-500" />
              Standings
            </h2>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-8">
              <LeagueStandingsColumn
                title="American League"
                divisionGroups={standings.al}
                wildCardRows={wildCard.al}
              />
              <LeagueStandingsColumn
                title="National League"
                divisionGroups={standings.nl}
                wildCardRows={wildCard.nl}
              />
            </div>
          </section>
        </>
      )}
    </div>
  );
}
