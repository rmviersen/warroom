"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getTeamLogoUrl } from "@/lib/mlb-images";
import {
  playoffFirstCellClass,
  playoffRowClass,
} from "@/lib/playoff-teams";
import type { TeamOverview, TeamOverviewStat } from "@/types";

const AL_ID = 103;
const NL_ID = 104;
const TOP_METRIC_RANK = 5;

type SortKey =
  | "team"
  | "wl"
  | "pct"
  | "rs"
  | "ra"
  | "era"
  | "whip"
  | "avg"
  | "slg"
  | "ops"
  | "hr";

type SortDir = "asc" | "desc";

const ASC_DEFAULT_KEYS: SortKey[] = ["era", "whip", "ra", "team"];

const SORT_COLUMNS: { key: SortKey; label: string }[] = [
  { key: "team", label: "Tm" },
  { key: "wl", label: "W-L" },
  { key: "pct", label: "Pct" },
  { key: "rs", label: "RS" },
  { key: "ra", label: "RA" },
  { key: "era", label: "ERA" },
  { key: "whip", label: "WHIP" },
  { key: "avg", label: "AVG" },
  { key: "slg", label: "SLG" },
  { key: "ops", label: "OPS" },
  { key: "hr", label: "HR" },
];

function winPct(team: TeamOverview): number {
  const games = team.wins + team.losses;
  if (games === 0) return 0;
  return team.wins / games;
}

function formatPct(team: TeamOverview): string {
  const games = team.wins + team.losses;
  if (games === 0) return "—";
  return winPct(team).toFixed(3).replace(/^0/, "");
}

function statNum(stat: TeamOverviewStat): number | null {
  if (stat.value == null) return null;
  const n = Number(stat.value);
  return Number.isFinite(n) ? n : null;
}

function compareNullable(a: number | null, b: number | null): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return a - b;
}

function compareTeams(a: TeamOverview, b: TeamOverview, key: SortKey): number {
  switch (key) {
    case "team":
      return (a.name ?? "").localeCompare(b.name ?? "");
    case "wl": {
      const pctDiff = compareNullable(winPct(a), winPct(b));
      if (pctDiff !== 0) return pctDiff;
      const winsDiff = compareNullable(a.wins, b.wins);
      if (winsDiff !== 0) return winsDiff;
      return compareNullable(a.losses, b.losses);
    }
    case "pct":
      return compareNullable(winPct(a), winPct(b));
    case "rs":
      return compareNullable(statNum(a.hitting.runsScored), statNum(b.hitting.runsScored));
    case "ra":
      return compareNullable(statNum(a.pitching.runsAllowed), statNum(b.pitching.runsAllowed));
    case "era":
      return compareNullable(statNum(a.pitching.era), statNum(b.pitching.era));
    case "whip":
      return compareNullable(statNum(a.pitching.whip), statNum(b.pitching.whip));
    case "avg":
      return compareNullable(statNum(a.hitting.avg), statNum(b.hitting.avg));
    case "slg":
      return compareNullable(statNum(a.hitting.slg), statNum(b.hitting.slg));
    case "ops":
      return compareNullable(statNum(a.hitting.ops), statNum(b.hitting.ops));
    case "hr":
      return compareNullable(statNum(a.hitting.homeRuns), statNum(b.hitting.homeRuns));
    default:
      return 0;
  }
}

function sortTeams(
  teams: TeamOverview[],
  sortBy: SortKey,
  sortDir: SortDir,
): TeamOverview[] {
  const sorted = [...teams].sort((a, b) => compareTeams(a, b, sortBy));
  if (sortDir === "desc") sorted.reverse();
  return sorted;
}

function TeamLogo({ teamId, teamName }: { teamId: number; teamName: string }) {
  const [hide, setHide] = useState(false);
  if (!teamId || hide) return null;

  return (
    <span
      className="relative inline-flex h-4 w-4 shrink-0 overflow-hidden"
      aria-hidden
    >
      <Image
        src={getTeamLogoUrl(teamId)}
        alt=""
        fill
        className="object-contain"
        sizes="16px"
        onError={() => setHide(true)}
      />
    </span>
  );
}

