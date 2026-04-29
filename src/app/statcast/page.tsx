"use client";

import { useCallback, useEffect, useState } from "react";

import type { StatcastBatting } from "@/types";

export type LeaderboardStat =
  | "exit_velocity"
  | "launch_angle"
  | "hard_hit_rate"
  | "barrel_rate"
  | "sprint_speed"
  | "xwoba";

type LeaderboardRow = StatcastBatting & {
  players?: { team: string | null } | null;
};

const STAT_OPTIONS: { value: LeaderboardStat; label: string; column: string }[] = [
  { value: "exit_velocity", label: "Exit Velocity", column: "Avg EV" },
  { value: "launch_angle", label: "Launch Angle", column: "Avg LA" },
  { value: "hard_hit_rate", label: "Hard Hit Rate", column: "Hard-hit%" },
  { value: "barrel_rate", label: "Barrel Rate", column: "Barrel%" },
  { value: "sprint_speed", label: "Sprint Speed", column: "Sprint" },
  { value: "xwoba", label: "xWOBA", column: "xWOBA" },
];

function getStatValue(row: LeaderboardRow, stat: LeaderboardStat): number | null {
  switch (stat) {
    case "exit_velocity":
      return row.avg_exit_velocity != null ? Number(row.avg_exit_velocity) : null;
    case "launch_angle":
      return row.avg_launch_angle != null ? Number(row.avg_launch_angle) : null;
    case "hard_hit_rate":
      return row.hard_hit_rate != null ? Number(row.hard_hit_rate) : null;
    case "barrel_rate":
      return row.barrel_rate != null ? Number(row.barrel_rate) : null;
    case "sprint_speed":
      return row.sprint_speed != null ? Number(row.sprint_speed) : null;
    case "xwoba":
      return row.xwoba != null ? Number(row.xwoba) : null;
    default:
      return null;
  }
}

function formatStatValue(stat: LeaderboardStat, row: LeaderboardRow): string {
  const v = getStatValue(row, stat);
  if (v == null || Number.isNaN(v)) return "—";

  switch (stat) {
    case "exit_velocity":
      return `${v.toFixed(1)} mph`;
    case "launch_angle":
      return `${v.toFixed(1)}°`;
    case "hard_hit_rate":
    case "barrel_rate":
      return `${v <= 1 ? (v * 100).toFixed(1) : v.toFixed(1)}%`;
    case "sprint_speed":
      return `${v.toFixed(1)} ft/s`;
    case "xwoba":
      return v.toFixed(3);
    default:
      return String(v);
  }
}

export default function StatcastPage() {
  const season = new Date().getFullYear();
  const [stat, setStat] = useState<LeaderboardStat>("exit_velocity");
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (s: LeaderboardStat) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        stat: s,
        limit: "25",
        season: String(season),
      });
      const res = await fetch(`/api/statcast/leaderboard?${params}`);
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(body.error ?? "Could not load leaderboard.");
        setRows([]);
        return;
      }
      const data = (await res.json()) as {
        leaderboard?: LeaderboardRow[];
      };
      setRows(data.leaderboard ?? []);
    } catch {
      setError("Something went wrong while loading Statcast data.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [season]);

  useEffect(() => {
    void load(stat);
  }, [stat, load]);

  const statMeta = STAT_OPTIONS.find((o) => o.value === stat)!;

  return (
    <div className="space-y-8">
      <header className="space-y-4">
        <h1 className="text-3xl sm:text-4xl font-black tracking-tight">
          <span className="text-red-500">WAR</span>
          <span className="text-white">room</span>
          <span className="text-gray-400 font-semibold text-2xl sm:text-3xl ml-2">
            Statcast
          </span>
        </h1>
        <div className="max-w-3xl text-gray-400 text-sm leading-relaxed space-y-2">
          <p>
            Statcast captures MLB pitch- and batted-ball tracking: pitch velocity
            and movement, exit velocity, launch angle, sprint speed, and quality-of-contact
            estimates like expected weighted on-base average (xWOBA). Leaderboards below
            pull seasonal batting metrics from your WARroom database.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-end gap-4">
          <div>
            <label
              htmlFor="stat-select"
              className="block text-xs font-semibold uppercase tracking-widest text-gray-500 mb-2"
            >
              Metric
            </label>
            <select
              id="stat-select"
              value={stat}
              onChange={(e) => setStat(e.target.value as LeaderboardStat)}
              className="rounded-lg bg-gray-900 border border-gray-800 text-white text-sm px-4 py-3 min-w-[200px] focus:outline-none focus:ring-2 focus:ring-red-500/40 focus:border-red-900/50"
            >
              {STAT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <p className="text-sm text-gray-500 pb-1">
            Season <span className="text-gray-300 font-mono">{season}</span>
          </p>
        </div>
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
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 py-20 flex flex-col items-center justify-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-red-500 border-t-transparent animate-spin" />
          <p className="text-sm text-gray-500">Loading leaderboard…</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left min-w-[520px]">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/80 text-gray-500 uppercase text-xs tracking-wider">
                  <th className="px-4 py-3 font-medium w-14">#</th>
                  <th className="px-4 py-3 font-medium">Player</th>
                  <th className="px-4 py-3 font-medium">Team</th>
                  <th className="px-4 py-3 font-medium text-right">
                    {statMeta.column}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-12 text-center text-gray-500"
                    >
                      No rows for this metric and season yet.
                    </td>
                  </tr>
                ) : (
                  rows.map((row, i) => (
                    <tr
                      key={row.id ?? `${row.player_id}-${i}`}
                      className="border-b border-gray-800/80 hover:bg-gray-800/25 transition-colors"
                    >
                      <td className="px-4 py-3 text-gray-500 tabular-nums">
                        {i + 1}
                      </td>
                      <td className="px-4 py-3 text-white font-medium">
                        {row.player_name ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {row.players?.team ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-200 tabular-nums font-mono">
                        {formatStatValue(stat, row)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
