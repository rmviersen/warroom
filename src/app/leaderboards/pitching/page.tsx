"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const SEASON_OPTIONS = Array.from(
  { length: 2026 - 1990 + 1 },
  (_, i) => 1990 + i,
);

const DEFAULT_SEASON = 2026;
const DEFAULT_MIN_IP = 20;

type SortKey =
  | "ip"
  | "era"
  | "fip"
  | "era_plus"
  | "k_per_9"
  | "bb_per_9"
  | "whip"
  | "pwpr"
  | "stuff_plus";

type SortDir = "asc" | "desc";

const ASC_DEFAULT_KEYS: SortKey[] = ["era", "fip", "whip", "bb_per_9"];

type PitchingLeaderboardRow = {
  id: number;
  player_id: number | null;
  player_name?: string | null;
  season: number | null;
  team: string | null;
  ip: number | null;
  era: number | null;
  fip: number | null;
  era_plus: number | null;
  k_per_9: number | null;
  bb_per_9: number | null;
  whip: number | null;
  pwpr: number | null;
  stuff_plus: number | null;
};

/** ERA+: average-or-better highlighting (no proprietary gold tier). */
function tierEraPlusStyle(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "text-[#7a8fa8]";
  const n = Number(v);
  if (n >= 90) return "text-[#0f2044]";
  return "text-[#7a8fa8]";
}

/** Stuff+: elite tier uses proprietary gold accent. */
function tierStuffPlusStyle(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "text-[#7a8fa8]";
  const n = Number(v);
  if (n >= 115) return "text-[#b8922a] font-semibold";
  if (n >= 90) return "text-[#0f2044]";
  return "text-[#7a8fa8]";
}

/** pWPR: elite-season proxy for wins scale; gold when clearly high impact. */
function tierPwprStyle(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "text-[#7a8fa8]";
  const n = Number(v);
  if (n >= 4) return "text-[#b8922a] font-semibold";
  if (n >= 1.5) return "text-[#0f2044]";
  return "text-[#7a8fa8]";
}

function formatIp(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(1);
}

function formatTwoDecimals(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(2);
}

function formatIntish(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return String(Math.round(Number(v)));
}

function formatPwprStuff(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(1);
}

const SORTABLE: { key: SortKey; label: string }[] = [
  { key: "ip", label: "IP" },
  { key: "era", label: "ERA" },
  { key: "fip", label: "FIP" },
  { key: "era_plus", label: "ERA+" },
  { key: "k_per_9", label: "K/9" },
  { key: "bb_per_9", label: "BB/9" },
  { key: "whip", label: "WHIP" },
  { key: "pwpr", label: "pWPR" },
  { key: "stuff_plus", label: "Stuff+" },
];

