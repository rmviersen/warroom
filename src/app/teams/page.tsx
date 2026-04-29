"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { Team } from "@/types";

const AL_ID = 103;
const NL_ID = 104;

function divisionRank(name: string | null): number {
  if (!name) return 99;
  if (name.includes("East")) return 0;
  if (name.includes("Central")) return 1;
  if (name.includes("West")) return 2;
  return 3;
}

function groupTeams(teams: Team[]) {
  const al = teams.filter(
    (t) =>
      t.league_id === AL_ID ||
      (t.league?.toLowerCase().includes("american") ?? false),
  );
  const nl = teams.filter(
    (t) =>
      t.league_id === NL_ID ||
      (t.league?.toLowerCase().includes("national") ?? false),
  );

  const byDivision = (list: Team[]) => {
    const map = new Map<string, Team[]>();
    for (const t of list) {
      const div = t.division ?? "Other";
      if (!map.has(div)) map.set(div, []);
      map.get(div)!.push(t);
    }
    const keys = [...map.keys()].sort(
      (a, b) => divisionRank(a) - divisionRank(b),
    );
    return keys.map((div) => ({
      division: div,
      teams: (map.get(div) ?? []).sort((a, b) =>
        (a.name ?? "").localeCompare(b.name ?? ""),
      ),
    }));
  };

  return {
    alGroups: byDivision(al),
    nlGroups: byDivision(nl),
  };
}

function LoadingGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-36 rounded-xl border border-gray-800 bg-gray-900/40 animate-pulse"
        />
      ))}
    </div>
  );
}

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { alGroups, nlGroups } = useMemo(() => groupTeams(teams), [teams]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/teams");
      if (!res.ok) throw new Error("Could not load teams.");
      const data = (await res.json()) as { teams?: Team[] };
      setTeams(data.teams ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setTeams([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <h1 className="text-3xl sm:text-4xl font-black tracking-tight">
          <span className="text-red-500">WAR</span>
          <span className="text-white">room</span>
          <span className="text-gray-400 font-semibold text-2xl sm:text-3xl ml-2">
            Teams
          </span>
        </h1>
        <p className="text-gray-500 max-w-2xl">
          All 30 clubs, grouped by league and division—aligned with your
          database team dimensions.
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
        <LoadingGrid />
      ) : (
        <div className="space-y-12">
          <LeagueSection title="American League" groups={alGroups} />
          <LeagueSection title="National League" groups={nlGroups} />
        </div>
      )}
    </div>
  );
}

function LeagueSection({
  title,
  groups,
}: {
  title: string;
  groups: { division: string; teams: Team[] }[];
}) {
  return (
    <section className="space-y-6">
      <h2 className="text-xl font-bold text-white border-b border-gray-800 pb-2 flex items-center gap-2">
        <span className="h-1 w-8 rounded-full bg-red-500" />
        {title}
      </h2>
      {groups.map(({ division, teams: divTeams }) => (
        <div key={division} className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-red-500/90">
            {division}
          </h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {divTeams.map((team) => (
              <Link
                key={team.id}
                href={`/teams/${team.id}`}
                className="group relative block rounded-xl border border-gray-800 bg-gray-900/50 p-4 hover:border-red-900/40 hover:bg-gray-900/80 hover:shadow-lg hover:shadow-red-950/20 transition-all duration-200"
              >
                <p className="text-white font-semibold leading-snug pr-24">
                  {team.name ?? "—"}
                </p>
                <p className="text-sm text-gray-400 mt-1">
                  {team.location_name ?? "—"}
                  {team.team_name ? ` · ${team.team_name}` : ""}
                </p>
                <dl className="mt-3 grid gap-1 text-xs text-gray-500">
                  <div className="flex justify-between gap-2">
                    <dt>Abbrev.</dt>
                    <dd className="text-gray-300 font-mono">
                      {team.abbreviation ?? "—"}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt>Division</dt>
                    <dd className="text-gray-300">{team.division ?? "—"}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt>Venue</dt>
                    <dd className="text-gray-300 text-right">
                      {team.venue ?? "—"}
                    </dd>
                  </div>
                </dl>
                <span className="pointer-events-none absolute top-4 right-4 text-xs font-semibold text-red-400 opacity-0 translate-x-1 transition-all duration-200 group-hover:opacity-100 group-hover:translate-x-0">
                  View Team →
                </span>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
