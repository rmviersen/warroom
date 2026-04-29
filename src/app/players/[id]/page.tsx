"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import type {
  PlayerBattingSeasonRow,
  PlayerFieldingSeasonRow,
  PlayerPitchingSeasonRow,
  PlayerProfileApiResponse,
  PlayerProfilePitchesApiResponse,
  PlayerRow,
  StatcastPitch,
} from "@/types";

type StatTier = "elite" | "average" | "below";

function normalizePercent(v: number | null): number | null {
  if (v == null || Number.isNaN(v)) return null;
  return v <= 1 ? v * 100 : v;
}

function tierExitVelo(mph: number | null): StatTier | null {
  if (mph == null) return null;
  if (mph >= 91) return "elite";
  if (mph >= 87) return "average";
  return "below";
}

function tierBarrel(pct: number | null): StatTier | null {
  if (pct == null) return null;
  if (pct >= 12) return "elite";
  if (pct >= 7) return "average";
  return "below";
}

function tierHardHit(pct: number | null): StatTier | null {
  if (pct == null) return null;
  if (pct >= 46) return "elite";
  if (pct >= 36) return "average";
  return "below";
}

function tierXwoba(x: number | null): StatTier | null {
  if (x == null) return null;
  if (x >= 0.37) return "elite";
  if (x >= 0.32) return "average";
  return "below";
}

function tierSprint(fps: number | null): StatTier | null {
  if (fps == null) return null;
  if (fps >= 29) return "elite";
  if (fps >= 27.8) return "average";
  return "below";
}

function tierClass(t: StatTier | null): string {
  if (!t) return "border-gray-800 bg-gray-900/40 text-gray-300";
  if (t === "elite") {
    return "border-emerald-600/50 bg-emerald-950/25 text-emerald-200";
  }
  if (t === "average") {
    return "border-amber-600/40 bg-amber-950/20 text-amber-100";
  }
  return "border-red-800/50 bg-red-950/25 text-red-200";
}

function formatPercentish(v: number | null): string {
  if (v == null) return "—";
  const p = normalizePercent(v);
  if (p == null) return "—";
  return `${p.toFixed(1)}%`;
}

function supabaseBioHasDisplayData(row: PlayerRow | null): boolean {
  if (!row) return false;
  const pieces = [
    row.debut_date,
    row.final_game,
    row.birth_date,
    row.name_first,
    row.name_last,
    row.birth_city,
    row.birth_country,
    row.height,
    row.weight,
    row.jersey_number,
    row.bats,
    row.throws,
  ];
  return pieces.some(
    (v) => v != null && v !== "" && (typeof v !== "number" || !Number.isNaN(v)),
  );
}