function isTopMetricRank(rank: number | null | undefined): boolean {
  return rank != null && rank >= 1 && rank <= TOP_METRIC_RANK;
}

function StatCell({ stat }: { stat: TeamOverviewStat }) {
  const top5 = isTopMetricRank(stat.rank);
  return (
    <span
      className={`inline-block font-mono text-[10px] tabular-nums leading-none sm:text-[11px] ${
        top5 ? "font-semibold text-[#b8922a]" : "text-[#1e3050]"
      }`}
    >
      {stat.value ?? "—"}
      {stat.rank != null ? (
        <span
          className={`ml-0.5 text-[8px] font-normal sm:text-[9px] ${
            top5 ? "text-[#b8922a]/80" : "text-[#7a8fa8]"
          }`}
        >
          #{stat.rank}
        </span>
      ) : null}
    </span>
  );
}

function teamDisplayLabel(team: TeamOverview): string {
  const abbr = team.abbreviation?.trim();
  if (abbr) return abbr.toUpperCase();
  const name = team.name?.trim();
  if (!name) return "—";
  return name.length > 4 ? name.slice(0, 3).toUpperCase() : name;
}

function SortHeader({
  label,
  active,
  sortDir,
  onClick,
  align = "right",
}: {
  label: string;
  active: boolean;
  sortDir: SortDir;
  onClick: () => void;
  align?: "left" | "right";
}) {
  return (
    <th className={`px-0.5 py-1.5 sm:px-1 ${align === "right" ? "text-right" : "text-left"}`}>
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-0.5 uppercase tracking-wide transition-colors hover:text-[#1e3a6b] ${
          active ? "font-semibold text-[#1e3a6b]" : "font-semibold text-[#7a8fa8]"
        } ${align === "right" ? "ml-auto" : ""}`}
      >
        {label}
        {active ? (
          <span className="font-normal" aria-hidden>
            {sortDir === "desc" ? "↓" : "↑"}
          </span>
        ) : null}
      </button>
    </th>
  );
}

function LeagueLeaderboard({
  title,
  teams,
}: {
  title: string;
  teams: TeamOverview[];
}) {
  const [sortBy, setSortBy] = useState<SortKey>("pct");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(
    () => sortTeams(teams, sortBy, sortDir),
    [teams, sortBy, sortDir],
  );

  const onSortHeader = (key: SortKey) => {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir(ASC_DEFAULT_KEYS.includes(key) ? "asc" : "desc");
    }
  };

  return (
    <section className="min-w-0">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-bold text-[#0f2044]">
        <span className="h-1 w-5 rounded-full bg-red-500" />
        {title}
      </h2>
      <div className="rounded-xl border border-[#d0daea] bg-white">
        <table className="w-full table-fixed text-left text-[10px] sm:text-[11px]">
          <colgroup>
            <col className="w-[5%]" />
            <col className="w-[12%]" />
            <col className="w-[8%]" />
            <col className="w-[7%]" />
            <col className="w-[7%]" />
            <col className="w-[7%]" />
            <col className="w-[8%]" />
            <col className="w-[8%]" />
            <col className="w-[7%]" />
            <col className="w-[7%]" />
            <col className="w-[7%]" />
            <col className="w-[7%]" />
            <col className="w-[6%]" />
          </colgroup>
          <thead>
            <tr className="border-b border-[#f0f4f9] bg-[#f4f7fb] text-[#7a8fa8]">
              <th className="px-0.5 py-1.5 text-center font-semibold sm:px-1">#</th>
              {SORT_COLUMNS.map((col) => (
                <SortHeader
                  key={col.key}
                  label={col.label}
                  active={sortBy === col.key}
                  sortDir={sortDir}
                  onClick={() => onSortHeader(col.key)}
                  align={col.key === "team" ? "left" : "right"}
                />
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#f0f4f9]">
            {sorted.map((team, idx) => {
              const rank = idx + 1;
              const playoff = team.playoff_position;
              const name = team.name?.trim() || `Team ${team.id}`;
              const label = teamDisplayLabel(team);

              return (
                <tr
                  key={team.id}
                  className={`transition-colors hover:bg-[#f4f7fb] ${playoffRowClass(playoff)}`}
                >
                  <td
                    className={`px-0.5 py-1 text-center font-mono tabular-nums text-[#7a8fa8] sm:px-1 ${playoffFirstCellClass(playoff)}`}
                  >
                    {rank}
                  </td>
                  <td className="px-0.5 py-1 sm:px-1">
                    <Link
                      href={`/teams/${team.id}`}
                      title={name}
                      className="inline-flex min-w-0 items-center gap-0.5 font-medium text-[#1e3a6b] hover:underline sm:gap-1"
                    >
                      <TeamLogo teamId={team.id} teamName={name} />
                      <span className="truncate">{label}</span>
                    </Link>
                  </td>
                  <td className="px-0.5 py-1 text-right font-mono tabular-nums text-[#1e3050] sm:px-1">
                    {team.wins}-{team.losses}
                  </td>
                  <td className="px-0.5 py-1 text-right font-mono tabular-nums text-[#1e3050] sm:px-1">
                    {formatPct(team)}
                  </td>
                  <td className="px-0.5 py-1 text-right sm:px-1">
                    <StatCell stat={team.hitting.runsScored} />
                  </td>
                  <td className="px-0.5 py-1 text-right sm:px-1">
                    <StatCell stat={team.pitching.runsAllowed} />
                  </td>
                  <td className="px-0.5 py-1 text-right sm:px-1">
                    <StatCell stat={team.pitching.era} />
                  </td>
                  <td className="px-0.5 py-1 text-right sm:px-1">
                    <StatCell stat={team.pitching.whip} />
                  </td>
                  <td className="px-0.5 py-1 text-right sm:px-1">
                    <StatCell stat={team.hitting.avg} />
                  </td>
                  <td className="px-0.5 py-1 text-right sm:px-1">
                    <StatCell stat={team.hitting.slg} />
                  </td>
                  <td className="px-0.5 py-1 text-right sm:px-1">
                    <StatCell stat={team.hitting.ops} />
                  </td>
                  <td className="px-0.5 py-1 text-right sm:px-1">
                    <StatCell stat={team.hitting.homeRuns} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function LoadingTables() {
  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
      {Array.from({ length: 2 }).map((_, i) => (
        <div
          key={i}
          className="h-[420px] rounded-xl border border-[#d0daea] bg-[#f4f7fb] animate-pulse"
        />
      ))}
    </div>
  );
}

export default function TeamsPage() {
  const [teams, setTeams] = useState<TeamOverview[]>([]);
  const [season, setSeason] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { alTeams, nlTeams } = useMemo(() => {
    const al = teams.filter((t) => t.league_id === AL_ID);
    const nl = teams.filter((t) => t.league_id === NL_ID);
    return { alTeams: al, nlTeams: nl };
  }, [teams]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/teams");
      if (!res.ok) throw new Error("Could not load teams.");
      const data = (await res.json()) as {
        teams?: TeamOverview[];
        season?: number;
      };
      setTeams(data.teams ?? []);
      setSeason(data.season ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setTeams([]);
      setSeason(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[#0f2044]">
            Teams
          </h1>
          <p className="mt-1 text-sm text-[#7a8fa8]">
            Click a column to sort. Gold rows = playoff position; gold stat
            text = top {TOP_METRIC_RANK} in MLB for that column.
          </p>
        </div>
        {season != null ? (
          <span className="rounded-md border border-[#d0daea] bg-[#f4f7fb] px-3 py-1.5 text-xs font-semibold tabular-nums text-[#1e3050]">
            {season} season
          </span>
        ) : null}
      </header>

      {error ? (
        <div
          className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-red-800 text-sm"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <LoadingTables />
      ) : (
        <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
          <LeagueLeaderboard title="American League" teams={alTeams} />
          <LeagueLeaderboard title="National League" teams={nlTeams} />
        </div>
      )}
    </div>
  );
}
