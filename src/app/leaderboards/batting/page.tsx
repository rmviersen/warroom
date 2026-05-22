"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const SEASON_OPTIONS = Array.from(
  { length: 2026 - 2015 + 1 },
  (_, i) => 2015 + i,
);

const DEFAULT_SEASON = 2026;
const DEFAULT_MIN_PA = 50;

type SortKey =
  | "pa"
  | "avg"
  | "obp"
  | "slg"
  | "hr"
  | "wrc_plus"
  | "ops_plus"
  | "woba"
  | "bwpr"
  | "cqi";

type SortDir = "asc" | "desc";

type BattingLeaderboardRow = {
  id: number;
  player_id: number;
  player_name?: string | null;
  season: number;
  team: string | null;
  pa: number | null;
  avg: number | null;
  obp: number | null;
  slg: number | null;
  hr: number | null;
  wrc_plus: number | null;
  ops_plus: number | null;
  woba: number | null;
  bwpr: number | null;
  cqi: number | null;
};

/** wRC+: average-or-better highlighting (no proprietary gold tier). */
function tierWrcPlusStyle(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "text-[#7a8fa8]";
  const n = Number(v);
  if (n >= 90) return "text-[#0f2044]";
  return "text-[#7a8fa8]";
}

/** CQI: elite tier uses proprietary gold accent. */
function tierCqiStyle(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "text-[#7a8fa8]";
  const n = Number(v);
  if (n >= 115) return "text-[#b8922a] font-semibold";
  if (n >= 90) return "text-[#0f2044]";
  return "text-[#7a8fa8]";
}

/** bWPR: elite-season proxy for wins scale; gold when clearly high impact. */
function tierBwprStyle(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "text-[#7a8fa8]";
  const n = Number(v);
  if (n >= 5) return "text-[#b8922a] font-semibold";
  if (n >= 2) return "text-[#0f2044]";
  return "text-[#7a8fa8]";
}

function formatAvgLike(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(3);
}

function formatIntish(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return String(Math.round(Number(v)));
}

function formatWoba(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(3);
}

function formatWprCqi(v: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(1);
}

const SORTABLE: { key: SortKey; label: string }[] = [
  { key: "pa", label: "PA" },
  { key: "avg", label: "AVG" },
  { key: "obp", label: "OBP" },
  { key: "slg", label: "SLG" },
  { key: "hr", label: "HR" },
  { key: "wrc_plus", label: "wRC+" },
  { key: "ops_plus", label: "OPS+" },
  { key: "woba", label: "wOBA" },
  { key: "bwpr", label: "bWPR" },
  { key: "cqi", label: "CQI" },
];

export default function BattingLeaderboardPage() {
  const [season, setSeason] = useState(DEFAULT_SEASON);
  const [minPaInput, setMinPaInput] = useState(String(DEFAULT_MIN_PA));
  const [minPa, setMinPa] = useState(DEFAULT_MIN_PA);
  const [sortBy, setSortBy] = useState<SortKey>("cqi");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const [players, setPlayers] = useState<BattingLeaderboardRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => {
      const n = parseInt(minPaInput.trim(), 10);
      if (minPaInput.trim() === "") {
        setMinPa(DEFAULT_MIN_PA);
        return;
      }
      if (!Number.isFinite(n) || n < 0) return;
      setMinPa(n);
    }, 400);
    return () => window.clearTimeout(t);
  }, [minPaInput]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        season: String(season),
        min_pa: String(minPa),
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: "100",
      });
      const res = await fetch(`/api/leaderboards/batting?${params}`);
      const body = (await res.json().catch(() => ({}))) as {
        error?: string;
        players?: BattingLeaderboardRow[];
        total?: number;
      };
      if (!res.ok) {
        setPlayers([]);
        setTotal(0);
        setError(body.error ?? "Could not load leaderboard.");
        return;
      }
      setPlayers(body.players ?? []);
      setTotal(body.total ?? 0);
    } catch {
      setPlayers([]);
      setTotal(0);
      setError("Something went wrong while loading the leaderboard.");
    } finally {
      setLoading(false);
    }
  }, [season, minPa, sortBy, sortDir]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSortHeader = (key: SortKey) => {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
  };

  const controlCls =
    "rounded-lg bg-white border border-[#d0daea] text-[#0f2044] text-sm px-3 py-1.5 min-w-[120px] focus:outline-none focus:ring-2 focus:ring-[#1e3a6b]";

  return (
    <div className="bg-white space-y-8">
      <header className="space-y-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-[#0f2044]">
            Batting Leaderboard
          </h1>
          <span className="mt-1 inline-flex items-center rounded-md bg-[#1e3a6b] px-2 py-0.5 text-xs font-semibold tracking-wide text-[#c9a84c]">
            WR
          </span>
        </div>

        <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] p-4 sm:p-5">
          <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-4 text-sm">
            <div>
              <label
                htmlFor="lb-season"
                className="block text-xs font-semibold uppercase tracking-widest text-[#7a8fa8] mb-2"
              >
                Season
              </label>
              <select
                id="lb-season"
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
                htmlFor="lb-min-pa"
                className="block text-xs font-semibold uppercase tracking-widest text-[#7a8fa8] mb-2"
              >
                Min PA
              </label>
              <input
                id="lb-min-pa"
                type="number"
                min={0}
                step={1}
                value={minPaInput}
                onChange={(e) => setMinPaInput(e.target.value)}
                className={`${controlCls} w-28 font-mono py-3 px-4`}
              />
            </div>
            {total > 0 ? (
              <div className="rounded-lg border border-[#d0daea] bg-white px-4 py-3 sm:mb-0 sm:pb-3">
                <p className="text-xs font-semibold uppercase tracking-wider text-[#7a8fa8] mb-1">
                  Qualified pool
                </p>
                <p className="text-sm text-[#1e3050]">
                  <span className="font-mono tabular-nums">{players.length}</span>{" "}
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
                    const isProprietary = col.key === "bwpr" || col.key === "cqi";
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
                {players.map((row, idx) => (
                  <tr
                    key={row.id}
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
                        {row.player_name?.trim()
                          ? row.player_name.trim()
                          : `Player ${row.player_id}`}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-[#1e3050]">
                      {row.team?.trim() ? row.team.trim() : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {row.pa != null ? row.pa : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatAvgLike(row.avg)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatAvgLike(row.obp)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatAvgLike(row.slg)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatIntish(row.hr)}
                    </td>
                    <td
                      className={`px-3 py-2.5 text-right font-mono tabular-nums ${tierWrcPlusStyle(
                        row.wrc_plus != null ? Number(row.wrc_plus) : null,
                      )}`}
                    >
                      {formatIntish(row.wrc_plus)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatIntish(row.ops_plus)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-[#1e3050]">
                      {formatWoba(row.woba)}
                    </td>
                    <td
                      className={`px-3 py-2.5 text-right font-mono tabular-nums ${tierBwprStyle(
                        row.bwpr != null ? Number(row.bwpr) : null,
                      )}`}
                    >
                      {formatWprCqi(row.bwpr)}
                    </td>
                    <td
                      className={`px-3 py-2.5 text-right font-mono tabular-nums ${tierCqiStyle(
                        row.cqi != null ? Number(row.cqi) : null,
                      )}`}
                    >
                      {formatWprCqi(row.cqi)}
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