function DatabaseBioPanel({ row }: { row: PlayerRow }) {
  const rows: { label: string; value: string }[] = [];
  const push = (label: string, value: string | null | undefined) => {
    if (value == null || value === "") return;
    rows.push({ label, value: String(value) });
  };

  if (row.name_first || row.name_last) {
    push(
      "Name",
      [row.name_first, row.name_last].filter(Boolean).join(" ") || "—",
    );
  }
  push("Birth date", row.birth_date);
  push("Birthplace", [row.birth_city, row.birth_country].filter(Boolean).join(", ") || null);
  push("Debut", row.debut_date);
  push("Final game", row.final_game);
  push("Height", row.height);
  push("Weight", row.weight != null ? `${row.weight} lb` : null);
  push("Bats / throws", [row.bats, row.throws].filter(Boolean).join(" / ") || null);
  push("Jersey", row.jersey_number);
  if (row.active != null) {
    push("Roster status (DB)", row.active ? "Active" : "Inactive");
  }

  if (rows.length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 bg-gray-950/50">
        <h2 className="text-sm font-semibold text-white">Bio · database</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          From your Supabase players row (historical / roster cache).
        </p>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.label}
              className="border-t border-gray-800/80 first:border-t-0"
            >
              <th
                scope="row"
                className="py-3 px-4 text-left font-medium text-gray-400 w-2/5"
              >
                {r.label}
              </th>
              <td className="py-3 px-4 text-right text-gray-200">{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function fmtSlash(n: number | null | undefined, digits: number): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function HistoricalSeasonsSection({
  batting,
  pitching,
  fielding,
}: {
  batting: PlayerBattingSeasonRow[];
  pitching: PlayerPitchingSeasonRow[];
  fielding: PlayerFieldingSeasonRow[];
}) {
  if (batting.length === 0 && pitching.length === 0 && fielding.length === 0) {
    return null;
  }

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-sm font-semibold text-white">
          Historical seasons · database
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Season totals from Supabase (newest year first).
        </p>
      </div>

      {batting.length > 0 ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden">
          <div className="px-4 py-2 border-b border-gray-800 bg-gray-950/50 text-xs font-medium text-gray-400">
            Batting
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[640px]">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-800">
                  <th className="py-2 px-3 font-medium">Year</th>
                  <th className="py-2 px-3 font-medium">Team</th>
                  <th className="py-2 px-3 font-mono tabular-nums">PA</th>
                  <th className="py-2 px-3 font-mono tabular-nums">AVG</th>
                  <th className="py-2 px-3 font-mono tabular-nums">OBP</th>
                  <th className="py-2 px-3 font-mono tabular-nums">SLG</th>
                  <th className="py-2 px-3 font-mono tabular-nums">OPS</th>
                  <th className="py-2 px-3 font-mono tabular-nums">HR</th>
                  <th className="py-2 px-3 font-mono tabular-nums">wRC+</th>
                  <th className="py-2 px-3 font-mono tabular-nums">WAR</th>
                </tr>
              </thead>
              <tbody>
                {batting.map((r) => (
                  <tr
                    key={`${r.id}-bat`}
                    className="border-b border-gray-800/80 text-gray-200"
                  >
                    <td className="py-2 px-3 font-mono">{r.season}</td>
                    <td className="py-2 px-3 max-w-[140px] truncate">
                      {r.team ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {r.pa ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.avg, 3)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.obp, 3)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.slg, 3)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.ops, 3)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {r.hr ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {r.wrc_plus ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.war, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {pitching.length > 0 ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden">
          <div className="px-4 py-2 border-b border-gray-800 bg-gray-950/50 text-xs font-medium text-gray-400">
            Pitching
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[600px]">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-800">
                  <th className="py-2 px-3 font-medium">Year</th>
                  <th className="py-2 px-3 font-medium">Team</th>
                  <th className="py-2 px-3 font-mono tabular-nums">IP</th>
                  <th className="py-2 px-3 font-mono tabular-nums">ERA</th>
                  <th className="py-2 px-3 font-mono tabular-nums">WHIP</th>
                  <th className="py-2 px-3 font-mono tabular-nums">SO</th>
                  <th className="py-2 px-3 font-mono tabular-nums">BB</th>
                  <th className="py-2 px-3 font-mono tabular-nums">FIP</th>
                  <th className="py-2 px-3 font-mono tabular-nums">WAR</th>
                </tr>
              </thead>
              <tbody>
                {pitching.map((r) => (
                  <tr
                    key={`${r.id}-pit`}
                    className="border-b border-gray-800/80 text-gray-200"
                  >
                    <td className="py-2 px-3 font-mono">{r.season}</td>
                    <td className="py-2 px-3 max-w-[140px] truncate">
                      {r.team ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.ip, 1)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.era, 2)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.whip, 3)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {r.so ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {r.bb ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.fip, 2)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.war, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {fielding.length > 0 ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden">
          <div className="px-4 py-2 border-b border-gray-800 bg-gray-950/50 text-xs font-medium text-gray-400">
            Fielding
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[520px]">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-800">
                  <th className="py-2 px-3 font-medium">Year</th>
                  <th className="py-2 px-3 font-medium">Team</th>
                  <th className="py-2 px-3 font-medium">Pos</th>
                  <th className="py-2 px-3 font-mono tabular-nums">Inn</th>
                  <th className="py-2 px-3 font-mono tabular-nums">DRS</th>
                  <th className="py-2 px-3 font-mono tabular-nums">OAA</th>
                </tr>
              </thead>
              <tbody>
                {fielding.map((r) => (
                  <tr
                    key={`${r.id}-fld`}
                    className="border-b border-gray-800/80 text-gray-200"
                  >
                    <td className="py-2 px-3 font-mono">{r.season}</td>
                    <td className="py-2 px-3 max-w-[140px] truncate">
                      {r.team ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono">
                      {r.position ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {fmtSlash(r.inn, 1)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {r.drs ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {r.oaa ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PersonHeader({
  player,
}: {
  player: Record<string, unknown> | null;
}) {
  if (!player) return null;
  const fullName = String(player.fullName ?? "Player");
  const pos = player.primaryPosition as { abbreviation?: string } | undefined;
  const team = player.currentTeam as { name?: string } | undefined;
  const position = pos?.abbreviation ?? "—";
  const teamName = team?.name ?? "—";

  return (
    <header className="space-y-2 border-b border-gray-800 pb-6">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
        {teamName}
      </p>
      <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-white">
        {fullName}
      </h1>
      <p className="text-sm text-gray-400">
        Position{" "}
        <span className="font-mono text-gray-200">{position}</span>
      </p>
    </header>
  );
}

function HittingTable({
  season,
  stats,
}: {
  season: number;
  stats: NonNullable<PlayerProfileApiResponse["mlbStats"]>["hitting"];
}) {
  if (!stats) {
    return (
      <p className="text-sm text-gray-500">
        No season hitting splits in MLB Stats API for {season}.
      </p>
    );
  }
  const rows: { label: string; value: string }[] = [
    { label: "H", value: stats.hits != null ? String(stats.hits) : "—" },
    { label: "HR", value: stats.homeRuns != null ? String(stats.homeRuns) : "—" },
    { label: "RBI", value: stats.rbi != null ? String(stats.rbi) : "—" },
    { label: "AVG", value: stats.avg ?? "—" },
    { label: "OPS", value: stats.ops ?? "—" },
  ];

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 bg-gray-950/50">
        <h2 className="text-sm font-semibold text-white">
          Traditional · {season} batting
        </h2>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.label}
              className="border-t border-gray-800/80 first:border-t-0"
            >
              <th
                scope="row"
                className="py-3 px-4 text-left font-medium text-gray-400 w-1/3"
              >
                {r.label}
              </th>
              <td className="py-3 px-4 text-right font-mono text-white tabular-nums">
                {r.value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PitchingTable({
  season,
  stats,
}: {
  season: number;
  stats: NonNullable<PlayerProfileApiResponse["mlbStats"]>["pitching"];
}) {
  if (!stats) {
    return (
      <p className="text-sm text-gray-500">
        No season pitching splits in MLB Stats API for {season}.
      </p>
    );
  }
  const k = stats.strikeOuts != null ? String(stats.strikeOuts) : "—";
  const bb = stats.baseOnBalls != null ? String(stats.baseOnBalls) : "—";
  const rows: { label: string; value: string }[] = [
    { label: "ERA", value: stats.era ?? "—" },
    { label: "K", value: k },
    { label: "BB", value: bb },
    { label: "WHIP", value: stats.whip ?? "—" },
  ];

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 bg-gray-950/50">
        <h2 className="text-sm font-semibold text-white">
          Traditional · {season} pitching
        </h2>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.label}
              className="border-t border-gray-800/80 first:border-t-0"
            >
              <th
                scope="row"
                className="py-3 px-4 text-left font-medium text-gray-400 w-1/3"
              >
                {r.label}
              </th>
              <td className="py-3 px-4 text-right font-mono text-white tabular-nums">
                {r.value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatCard({
  label,
  display,
  tier,
}: {
  label: string;
  display: string;
  tier: StatTier | null;
}) {
  const tierLabel =
    tier === "elite"
      ? "Elite"
      : tier === "average"
        ? "Average"
        : tier === "below"
          ? "Below avg"
          : null;

  return (
    <div
      className={`rounded-xl border px-4 py-4 transition-colors ${tierClass(tier)}`}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {label}
      </p>
      <p className="mt-2 text-2xl font-bold tabular-nums tracking-tight">
        {display}
      </p>
      {tierLabel ? (
        <p className="mt-1 text-xs text-gray-400">{tierLabel}</p>
      ) : null}
    </div>
  );
}

function PitchesTable({ pitches }: { pitches: StatcastPitch[] }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-x-auto">
      <div className="px-4 py-3 border-b border-gray-800 bg-gray-950/50 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-white">
          Last 10 pitches / batted balls
        </h2>
        <p className="text-xs text-gray-500">Most recent by ingest time</p>
      </div>
      <table className="min-w-full text-xs sm:text-sm">
        <thead>
          <tr className="text-left text-gray-500 border-b border-gray-800">
            <th className="py-2 px-3 font-medium">Date</th>
            <th className="py-2 px-3 font-medium">Pitch</th>
            <th className="py-2 px-3 font-medium">Velo</th>
            <th className="py-2 px-3 font-medium hidden sm:table-cell">
              LA
            </th>
            <th className="py-2 px-3 font-medium hidden sm:table-cell">
              EV
            </th>
            <th className="py-2 px-3 font-medium">Event</th>
          </tr>
        </thead>
        <tbody>
          {pitches.map((p) => (
            <tr
              key={p.id}
              className="border-b border-gray-800/80 last:border-0 text-gray-200"
            >
              <td className="py-2 px-3 whitespace-nowrap font-mono text-gray-400">
                {p.game_date ?? "—"}
              </td>
              <td className="py-2 px-3">
                {p.pitch_name ?? p.pitch_type ?? "—"}
              </td>
              <td className="py-2 px-3 font-mono tabular-nums">
                {p.release_speed != null ? `${p.release_speed.toFixed(1)}` : "—"}
              </td>
              <td className="py-2 px-3 font-mono tabular-nums hidden sm:table-cell">
                {p.launch_angle != null ? `${p.launch_angle.toFixed(0)}°` : "—"}
              </td>
              <td className="py-2 px-3 font-mono tabular-nums hidden sm:table-cell">
                {p.launch_speed != null ? `${p.launch_speed.toFixed(1)}` : "—"}
              </td>
              <td className="py-2 px-3 max-w-[140px] sm:max-w-xs truncate text-gray-300">
                {p.events ?? p.description ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PlayerProfilePage() {
  const params = useParams();
  const id = params.id as string | undefined;

  const [profile, setProfile] = useState<PlayerProfileApiResponse | null>(null);
  const [pitches, setPitches] = useState<StatcastPitch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [profRes, pitRes] = await Promise.all([
        fetch(`/api/players/${id}`),
        fetch(`/api/players/${id}/pitches`),
      ]);

      if (!profRes.ok) {
        if (profRes.status === 404) {
          setError("Player not found.");
        } else {
          setError("Could not load this player profile.");
        }
        setProfile(null);
        setPitches([]);
        return;
      }

      const profJson = (await profRes.json()) as PlayerProfileApiResponse & {
        error?: string;
      };
      if (profJson.error) {
        setError(profJson.error);
        setProfile(null);
        setPitches([]);
        return;
      }
      setProfile(profJson);

      if (pitRes.ok) {
        const pitJson = (await pitRes.json()) as PlayerProfilePitchesApiResponse;
        setPitches(pitJson.pitches ?? []);
      } else {
        setPitches([]);
      }
    } catch {
      setError("Something went wrong while loading the profile.");
      setProfile(null);
      setPitches([]);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const season = profile?.mlbStats?.season ?? new Date().getFullYear();
  const sc = profile?.statcastBatting;
  const ev = sc?.avg_exit_velocity != null ? Number(sc.avg_exit_velocity) : null;
  const barrelPct = normalizePercent(
    sc?.barrel_rate != null ? Number(sc.barrel_rate) : null,
  );
  const hardPct = normalizePercent(
    sc?.hard_hit_rate != null ? Number(sc.hard_hit_rate) : null,
  );
  const xw = sc?.xwoba != null ? Number(sc.xwoba) : null;
  const sprint = sc?.sprint_speed != null ? Number(sc.sprint_speed) : null;

  const topPitches = pitches.slice(0, 10);

  const primaryCode = profile
    ? (
        profile.player?.primaryPosition as { code?: string } | undefined
      )?.code
    : undefined;
  const isPitcherPrimary =
    profile?.mlbStats?.isPitcherPrimary ?? primaryCode === "1";

  return (
    <div className="max-w-6xl mx-auto space-y-10">
      <p className="text-xs font-black tracking-tight">
        <span className="text-red-500">WAR</span>
        <span className="text-white">room</span>
      </p>
      <nav className="text-sm">
        <Link
          href="/players"
          className="text-red-400 hover:text-red-300 transition-colors"
        >
          ← Players
        </Link>
      </nav>

      {loading ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 py-20 flex flex-col items-center justify-center gap-3">
          <div className="h-10 w-10 rounded-full border-2 border-red-500 border-t-transparent animate-spin" />
          <p className="text-sm text-gray-500">Loading profile…</p>
        </div>
      ) : null}

      {!loading && error ? (
        <div
          className="rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-3 text-red-200 text-sm"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {!loading && !error && profile ? (
        <>
          <PersonHeader player={profile.player} />

          {profile.supabasePlayer &&
          supabaseBioHasDisplayData(profile.supabasePlayer) ? (
            <DatabaseBioPanel row={profile.supabasePlayer} />
          ) : null}

          <HistoricalSeasonsSection
            batting={profile.historicalBatting ?? []}
            pitching={profile.historicalPitching ?? []}
            fielding={profile.historicalFielding ?? []}
          />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8">
            <section className="space-y-3">
              <h2 className="sr-only">MLB season stats</h2>
              {isPitcherPrimary ? (
                <PitchingTable
                  season={season}
                  stats={profile.mlbStats?.pitching ?? null}
                />
              ) : (
                <HittingTable
                  season={season}
                  stats={profile.mlbStats?.hitting ?? null}
                />
              )}
            </section>

            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-gray-400">
                Statcast · {season}
              </h2>
              {!sc ? (
                <p className="text-sm text-gray-500 rounded-xl border border-gray-800 bg-gray-900/30 px-4 py-8 text-center">
                  No Statcast batting row for this player in {season}.
                </p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <StatCard
                    label="Avg exit velo"
                    display={ev != null ? `${ev.toFixed(1)} mph` : "—"}
                    tier={tierExitVelo(ev)}
                  />
                  <StatCard
                    label="Barrel rate"
                    display={formatPercentish(
                      sc.barrel_rate != null ? Number(sc.barrel_rate) : null,
                    )}
                    tier={tierBarrel(barrelPct)}
                  />
                  <StatCard
                    label="Hard-hit rate"
                    display={formatPercentish(
                      sc.hard_hit_rate != null ? Number(sc.hard_hit_rate) : null,
                    )}
                    tier={tierHardHit(hardPct)}
                  />
                  <StatCard
                    label="xwOBA"
                    display={xw != null ? xw.toFixed(3) : "—"}
                    tier={tierXwoba(xw)}
                  />
                  <StatCard
                    label="Sprint speed"
                    display={
                      sprint != null ? `${sprint.toFixed(1)} ft/s` : "—"
                    }
                    tier={tierSprint(sprint)}
                  />
                </div>
              )}
            </section>
          </div>

          {topPitches.length > 0 ? (
            <PitchesTable pitches={topPitches} />
          ) : (
            <p className="text-sm text-gray-500 text-center py-8 border border-dashed border-gray-800 rounded-xl">
              No pitch or batted-ball rows in Supabase for this player yet.
            </p>
          )}
        </>
      ) : null}
    </div>
  );
}
