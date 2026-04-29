"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

import type { StandingRow } from "@/types";

const AL_LEAGUE_ID = 103;
const NL_LEAGUE_ID = 104;

type ScheduleGame = {
  gamePk?: number;
  gameDate?: string;
  status?: { detailedState?: string; abstractGameState?: string };
  teams?: {
    away?: { team?: { name?: string }; score?: number };
    home?: { team?: { name?: string }; score?: number };
  };
};

type ScheduleDate = { games?: ScheduleGame[] };

type RawStandingDivision = {
  league?: { id?: number; name?: string };
  division?: { id?: number; name?: string };
  teamRecords?: Array<{
    team?: { name?: string };
    leagueRecord?: { wins?: number; losses?: number; pct?: string };
    gamesBack?: string;
  }>;
};

function divisionSortKey(name: string): number {
  if (name.includes("East")) return 0;
  if (name.includes("Central")) return 1;
  if (name.includes("West")) return 2;
  return 3;
}

function parseStandingsRecords(records: unknown[]): {
  al: StandingRow[];
  nl: StandingRow[];
} {
  const al: StandingRow[] = [];
  const nl: StandingRow[] = [];

  for (const rec of records as RawStandingDivision[]) {
    const leagueId = rec.league?.id;
    const bucket =
      leagueId === AL_LEAGUE_ID ? al : leagueId === NL_LEAGUE_ID ? nl : null;
    if (!bucket) continue;

    const divisionName = rec.division?.name ?? "";

    for (const tr of rec.teamRecords ?? []) {
      bucket.push({
        teamName: tr.team?.name ?? "—",
        wins: tr.leagueRecord?.wins ?? 0,
        losses: tr.leagueRecord?.losses ?? 0,
        pct: tr.leagueRecord?.pct ?? "—",
        gamesBack: tr.gamesBack ?? "—",
        divisionName,
      });
    }
  }

  const sortRows = (a: StandingRow, b: StandingRow) => {
    const d = divisionSortKey(a.divisionName) - divisionSortKey(b.divisionName);
    if (d !== 0) return d;
    const pctA = parseFloat(a.pct) || 0;
    const pctB = parseFloat(b.pct) || 0;
    return pctB - pctA;
  };

  al.sort(sortRows);
  nl.sort(sortRows);

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

function scoreline(game: ScheduleGame): string {
  const away = game.teams?.away;
  const home = game.teams?.home;
  const state = game.status?.abstractGameState ?? "";
  const detailed = game.status?.detailedState ?? "";

  const awayName = away?.team?.name ?? "Away";
  const homeName = home?.team?.name ?? "Home";

  const aScore = away?.score;
  const hScore = home?.score;
  const hasScore =
    aScore !== undefined &&
    hScore !== undefined &&
    (state === "Live" ||
      state === "Final" ||
      detailed === "In Progress" ||
      detailed === "Final" ||
      detailed === "Game Over");

  if (hasScore) {
    return `${awayName} ${aScore} @ ${homeName} ${hScore}`;
  }

  return `${awayName} @ ${homeName}`;
}

function statusText(game: ScheduleGame): string {
  return game.status?.detailedState ?? game.status?.abstractGameState ?? "—";
}

function StandingsTable({
  title,
  rows,
}: {
  title: string;
  rows: StandingRow[];
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/80">
        <h3 className="text-sm font-semibold text-white tracking-wide">
          {title}
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="border-b border-gray-800 text-gray-500 uppercase text-xs tracking-wider">
              <th className="px-4 py-2 font-medium">Team</th>
              <th className="px-2 py-2 font-medium text-right">W</th>
              <th className="px-2 py-2 font-medium text-right">L</th>
              <th className="px-2 py-2 font-medium text-right">PCT</th>
              <th className="px-4 py-2 font-medium text-right">GB</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const prev = rows[i - 1];
              const divisionLabel =
                row.divisionName &&
                row.divisionName !== prev?.divisionName
                  ? row.divisionName
                  : null;
              return (
                <Fragment key={`${row.teamName}-${row.divisionName}-${i}`}>
                  {divisionLabel ? (
                    <tr className="bg-gray-950/80">
                      <td
                        colSpan={5}
                        className="px-4 py-2 text-xs font-semibold text-red-500/90 uppercase tracking-wide"
                      >
                        {divisionLabel}
                      </td>
                    </tr>
                  ) : null}
                  <tr className="border-b border-gray-800/80 hover:bg-gray-800/30 transition-colors">
                    <td className="px-4 py-2.5 text-gray-200 whitespace-nowrap">
                      {row.teamName}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-gray-300">
                      {row.wins}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-gray-300">
                      {row.losses}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-gray-300">
                      {row.pct}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-400">
                      {row.gamesBack}
                    </td>
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-8 flex flex-col items-center justify-center gap-3 min-h-[200px]">
      <div className="h-8 w-8 rounded-full border-2 border-red-500 border-t-transparent animate-spin" />
      <p className="text-sm text-gray-500">Loading MLB data…</p>
    </div>
  );
}

export default function HomePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [games, setGames] = useState<ScheduleGame[]>([]);
  const [standings, setStandings] = useState<{ al: StandingRow[]; nl: StandingRow[] }>({
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
      const standJson = (await standRes.json()) as { records?: unknown[] };

      setGames(flattenGames(schedJson.dates ?? []));
      setStandings(parseStandingsRecords(standJson.records ?? []));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setGames([]);
      setStandings({ al: [], nl: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-10">
      <header className="text-center space-y-3 pt-4">
        <h1 className="text-4xl sm:text-5xl font-black tracking-tight">
          <span className="text-red-500">WAR</span>
          <span className="text-white">room</span>
        </h1>
        <p className="text-gray-400 max-w-2xl mx-auto text-lg">
          Today&apos;s schedule and full-league standings — powered by the MLB
          Stats API.
        </p>
      </header>

      {error ? (
        <div
          className="rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-3 text-red-200 text-sm"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <LoadingPanel />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-10 items-start">
          <section className="space-y-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <span className="h-1 w-6 rounded-full bg-red-500" />
              Today&apos;s games
            </h2>
            {games.length === 0 ? (
              <p className="text-gray-500 text-sm py-8 text-center rounded-xl border border-gray-800 bg-gray-900/30">
                No games on the schedule for today.
              </p>
            ) : (
              <ul className="space-y-3">
                {games.map((game, idx) => (
                  <li
                    key={game.gamePk ?? `${game.gameDate ?? "g"}-${idx}`}
                    className="rounded-xl border border-gray-800 bg-gray-900/50 px-4 py-4 hover:border-gray-700 transition-colors"
                  >
                    <p className="text-white font-medium">{scoreline(game)}</p>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                      <span>{formatGameTime(game.gameDate)}</span>
                      <span className="text-gray-400">{statusText(game)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-6">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <span className="h-1 w-6 rounded-full bg-red-500" />
              Standings
            </h2>
            <StandingsTable title="American League" rows={standings.al} />
            <StandingsTable title="National League" rows={standings.nl} />
          </section>
        </div>
      )}
    </div>
  );
}