export default function PitchingLeaderboardPage() {
  const [season, setSeason] = useState(DEFAULT_SEASON);
  const [minIpInput, setMinIpInput] = useState(String(DEFAULT_MIN_IP));
  const [minIp, setMinIp] = useState(DEFAULT_MIN_IP);
  const [sortBy, setSortBy] = useState<SortKey>("pwpr");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const [pitchers, setPitchers] = useState<PitchingLeaderboardRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => {
      const n = parseInt(minIpInput.trim(), 10);
      if (minIpInput.trim() === "") {
        setMinIp(DEFAULT_MIN_IP);
        return;
      }
      if (!Number.isFinite(n) || n < 0) return;
      setMinIp(n);
    }, 400);
    return () => window.clearTimeout(t);
  }, [minIpInput]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        season: String(season),
        min_ip: String(minIp),
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: "100",
      });
      const res = await fetch(`/api/leaderboards/pitching?${params}`);
      const body = (await res.json().catch(() => ({}))) as {
        error?: string;
        pitchers?: PitchingLeaderboardRow[];
        total?: number;
      };
      if (!res.ok) {
        setPitchers([]);
        setTotal(0);
        setError(body.error ?? "Could not load leaderboard.");
        return;
      }
      setPitchers(body.pitchers ?? []);
      setTotal(body.total ?? 0);
    } catch {
      setPitchers([]);
      setTotal(0);
      setError("Something went wrong while loading the leaderboard.");
    } finally {
      setLoading(false);
    }
  }, [season, minIp, sortBy, sortDir]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSortHeader = (key: SortKey) => {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir(ASC_DEFAULT_KEYS.includes(key) ? "asc" : "desc");
    }
  };

  const controlCls =
    "rounded-lg bg-white border border-[#d0daea] text-[#0f2044] text-sm px-3 py-1.5 min-w-[120px] focus:outline-none focus:ring-2 focus:ring-[#1e3a6b]";

  return (
    <div className="bg-white space-y-8">
      <header className="space-y-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-[#0f2044]">
            Pitching Leaderboard
          </h1>
          <span className="mt-1 inline-flex items-center rounded-md bg-[#1e3a6b] px-2 py-0.5 text-xs font-semibold tracking-wide text-[#c9a84c]">
            WR
          </span>
        </div>

        <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] p-4 sm:p-5">
          <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-4 text-sm">
            <div>
              <label
                htmlFor="lb-pitch-season"
                className="block text-xs font-semibold uppercase tracking-widest text-[#7a8fa8] mb-2"
              >
                Season
              </label>
              <select
                id="lb-pitch-season"
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
            <div>
              <label
                htmlFor="lb-min-ip"
                className="block text-xs font-semibold uppercase tracking-widest text-[#7a8fa8] mb-2"
              >
                Min IP
              </label>
              <input
                id="lb-min-ip"
                type="number"
                min={0}
                step={1}
                value={minIpInput}
                onChange={(e) => setMinIpInput(e.target.value)}
                className={`${controlCls} w-28 font-mono py-3 px-4`}
              />
            </div>
            {total > 0 ? (
              <div className="rounded-lg border border-[#d0daea] bg-white px-4 py-3 sm:mb-0 sm:pb-3">
                <p className="text-xs font-semibold uppercase tracking-wider text-[#7a8fa8] mb-1">
                  Qualified pool
                </p>
                <p className="text-sm text-[#1e3050]">
                  <span className="font-mono tabular-nums">{pitchers.length}</span>{" "}
                  <span className="text-[#7a8fa8]">of</span>{" "}
                  <span className="font-mono tabular-nums font-semibold text-[#0f2044]">
                    {total}
                  </span>
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left min-w-[960px]">
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
                  {SORTABLE.map((col) => {
                    const active = sortBy === col.key;
                    const isProprietary =
                      col.key === "pwpr" || col.key === "stuff_plus";
                    const inactiveCls = isProprietary
                      ? "text-[#b8922a] font-semibold"
                      : "font-semibold text-[#7a8fa8]";
                    const activeCls = "text-[#1e3a6b] font-semibold";
                    return (
                      <th key={col.key} className="px-3 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => onSortHeader(col.key)}
                          className={`inline-flex items-center gap-1 tracking-wider uppercase transition-colors hover:text-[#1e3a6b] ${
                            active ? activeCls : inactiveCls
                          }`}
                        >
                          {col.label}
                          {active ? (
                            <span className="text-[#1e3a6b] font-normal" aria-hidden>
                              {sortDir === "desc" ? "↓" : "↑"}
                            </span>
                          ) : null}
                        </button>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f0f4f9] text-[#1e3050]">
                {pitchers.map((row, idx) => (
                  <tr
                    key={row.id}
                    className="bg-white hover:bg-[#f4f7fb] transition-colors"
                  >
                    <td className="px-3 py-2.5 font-mono tabular-nums text-[#7a8fa8]">
                      {idx + 1}
                    </td>
                    <td className="px-3 py-2.5">
                      {row.player_id != null ? (
                        <Link
                          href={`/players/${row.player_id}`}
                          className="text-[#1e3a6b] hover:underline font-medium"
                        >
                          {row.player_name?.trim()
                            ? row.player_name.trim()
                            : `Player ${row.player_id}`}
                        </Link>
                      ) : (
                        <span className="text-[#7a8fa8] font-medium">
                          {row.player_name?.trim()
                            ? row.player_name.trim()
                            : "—"}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-[#1e3050]">
                      {row.team?.trim() ? row.team.trim() : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatIp(row.ip)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatTwoDecimals(row.era)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatTwoDecimals(row.fip)}
                    </td>
                    <td
                      className={`px-3 py-2.5 text-right font-mono tabular-nums ${tierEraPlusStyle(
                        row.era_plus != null ? Number(row.era_plus) : null,
                      )}`}
                    >
                      {formatIntish(row.era_plus)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatTwoDecimals(row.k_per_9)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatTwoDecimals(row.bb_per_9)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatTwoDecimals(row.whip)}
                    </td>
                    <td
                      className={`px-3 py-2.5 text-right font-mono tabular-nums ${tierPwprStyle(
                        row.pwpr != null ? Number(row.pwpr) : null,
                      )}`}
                    >
                      {formatPwprStuff(row.pwpr)}
                    </td>
                    <td
                      className={`px-3 py-2.5 text-right font-mono tabular-nums ${tierStuffPlusStyle(
                        row.stuff_plus != null ? Number(row.stuff_plus) : null,
                      )}`}
                    >
                      {formatPwprStuff(row.stuff_plus)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!loading && pitchers.length === 0 && !error ? (
            <p className="px-4 py-8 text-center text-[#7a8fa8] text-sm border-t border-[#f0f4f9]">
              No rows match these filters.
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}
