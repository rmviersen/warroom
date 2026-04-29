"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  TeamDetailApiResponse,
  TeamRosterPlayer,
  TeamRosterPositionGroup,
  TeamStatcastApiResponse,
} from "@/types";

const FILTER_OPTIONS: {
  value: "all" | TeamRosterPositionGroup;
  label: string;
}[] = [
  { value: "all", label: "All position groups" },
  { value: "pitchers", label: "Pitchers" },
  { value: "catchers", label: "Catchers" },
  { value: "infielders", label: "Infielders" },
  { value: "outfielders", label: "Outfielders" },
  { value: "dh", label: "Designated hitter" },
  { value: "other", label: "Other" },
];

function formatInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return String(n);
}

function TeamHeader({ team }: { team: Record<string, unknown> }) {
  const name = String(team.name ?? "Team");
  const league =
    (team.league as { name?: string } | undefined)?.name ?? "—";
  const division =
    (team.division as { name?: string } | undefined)?.name ?? "—";
  const venueRaw = team.venue;
  let venueName = "—";
  if (typeof venueRaw === "object" && venueRaw !== null && "name" in venueRaw) {
    venueName = String((venueRaw as { name?: string }).name ?? "—");
  } else if (typeof venueRaw === "string") {
    venueName = venueRaw;
  }

  return (
    <header className="space-y-3 border-b border-gray-800 pb-6">
      <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-white">
        {name}
      </h1>
      <dl className="grid gap-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-gray-500">League</dt>
          <dd className="text-gray-200">{league}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Division</dt>
          <dd className="text-gray-200">{division}</dd>
        </div>
        <div className="sm:col-span-1">
          <dt className="text-gray-500">Venue</dt>
          <dd className="text-gray-200">{venueName}</dd>
        </div>
      </dl>
    </header>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-t border-gray-800/90 py-2.5 first:border-t-0">
      <span className="text-gray-400">{label}</span>
      <span className="font-mono tabular-nums text-white">{value}</span>
    </div>
  );
}

type StatTier = "elite" | "average" | "below";

function normalizePercent(v: number | null | undefined): number | null {
  if (v == null || Number.isNaN(v)) return null;
  return v <= 1 ? v * 100 : v;
}

function tierAvgEv(mph: number | null): StatTier | null {
  if (mph == null) return null;
  if (mph > 89) return "elite";
  if (mph >= 86) return "average";
  return "below";
}

function tierMaxEv(mph: number | null): StatTier | null {
  if (mph == null) return null;
  if (mph > 92) return "elite";
  if (mph >= 88) return "average";
  return "below";
}

function tierBarrel(pct: number | null): StatTier | null {
  if (pct == null) return null;
  const p = normalizePercent(pct);
  if (p == null) return null;
  if (p > 8) return "elite";
  if (p >= 5) return "average";
  return "below";
}

function tierHardHit(pct: number | null): StatTier | null {
  if (pct == null) return null;
  const p = normalizePercent(pct);
  if (p == null) return null;
  if (p > 40) return "elite";
  if (p >= 35) return "average";
  return "below";
}

function tierXwoba(x: number | null): StatTier | null {
  if (x == null) return null;
  if (x > 0.32) return "elite";
  if (x >= 0.3) return "average";
  return "below";
}

function tierSprint(fps: number | null): StatTier | null {
  if (fps == null) return null;
  if (fps > 27) return "elite";
  if (fps >= 25) return "average";
  return "below";
}

function tierCardClass(tier: StatTier | null, neutral: boolean): string {
  if (neutral || !tier) {
    return "border-gray-800 bg-gray-900/40 text-gray-200";
  }
  if (tier === "elite") {
    return "border-emerald-600/50 bg-emerald-950/25 text-emerald-100";
  }
  if (tier === "average") {
    return "border-amber-600/40 bg-amber-950/20 text-amber-100";
  }
  return "border-red-800/50 bg-red-950/25 text-red-100";
}

function formatPercentDisplay(v: number | null): string {
  if (v == null) return "—";
  const p = normalizePercent(v);
  if (p == null) return "—";
  return `${p.toFixed(1)}%`;
}

