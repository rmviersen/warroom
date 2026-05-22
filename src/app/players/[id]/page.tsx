"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import BatterStatcastSection from "@/components/ui/BatterStatcastSection";
import PitcherStatcastSection from "@/components/ui/PitcherStatcastSection";
import type {
  PlayerBattingSeasonRow,
  PlayerFieldingSeasonRow,
  PlayerPitchingSeasonRow,
  PlayerProfileApiResponse,
  PlayerProfilePitchesApiResponse,
  PlayerRow,
  StatcastPitch,
} from "@/types";

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
    <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] overflow-hidden">
      <div className="px-4 py-3 border-b border-[#d0daea] bg-[#f4f7fb]">
        <h2 className="text-sm font-semibold text-[#0f2044]">Bio · database</h2>
        <p className="text-xs text-[#7a8fa8] mt-0.5">
          From your Supabase players row (historical / roster cache).
        </p>
      </div>
      <table className="w-full text-sm">
        <tbody className="divide-y divide-[#f0f4f9]">
          {rows.map((r) => (
            <tr key={r.label}>
              <th
                scope="row"
                className="py-3 px-4 text-left font-medium text-[#7a8fa8] w-2/5"
              >
                {r.label}
              </th>
              <td className="py-3 px-4 text-right font-mono tabular-nums text-[#1e3050]">
                {r.value}
              </td>
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
        <h2 className="text-sm font-semibold text-[#0f2044]">
          Historical seasons · database
        </h2>
        <p className="text-xs text-[#7a8fa8] mt-0.5">
          Season totals from Supabase (newest year first).
        </p>
      </div>

      {batting.length > 0 ? (
        <div className="rounded-xl border border-[#d0daea] bg-white overflow-hidden">
          <div className="px-4 py-2 border-b border-[#d0daea] bg-[#f4f7fb] text-xs font-semibold text-[#0f2044]">
            Batting
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[640px]">
              <thead>
                <tr className="text-left text-[#7a8fa8] bg-[#f4f7fb] border-b border-[#f0f4f9]">
                  <th className="py-2 px-3 font-medium text-[#7a8fa8]">Year</th>
                  <th className="py-2 px-3 font-medium text-[#7a8fa8]">Team</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">PA</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">AVG</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">OBP</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">SLG</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">OPS</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">HR</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">wRC+</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-semibold text-[#b8922a]">bWPR</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f0f4f9] text-[#1e3050]">
                {batting.map((r) => (
                  <tr
                    key={`${r.id}-bat`}
                    className="bg-white hover:bg-[#f4f7fb] transition-colors"
                  >
                    <td className="py-2 px-3 font-mono tabular-nums">{r.season}</td>
                    <td className="py-2 px-3 max-w-[140px] truncate text-[#7a8fa8]">
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
                      {fmtSlash(r.bwpr, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {pitching.length > 0 ? (
        <div className="rounded-xl border border-[#d0daea] bg-white overflow-hidden">
          <div className="px-4 py-2 border-b border-[#d0daea] bg-[#f4f7fb] text-xs font-semibold text-[#0f2044]">
            Pitching
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[600px]">
              <thead>
                <tr className="text-left text-[#7a8fa8] bg-[#f4f7fb] border-b border-[#f0f4f9]">
                  <th className="py-2 px-3 font-medium text-[#7a8fa8]">Year</th>
                  <th className="py-2 px-3 font-medium text-[#7a8fa8]">Team</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">IP</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">ERA</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">WHIP</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">SO</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">BB</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">FIP</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-semibold text-[#b8922a]">pWPR</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f0f4f9] text-[#1e3050]">
                {pitching.map((r) => (
                  <tr
                    key={`${r.id}-pit`}
                    className="bg-white hover:bg-[#f4f7fb] transition-colors"
                  >
                    <td className="py-2 px-3 font-mono tabular-nums">{r.season}</td>
                    <td className="py-2 px-3 max-w-[140px] truncate text-[#7a8fa8]">
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
                      {fmtSlash(r.pwpr, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {fielding.length > 0 ? (
        <div className="rounded-xl border border-[#d0daea] bg-white overflow-hidden">
          <div className="px-4 py-2 border-b border-[#d0daea] bg-[#f4f7fb] text-xs font-semibold text-[#0f2044]">
            Fielding
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[520px]">
              <thead>
                <tr className="text-left text-[#7a8fa8] bg-[#f4f7fb] border-b border-[#f0f4f9]">
                  <th className="py-2 px-3 font-medium text-[#7a8fa8]">Year</th>
                  <th className="py-2 px-3 font-medium text-[#7a8fa8]">Team</th>
                  <th className="py-2 px-3 font-medium text-[#7a8fa8]">Pos</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">Inn</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">DRS</th>
                  <th className="py-2 px-3 font-mono tabular-nums font-medium text-[#7a8fa8]">OAA</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f0f4f9] text-[#1e3050]">
                {fielding.map((r) => (
                  <tr
                    key={`${r.id}-fld`}
                    className="bg-white hover:bg-[#f4f7fb] transition-colors"
                  >
                    <td className="py-2 px-3 font-mono tabular-nums">{r.season}</td>
                    <td className="py-2 px-3 max-w-[140px] truncate text-[#7a8fa8]">
                      {r.team ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono text-[#7a8fa8]">
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
    <header className="space-y-2 border-b border-[#d0daea] pb-6">
      <p className="text-xs font-medium uppercase tracking-wider text-[#7a8fa8]">
        {teamName}
      </p>
      <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-[#0f2044]">
        {fullName}
      </h1>
      <p className="text-sm text-[#7a8fa8]">
        Position{" "}
        <span className="font-mono tabular-nums text-[#7a8fa8]">{position}</span>
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
      <p className="text-sm text-[#7a8fa8]">
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
    <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] overflow-hidden">
      <div className="px-4 py-3 border-b border-[#d0daea] bg-[#f4f7fb]">
        <h2 className="text-sm font-semibold text-[#0f2044]">
          Traditional · {season} batting
        </h2>
      </div>
      <table className="w-full text-sm">
        <tbody className="divide-y divide-[#f0f4f9]">
          {rows.map((r) => (
            <tr key={r.label}>
              <th
                scope="row"
                className="py-3 px-4 text-left font-medium text-[#7a8fa8] w-1/3"
              >
                {r.label}
              </th>
              <td className="py-3 px-4 text-right font-mono tabular-nums text-[#1e3050]">
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
      <p className="text-sm text-[#7a8fa8]">
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
    <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] overflow-hidden">
      <div className="px-4 py-3 border-b border-[#d0daea] bg-[#f4f7fb]">
        <h2 className="text-sm font-semibold text-[#0f2044]">
          Traditional · {season} pitching
        </h2>
      </div>
      <table className="w-full text-sm">
        <tbody className="divide-y divide-[#f0f4f9]">
          {rows.map((r) => (
            <tr key={r.label}>
              <th
                scope="row"
                className="py-3 px-4 text-left font-medium text-[#7a8fa8] w-1/3"
              >
                {r.label}
              </th>
              <td className="py-3 px-4 text-right font-mono tabular-nums text-[#1e3050]">
                {r.value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PitchesTable({ pitches }: { pitches: StatcastPitch[] }) {
  return (
    <div className="rounded-xl border border-[#d0daea] bg-white overflow-x-auto">
      <div className="px-4 py-3 border-b border-[#d0daea] bg-[#f4f7fb] flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-[#0f2044]">
          Last 10 pitches / batted balls
        </h2>
        <p className="text-xs text-[#7a8fa8]">Most recent by ingest time</p>
      </div>
      <table className="min-w-full text-xs sm:text-sm">
        <thead>
          <tr className="text-left text-[#7a8fa8] bg-[#f4f7fb] border-b border-[#f0f4f9]">
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
        <tbody className="divide-y divide-[#f0f4f9] text-[#1e3050]">
          {pitches.map((p) => (
            <tr
              key={p.id}
              className="bg-white hover:bg-[#f4f7fb] transition-colors"
            >
              <td className="py-2 px-3 whitespace-nowrap font-mono tabular-nums text-[#7a8fa8]">
                {p.game_date ?? "—"}
              </td>
              <td className="py-2 px-3 text-[#1e3050]">
                {p.pitch_name ?? p.pitch_type ?? "—"}
              </td>
              <td className="py-2 px-3 font-mono tabular-nums text-[#1e3050]">
                {p.release_speed != null ? `${p.release_speed.toFixed(1)}` : "—"}
              </td>
              <td className="py-2 px-3 font-mono tabular-nums hidden sm:table-cell text-[#1e3050]">
                {p.launch_angle != null ? `${p.launch_angle.toFixed(0)}°` : "—"}
              </td>
              <td className="py-2 px-3 font-mono tabular-nums hidden sm:table-cell text-[#1e3050]">
                {p.launch_speed != null ? `${p.launch_speed.toFixed(1)}` : "—"}
              </td>
              <td className="py-2 px-3 max-w-[140px] sm:max-w-xs truncate text-[#1e3050]">
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

  const topPitches = pitches.slice(0, 10);

  const primaryCode = profile
    ? (
        profile.player?.primaryPosition as { code?: string } | undefined
      )?.code
    : undefined;
  const isPitcherPrimary =
    profile?.mlbStats?.isPitcherPrimary ?? primaryCode === "1";

  return (
    <div className="bg-white text-[#1e3050] max-w-6xl mx-auto space-y-10">
      <p className="text-xs font-black tracking-tight">
        <span className="text-[#b8922a]">WAR</span>
        <span className="text-[#0f2044]">room</span>
      </p>
      <nav className="text-sm">
        <Link
          href="/players"
          className="text-[#1e3a6b] hover:text-[#b8922a] transition-colors"
        >
          ← Players
        </Link>
      </nav>

      {loading ? (
        <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] py-20 flex flex-col items-center justify-center gap-3">
          <div className="h-10 w-10 rounded-full border-2 border-[#1e3a6b] border-t-transparent animate-spin" />
          <p className="text-sm text-[#7a8fa8]">Loading profile…</p>
        </div>
      ) : null}

      {!loading && error ? (
        <div
          className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] px-4 py-3 text-[#0f2044] text-sm"
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
              {isPitcherPrimary ? (
                <PitcherStatcastSection
                  pitcherPercentiles={profile.pitcherPercentiles}
                  season={season}
                />
              ) : (
                <BatterStatcastSection
                  batterPercentiles={profile.batterPercentiles}
                  season={season}
                />
              )}
            </section>
          </div>

          {topPitches.length > 0 ? (
            <PitchesTable pitches={topPitches} />
          ) : (
            <p className="text-sm text-[#7a8fa8] text-center py-8 border border-dashed border-[#d0daea] rounded-xl bg-[#f4f7fb]">
              No pitch or batted-ball rows in Supabase for this player yet.
            </p>
          )}
        </>
      ) : null}
    </div>
  );
}
