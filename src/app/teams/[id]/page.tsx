"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import BaseballFieldView from "@/components/ui/BaseballFieldView";
import TeamProfileBanner from "@/components/ui/TeamProfileBanner";
import type {
  TeamBannerApiResponse,
  TeamDetailApiResponse,
  TeamPositionWprApiResponse,
  TeamPositionWprPlayerRow,
  TeamPositionWprPlayersApiResponse,
  TeamPositionWprRow,
  TeamRosterPlayer,
  TeamRosterPositionGroup,
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

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-t border-[#f0f4f9] py-2.5 first:border-t-0">
      <span className="text-[#7a8fa8]">{label}</span>
      <span className="font-mono tabular-nums text-[#1e3050]">{value}</span>
    </div>
  );
}

export default function TeamDetailPage() {
  const params = useParams();
  const id = params.id as string | undefined;
  const teamId = id ? Number.parseInt(id, 10) : NaN;

  const [data, setData] = useState<TeamDetailApiResponse | null>(null);
  const [banner, setBanner] = useState<TeamBannerApiResponse | null>(null);
  const [positionWpr, setPositionWpr] = useState<TeamPositionWprRow[]>([]);
  const [positionPlayers, setPositionPlayers] = useState<
    TeamPositionWprPlayerRow[]
  >([]);
  const [positionWprError, setPositionWprError] = useState(false);
  const [bannerError, setBannerError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [groupFilter, setGroupFilter] = useState<
    "all" | TeamRosterPositionGroup
  >("all");

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    setBannerError(false);
    setPositionWprError(false);
    setPositionWpr([]);
    setPositionPlayers([]);

    try {
      const teamRes = await fetch(`/api/teams/${id}`, { cache: "no-store" });

      if (teamRes.status === 404) {
        setError("Team not found.");
        setData(null);
        setBanner(null);
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

      const season = json.stats?.season ?? new Date().getFullYear();

      const [bannerRes, wprRes, wprPlayersRes] = await Promise.all([
        fetch(`/api/teams/${id}/banner?season=${season}`, { cache: "no-store" }),
        fetch(`/api/teams/${id}/position-wpr?season=${season}`, {
          cache: "no-store",
        }),
        fetch(`/api/teams/${id}/position-wpr/players?season=${season}`, {
          cache: "no-store",
        }),
      ]);

      if (bannerRes.ok) {
        setBanner((await bannerRes.json()) as TeamBannerApiResponse);
        setBannerError(false);
      } else {
        setBanner(null);
        setBannerError(true);
      }

      if (wprRes.ok) {
        const wprJson = (await wprRes.json()) as TeamPositionWprApiResponse;
        setPositionWpr(wprJson.positions ?? []);
        setPositionWprError(false);
      } else {
        setPositionWpr([]);
        setPositionWprError(true);
      }

      if (wprPlayersRes.ok) {
        const playersJson =
          (await wprPlayersRes.json()) as TeamPositionWprPlayersApiResponse;
        setPositionPlayers(playersJson.players ?? []);
      } else {
        setPositionPlayers([]);
      }

    } catch {
      setError("Something went wrong while loading this team.");
      setData(null);
      setBanner(null);
      setPositionWpr([]);
      setPositionPlayers([]);
      setPositionWprError(true);
      setBannerError(true);
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

  const playersByPosition = useMemo(() => {
    const map = new Map<string, TeamPositionWprPlayerRow[]>();
    for (const player of positionPlayers) {
      const list = map.get(player.position) ?? [];
      list.push(player);
      map.set(player.position, list);
    }
    return map;
  }, [positionPlayers]);

  const season = data?.stats?.season ?? banner?.season ?? new Date().getFullYear();
  const hit = data?.stats?.hitting;
  const pit = data?.stats?.pitching;

  return (
    <div className="space-y-6">
      <p className="text-xs font-black tracking-tight">
        <span className="text-[#b8922a]">WAR</span>
        <span className="text-[#0f2044]">room</span>
      </p>
      <nav className="text-sm">
        <Link
          href="/teams"
          className="text-[#1e3a6b] hover:text-[#b8922a] transition-colors"
        >
          ← Teams
        </Link>
      </nav>

      {loading ? (
        <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] py-20 flex flex-col items-center justify-center gap-3">
          <div className="h-10 w-10 rounded-full border-2 border-[#1e3a6b] border-t-transparent animate-spin" />
          <p className="text-sm text-[#7a8fa8]">Loading team…</p>
        </div>
      ) : null}

      {!loading && error ? (
        <div
          className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-red-800 text-sm"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {!loading && !error && data && Number.isFinite(teamId) ? (
        <>
          <TeamProfileBanner
            team={data.team}
            teamId={teamId}
            banner={bannerError ? null : banner}
            season={season}
          />

          {bannerError ? (
            <p
              className="text-sm text-amber-900 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3"
              role="status"
            >
              Ranked team metrics could not be loaded. Basic season totals below
              may still be available.
            </p>
          ) : null}

          <BaseballFieldView
            season={season}
            positions={positionWpr}
            playersByPosition={playersByPosition}
            loadError={positionWprError}
          />

          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-[#0f2044]">
              Season {season} · team totals
            </h2>
            {!data.stats ? (
              <p className="text-sm text-[#7a8fa8] rounded-xl border border-[#d0daea] bg-[#f4f7fb] px-4 py-6">
                Team season stats are unavailable from the MLB API right now.
              </p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-[#d0daea] bg-white px-4 py-3">
                  <h3 className="text-xs font-bold uppercase tracking-widest text-[#1e3a6b] mb-1">
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
                <div className="rounded-xl border border-[#d0daea] bg-white px-4 py-3">
                  <h3 className="text-xs font-bold uppercase tracking-widest text-[#1e3a6b] mb-1">
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

          <section className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
              <h2 className="text-lg font-bold text-[#0f2044]">Active roster</h2>
              <div>
                <label htmlFor="roster-group" className="sr-only">
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
                  className="rounded-lg bg-white border border-[#d0daea] text-[#0f2044] text-sm px-3 py-2 min-w-[200px] focus:outline-none focus:ring-2 focus:ring-[#1e3a6b]/30"
                >
                  {FILTER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="rounded-xl border border-[#d0daea] bg-white overflow-x-auto">
              <table className="w-full text-sm text-left min-w-[640px]">
                <thead>
                  <tr className="border-b border-[#f0f4f9] bg-[#f4f7fb] text-[#7a8fa8] text-xs uppercase tracking-wider">
                    <th className="px-3 py-3 font-medium w-16">#</th>
                    <th className="px-3 py-3 font-medium">Player</th>
                    <th className="px-3 py-3 font-medium">Pos</th>
                    <th className="px-3 py-3 font-medium">B</th>
                    <th className="px-3 py-3 font-medium">T</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f0f4f9]">
                  {rosterFiltered.length === 0 ? (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-3 py-10 text-center text-[#7a8fa8]"
                      >
                        No players in this group.
                      </td>
                    </tr>
                  ) : (
                    rosterFiltered.map((p: TeamRosterPlayer) => (
                      <tr
                        key={p.playerId}
                        className="hover:bg-[#f4f7fb] transition-colors"
                      >
                        <td className="px-3 py-2.5 font-mono text-[#7a8fa8] tabular-nums">
                          {p.jerseyNumber ?? "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <Link
                            href={`/players/${p.playerId}`}
                            className="text-[#1e3a6b] font-medium hover:underline"
                          >
                            {p.fullName}
                          </Link>
                        </td>
                        <td className="px-3 py-2.5 text-[#1e3050]">
                          {p.positionAbbrev ?? p.positionName ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[#7a8fa8]">
                          {p.batSide ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[#7a8fa8]">
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