function TeamStatcastSection({
  season,
  statcast,
  statcastError,
}: {
  season: number;
  statcast: TeamStatcastApiResponse | null;
  statcastError: boolean;
}) {
  if (statcastError) {
    return (
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
          Statcast · {season}
        </h2>
        <p className="text-sm text-amber-200/90 rounded-xl border border-amber-900/40 bg-amber-950/20 px-4 py-4">
          Statcast team metrics could not be loaded. Try again later.
        </p>
      </section>
    );
  }

  const ts = statcast?.teamStatcast;
  const hasData =
    statcast != null &&
    statcast.playerCount > 0 &&
    ts != null;

  if (!hasData) {
    return (
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
          Statcast · {season}
        </h2>
        <p className="text-sm text-gray-500 rounded-xl border border-gray-800 bg-gray-900/30 px-4 py-8 text-center">
          No Statcast data available for this team and season in your database.
        </p>
      </section>
    );
  }

  const nRoster = statcast?.playerCount ?? 0;
  const totalPa = ts!.total_pa;

  return (
    <section className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
          Statcast · {season}
        </h2>
        <p className="text-xs text-gray-500 text-right sm:text-left max-w-md">
          <span className="text-gray-400 font-mono">{nRoster}</span> player
          {nRoster === 1 ? "" : "s"} in{" "}
          <span className="text-gray-400">statcast_batting</span>
          {". "}
          {totalPa > 0 ? (
            <>
              Metrics use PA-weighted means (
              <span className="text-gray-400 font-mono">
                ΣPA = {totalPa.toLocaleString()}
              </span>
              ) where each row has <span className="text-gray-400">pa</span>;{" "}
              otherwise a simple mean across players.
            </>
          ) : (
            <>No <span className="text-gray-400">pa</span> values — using simple means.</>
          )}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        <div
          className={`rounded-xl border px-4 py-3 ${tierCardClass(tierAvgEv(ts!.avg_exit_velocity), false)}`}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Avg exit velocity
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums">
            {ts!.avg_exit_velocity != null
              ? `${ts!.avg_exit_velocity.toFixed(1)} mph`
              : "—"}
          </p>
        </div>
        <div
          className={`rounded-xl border px-4 py-3 ${tierCardClass(tierMaxEv(ts!.max_exit_velocity), false)}`}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Max exit velocity
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums">
            {ts!.max_exit_velocity != null
              ? `${ts!.max_exit_velocity.toFixed(1)} mph`
              : "—"}
          </p>
          <p className="mt-1 text-[10px] text-gray-500">Best single-player max on roster</p>
        </div>
        <div
          className={`rounded-xl border px-4 py-3 ${tierCardClass(null, true)}`}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Avg launch angle
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums">
            {ts!.avg_launch_angle != null
              ? `${ts!.avg_launch_angle.toFixed(1)}°`
              : "—"}
          </p>
        </div>
        <div
          className={`rounded-xl border px-4 py-3 ${tierCardClass(tierBarrel(ts!.barrel_rate), false)}`}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Barrel rate (avg)
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums">
            {formatPercentDisplay(ts!.barrel_rate)}
          </p>
        </div>
        <div
          className={`rounded-xl border px-4 py-3 ${tierCardClass(tierHardHit(ts!.hard_hit_rate), false)}`}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Hard-hit rate (avg)
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums">
            {formatPercentDisplay(ts!.hard_hit_rate)}
          </p>
        </div>
        <div
          className={`rounded-xl border px-4 py-3 ${tierCardClass(tierXwoba(ts!.avg_xwoba), false)}`}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            xwOBA (avg)
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums">
            {ts!.avg_xwoba != null ? ts!.avg_xwoba.toFixed(3) : "—"}
          </p>
        </div>
        <div
          className={`rounded-xl border px-4 py-3 sm:col-span-2 xl:col-span-1 ${tierCardClass(tierSprint(ts!.avg_sprint_speed), false)}`}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Sprint speed (avg)
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums">
            {ts!.avg_sprint_speed != null
              ? `${ts!.avg_sprint_speed.toFixed(1)} ft/s`
              : "—"}
          </p>
        </div>
      </div>

      {statcast!.topPlayers.length > 0 ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-x-auto">
          <h3 className="px-4 pt-4 pb-2 text-xs font-bold uppercase tracking-widest text-red-500/90">
            Top 5 on roster · avg exit velocity
          </h3>
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="border-t border-b border-gray-800 text-gray-500 text-xs uppercase">
                <th className="px-4 py-2 text-left font-medium">Player</th>
                <th className="px-4 py-2 text-right font-medium">PA</th>
                <th className="px-4 py-2 text-right font-medium">Avg EV</th>
                <th className="px-4 py-2 text-right font-medium">Barrel%</th>
                <th className="px-4 py-2 text-right font-medium">xwOBA</th>
              </tr>
            </thead>
            <tbody>
              {statcast!.topPlayers.map((p) => (
                <tr
                  key={p.player_id}
                  className="border-b border-gray-800/80 hover:bg-gray-800/20"
                >
                  <td className="px-4 py-2.5">
                    <Link
                      href={`/players/${p.player_id}`}
                      className="text-white font-medium hover:text-red-400 transition-colors"
                    >
                      {p.player_name ?? "—"}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums text-gray-400">
                    {p.pa != null ? String(p.pa) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums text-gray-200">
                    {p.avg_exit_velocity != null
                      ? `${p.avg_exit_velocity.toFixed(1)}`
                      : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums text-gray-300">
                    {formatPercentDisplay(p.barrel_rate)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums text-gray-300">
                    {p.xwoba != null ? p.xwoba.toFixed(3) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

export default function TeamDetailPage() {
  const params = useParams();
  const id = params.id as string | undefined;

  const [data, setData] = useState<TeamDetailApiResponse | null>(null);
  const [statcast, setStatcast] = useState<TeamStatcastApiResponse | null>(
    null,
  );
  const [statcastError, setStatcastError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [groupFilter, setGroupFilter] = useState<
    "all" | TeamRosterPositionGroup
  >("all");

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    setStatcastError(false);
    const year = new Date().getFullYear();
    try {
      const [teamRes, scRes] = await Promise.all([
        fetch(`/api/teams/${id}`),
        fetch(`/api/teams/${id}/statcast?season=${year}`),
      ]);

      if (scRes.ok) {
        setStatcast((await scRes.json()) as TeamStatcastApiResponse);
        setStatcastError(false);
      } else {
        setStatcast(null);
        setStatcastError(true);
      }

      if (teamRes.status === 404) {
        setError("Team not found.");
        setData(null);
        setStatcast(null);
        return;
      }
      if (!teamRes.ok) {
        const body = (await teamRes.json().catch(() => ({}))) as {
          error?: string;
        };
        setError(body.error ?? "Could not load team.");
        setData(null);
        return;
      }
      const json = (await teamRes.json()) as TeamDetailApiResponse;
      setData(json);
    } catch {
      setError("Something went wrong while loading this team.");
      setData(null);
      setStatcast(null);
      setStatcastError(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const rosterFiltered = useMemo(() => {
    if (!data?.roster) return [];
    if (groupFilter === "all") return data.roster;
    return data.roster.filter((r) => r.positionGroup === groupFilter);
  }, [data, groupFilter]);

  const season = data?.stats?.season ?? new Date().getFullYear();
  const statcastSeason =
    statcast?.teamStatcast?.season ?? season;
  const hit = data?.stats?.hitting;
  const pit = data?.stats?.pitching;

  return (
    <div className="max-w-5xl mx-auto space-y-10">
      <p className="text-xs font-black tracking-tight">
        <span className="text-red-500">WAR</span>
        <span className="text-white">room</span>
      </p>
      <nav className="text-sm">
        <Link
          href="/teams"
          className="text-red-400 hover:text-red-300 transition-colors"
        >
          ← Teams
        </Link>
      </nav>

      {loading ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 py-20 flex flex-col items-center justify-center gap-3">
          <div className="h-10 w-10 rounded-full border-2 border-red-500 border-t-transparent animate-spin" />
          <p className="text-sm text-gray-500">Loading team…</p>
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

      {!loading && !error && data ? (
        <>
          <TeamHeader team={data.team} />

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
              Season {season} · team totals
            </h2>
            {!data.stats ? (
              <p className="text-sm text-gray-500 rounded-xl border border-gray-800 bg-gray-900/30 px-4 py-6">
                Team season stats are unavailable from the MLB API right now.
              </p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 lg:gap-6">
                <div className="rounded-xl border border-gray-800 bg-gray-900/45 px-4 py-3">
                  <h3 className="text-xs font-bold uppercase tracking-widest text-red-500/90 mb-1">
                    Hitting
                  </h3>
                  <div className="text-sm">
                    <StatRow label="AVG" value={hit?.avg ?? "—"} />
                    <StatRow label="OPS" value={hit?.ops ?? "—"} />
                    <StatRow label="HR" value={formatInt(hit?.homeRuns)} />
                    <StatRow label="RBI" value={formatInt(hit?.rbi)} />
                    <StatRow label="Runs" value={formatInt(hit?.runs)} />
                  </div>
                </div>
                <div className="rounded-xl border border-gray-800 bg-gray-900/45 px-4 py-3">
                  <h3 className="text-xs font-bold uppercase tracking-widest text-red-500/90 mb-1">
                    Pitching
                  </h3>
                  <div className="text-sm">
                    <StatRow label="ERA" value={pit?.era ?? "—"} />
                    <StatRow label="WHIP" value={pit?.whip ?? "—"} />
                    <StatRow label="K" value={formatInt(pit?.strikeOuts)} />
                    <StatRow label="BB" value={formatInt(pit?.baseOnBalls)} />
                    <StatRow label="Saves" value={formatInt(pit?.saves)} />
                  </div>
                </div>
              </div>
            )}
          </section>

          <TeamStatcastSection
            season={statcastSeason}
            statcast={statcast}
            statcastError={statcastError}
          />

          <section className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
              <h2 className="text-lg font-bold text-white">Active roster</h2>
              <div>
                <label
                  htmlFor="roster-group"
                  className="sr-only"
                >
                  Filter by position group
                </label>
                <select
                  id="roster-group"
                  value={groupFilter}
                  onChange={(e) =>
                    setGroupFilter(
                      e.target.value as "all" | TeamRosterPositionGroup,
                    )
                  }
                  className="rounded-lg bg-gray-900 border border-gray-800 text-white text-sm px-3 py-2 min-w-[200px] focus:outline-none focus:ring-2 focus:ring-red-500/40"
                >
                  {FILTER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-x-auto">
              <table className="w-full text-sm text-left min-w-[640px]">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-500 text-xs uppercase tracking-wider">
                    <th className="px-3 py-3 font-medium w-16">#</th>
                    <th className="px-3 py-3 font-medium">Player</th>
                    <th className="px-3 py-3 font-medium">Pos</th>
                    <th className="px-3 py-3 font-medium">B</th>
                    <th className="px-3 py-3 font-medium">T</th>
                  </tr>
                </thead>
                <tbody>
                  {rosterFiltered.length === 0 ? (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-3 py-10 text-center text-gray-500"
                      >
                        No players in this group.
                      </td>
                    </tr>
                  ) : (
                    rosterFiltered.map((p: TeamRosterPlayer) => (
                      <tr
                        key={p.playerId}
                        className="border-b border-gray-800/80 hover:bg-gray-800/25"
                      >
                        <td className="px-3 py-2.5 font-mono text-gray-400 tabular-nums">
                          {p.jerseyNumber ?? "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <Link
                            href={`/players/${p.playerId}`}
                            className="text-white font-medium hover:text-red-400 transition-colors"
                          >
                            {p.fullName}
                          </Link>
                        </td>
                        <td className="px-3 py-2.5 text-gray-300">
                          {p.positionAbbrev ?? p.positionName ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-gray-400">
                          {p.batSide ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-gray-400">
                          {p.pitchHand ?? "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
