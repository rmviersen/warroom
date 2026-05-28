"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const SEASON_OPTIONS = Array.from(
  { length: 2026 - 1990 + 1 },
  (_, i) => 1990 + i,
);

const DEFAULT_SEASON = 2026;
const STATCAST_BASERUNNING_MIN_SEASON = 2016;

type BaserunningLeaderboardRow = {
  player_id: number;
  full_name: string | null;
  team_id: number | null;
  team_abbreviation: string | null;
  season: number;
  sb: number | null;
  cs: number | null;
  brwpr: number | null;
  runner_runs_tot: number | null;
  runner_runs_xb: number | null;
  runner_runs_sbx: number | null;
};

function formatIntish(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return String(Math.round(Number(v)));
}

function formatBrwpr(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(1);
}

function formatRunValue(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const fixed = n.toFixed(1);
  if (n > 0) return `+${fixed}`;
  return fixed;
}

function formatTeam(row: BaserunningLeaderboardRow): string {
  if (row.team_abbreviation?.trim()) return row.team_abbreviation.trim();
  if (row.team_id != null) return String(row.team_id);
  return "—";
}

export default function BaserunningLeaderboardPage() {
  const [season, setSeason] = useState(DEFAULT_SEASON);
  const [players, setPlayers] = useState<BaserunningLeaderboardRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        season: String(season),
        limit: "100",
      });
      const res = await fetch(`/api/leaderboards/baserunning?${params}`);
      const body = (await res.json().catch(() => ({}))) as {
        error?: string;
        players?: BaserunningLeaderboardRow[];
      };
      if (!res.ok) {
        setPlayers([]);
        setError(body.error ?? "Could not load leaderboard.");
        return;
      }
      setPlayers(body.players ?? []);
    } catch {
      setPlayers([]);
      setError("Something went wrong while loading the leaderboard.");
    } finally {
      setLoading(false);
    }
  }, [season]);

  useEffect(() => {
    void load();
  }, [load]);

  const controlCls =
    "rounded-lg bg-white border border-[#d0daea] text-[#0f2044] text-sm px-3 py-1.5 min-w-[120px] focus:outline-none focus:ring-2 focus:ring-[#1e3a6b]";

  const showStatcastNote = season < STATCAST_BASERUNNING_MIN_SEASON;

  return (
    <div className="bg-white space-y-8">
      <header className="space-y-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-[#0f2044]">
            Baserunning Leaderboard
          </h1>
          <span className="mt-1 inline-flex items-center rounded-md bg-[#1e3a6b] px-2 py-0.5 text-xs font-semibold tracking-wide text-[#c9a84c]">
            WR
          </span>
        </div>

        <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] p-4 sm:p-5">
          <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-4 text-sm">
            <div>
              <label
                htmlFor="lb-br-season"
                className="block text-xs font-semibold uppercase tracking-widest text-[#7a8fa8] mb-2"
              >
                Season
              </label>
              <select
                id="lb-br-season"
                value={season}
                onChange={(e) => setSeason(Number(e.target.value))}
                className={`${controlCls} py-3 px-4`}
              >
                {SEASON_OPTIONS.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
            {players.length > 0 ? (
              <div className="rounded-lg border border-[#d0daea] bg-white px-4 py-3 sm:mb-0 sm:pb-3">
                <p className="text-xs font-semibold uppercase tracking-wider text-[#7a8fa8] mb-1">
                  Showing
                </p>
                <p className="text-sm text-[#1e3050]">
                  Top{" "}
                  <span className="font-mono tabular-nums font-semibold text-[#0f2044]">
                    {players.length}
                  </span>{" "}
                  by brWPR
                </p>
              </div>
            ) : null}
          </div>
        </div>
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
        <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] py-20 flex flex-col items-center justify-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-[#1e3a6b] border-t-transparent animate-spin" />
          <p className="text-sm text-[#7a8fa8]">Loading leaderboard…</p>
        </div>
      ) : (
        <div className="rounded-xl border border-[#d0daea] bg-white overflow-hidden">
          <p className="border-b border-[#f0f4f9] bg-[#f4f7fb] px-4 py-2 text-xs text-[#7a8fa8]">
            Total Runs, SB Runs, and XB Runs are available from{" "}
            {STATCAST_BASERUNNING_MIN_SEASON} onward (Statcast era).
            {showStatcastNote
              ? " Earlier seasons show — for those columns."
              : null}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left min-w-[880px]">
              <thead>
                <tr className="bg-[#f4f7fb] border-b border-[#f0f4f9] uppercase text-xs tracking-wider text-[#7a8fa8]">
                  <th className="px-3 py-3 font-medium w-12 font-semibold text-[#7a8fa8]">
                    Rank
                  </th>
                  <th className="px-3 py-3 font-medium font-semibold text-[#7a8fa8]">
                    Player
                  </th>
                  <th className="px-3 py-3 font-medium font-semibold text-[#7a8fa8]">
                    Team
                  </th>
                  <th className="px-3 py-3 font-medium text-right font-semibold text-[#7a8fa8]">
                    SB
                  </th>
                  <th className="px-3 py-3 font-medium text-right font-semibold text-[#7a8fa8]">
                    CS
                  </th>
                  <th className="px-3 py-3 font-medium text-right font-semibold text-[#7a8fa8]">
                    SB Runs
                  </th>
                  <th
                    className="px-3 py-3 font-medium text-right font-semibold text-[#7a8fa8]"
                    title="Extra bases taken"
                  >
                    <span>XB Runs</span>
                    <span className="mt-0.5 block text-[10px] font-normal normal-case tracking-normal text-[#7a8fa8]">
                      Extra bases taken
                    </span>
                  </th>
                  <th className="px-3 py-3 font-medium text-right font-semibold text-[#7a8fa8]">
                    Total Runs
                  </th>
                  <th className="px-3 py-3 font-medium text-right font-semibold text-[#b8922a]">
                    brWPR
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f0f4f9] text-[#1e3050]">
                {players.map((row, idx) => (
                  <tr
                    key={`${row.player_id}-${row.season}-${idx}`}
                    className="bg-white hover:bg-[#f4f7fb] transition-colors"
                  >
                    <td className="px-3 py-2.5 font-mono tabular-nums text-[#7a8fa8]">
                      {idx + 1}
                    </td>
                    <td className="px-3 py-2.5">
                      <Link
                        href={`/players/${row.player_id}`}
                        className="text-[#1e3a6b] hover:underline font-medium"
                      >
                        {row.full_name?.trim()
                          ? row.full_name.trim()
                          : `Player ${row.player_id}`}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 font-mono tabular-nums text-[#1e3050]">
                      {formatTeam(row)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatIntish(row.sb)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatIntish(row.cs)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatRunValue(row.runner_runs_sbx)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatRunValue(row.runner_runs_xb)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatRunValue(row.runner_runs_tot)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums font-bold text-[#b8922a]">
                      {formatBrwpr(row.brwpr)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!loading && players.length === 0 && !error ? (
            <p className="px-4 py-8 text-center text-[#7a8fa8] text-sm border-t border-[#f0f4f9]">
              No rows match these filters.
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}
