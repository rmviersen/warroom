"use client";

import Image from "next/image";
import { useState, type ReactNode } from "react";

import { getTeamLogoUrl } from "@/lib/mlb-images";
import {
  playoffFirstCellClass,
  playoffRowClass,
} from "@/lib/playoff-teams";
import type { TeamBannerApiResponse, TeamBannerStat } from "@/types";

const TOP_METRIC_RANK = 5;

function isTopMetricRank(rank: number | null | undefined): boolean {
  return rank != null && rank >= 1 && rank <= TOP_METRIC_RANK;
}

function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

function RankedStat({
  label,
  stat,
}: {
  label: string;
  stat: TeamBannerStat;
}) {
  const top5 = isTopMetricRank(stat.rank);
  const gold = stat.proprietary || top5;

  return (
    <div className="min-w-[4.5rem] shrink-0">
      <dt className="text-[10px] font-semibold uppercase tracking-wider text-[#7a8fa8]">
        {label}
      </dt>
      <dd
        className={`mt-0.5 font-mono text-xs tabular-nums sm:text-sm ${
          stat.proprietary
            ? "font-semibold text-[#b8922a]"
            : top5
              ? "font-semibold text-[#1e3a6b]"
              : "text-[#1e3050]"
        }`}
      >
        {stat.value ?? "—"}
        {stat.rank != null ? (
          <span
            className={`ml-0.5 text-[9px] font-normal ${
              gold ? "text-[#b8922a]/80" : "text-[#7a8fa8]"
            }`}
          >
            #{stat.rank}
          </span>
        ) : null}
      </dd>
    </div>
  );
}

function StatGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-[#d0daea]/80 bg-white/70 px-3 py-2.5">
      <h2 className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#1e3a6b]">
        {title}
      </h2>
      <dl className="flex flex-wrap gap-x-4 gap-y-2">{children}</dl>
    </div>
  );
}

function formatDivisionRank(
  rank: number | null,
  divisionName: string | null,
): string {
  if (rank == null) return "—";
  const div = divisionName?.trim();
  return div ? `${ordinal(rank)} ${div}` : ordinal(rank);
}

export default function TeamProfileBanner({
  team,
  teamId,
  banner,
  season,
}: {
  team: Record<string, unknown>;
  teamId: number;
  banner: TeamBannerApiResponse | null;
  season: number;
}) {
  const [hideLogo, setHideLogo] = useState(false);
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

  const record = banner?.record;
  const playoff = record?.playoffPosition ?? false;

  return (
    <header
      className={`rounded-xl border border-[#d0daea] bg-[#f4f7fb] overflow-hidden ${playoffRowClass(playoff)} ${playoff ? playoffFirstCellClass(true) : ""}`}
    >
      <div className="space-y-4 p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          {!hideLogo && teamId ? (
            <span className="relative h-16 w-16 shrink-0">
              <Image
                src={getTeamLogoUrl(teamId)}
                alt=""
                fill
                className="object-contain"
                sizes="64px"
                onError={() => setHideLogo(true)}
              />
            </span>
          ) : null}

          <div className="min-w-0 flex-1 space-y-3">
            <div>
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[#0f2044] truncate">
                {name}
              </h1>
              <p className="mt-1 text-xs text-[#7a8fa8]">
                {league} · {division} · {venueName}
              </p>
            </div>

            {record ? (
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
                <p className="font-mono tabular-nums text-[#0f2044]">
                  <span className="text-lg font-bold">
                    {record.wins}-{record.losses}
                  </span>
                  <span className="ml-2 text-[#7a8fa8]">
                    ({record.winPct})
                  </span>
                </p>
                <p className="text-[#1e3050]">
                  {formatDivisionRank(record.divisionRank, record.divisionName)}
                </p>
                <p className="font-mono tabular-nums text-[#7a8fa8]">
                  GB {record.gamesBack}
                </p>
                {playoff ? (
                  <span className="rounded-full border border-[#b8922a]/40 bg-[#b8922a]/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#b8922a]">
                    Playoff position
                  </span>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-[#7a8fa8]">
                Standings unavailable for {season}.
              </p>
            )}
          </div>
        </div>

        {banner ? (
          <div className="grid grid-cols-1 gap-2 xl:grid-cols-2 2xl:grid-cols-3">
            <StatGroup title="Batting">
              <RankedStat label="AVG" stat={banner.batting.avg} />
              <RankedStat label="OBP" stat={banner.batting.obp} />
              <RankedStat label="SLG" stat={banner.batting.slg} />
              <RankedStat label="OPS" stat={banner.batting.ops} />
              <RankedStat label="R" stat={banner.batting.runs} />
              <RankedStat label="HR" stat={banner.batting.homeRuns} />
              <RankedStat label="wOBA" stat={banner.batting.woba} />
              <RankedStat label="wRC+" stat={banner.batting.wrc_plus} />
              <RankedStat label="ISO" stat={banner.batting.iso} />
              <RankedStat label="BB%" stat={banner.batting.bb_pct} />
              <RankedStat label="K%" stat={banner.batting.k_pct} />
            </StatGroup>

            <StatGroup title="Pitching">
              <RankedStat label="ERA" stat={banner.pitching.era} />
              <RankedStat label="WHIP" stat={banner.pitching.whip} />
              <RankedStat label="RA" stat={banner.pitching.runsAllowed} />
              <RankedStat label="K" stat={banner.pitching.strikeOuts} />
              <RankedStat label="FIP" stat={banner.pitching.fip} />
              <RankedStat label="xFIP" stat={banner.pitching.xfip} />
              <RankedStat label="K%" stat={banner.pitching.k_pct} />
              <RankedStat label="BB%" stat={banner.pitching.bb_pct} />
              <RankedStat label="K−BB%" stat={banner.pitching.k_bb_pct} />
              <RankedStat label="Stuff+" stat={banner.pitching.stuff_plus} />
            </StatGroup>

            <StatGroup title="Fielding">
              <RankedStat label="FPCT" stat={banner.fielding.fld_pct} />
              <RankedStat label="E" stat={banner.fielding.errors} />
              <RankedStat label="OAA" stat={banner.fielding.oaa} />
              <RankedStat label="fWPR" stat={banner.fielding.fwpr} />
            </StatGroup>

            {banner.statcast ? (
              <StatGroup title={`Statcast · ${season}`}>
                <RankedStat
                  label="Avg EV"
                  stat={banner.statcast.avg_exit_velocity}
                />
                <RankedStat
                  label="Max EV"
                  stat={banner.statcast.max_exit_velocity}
                />
                <RankedStat
                  label="Launch"
                  stat={banner.statcast.avg_launch_angle}
                />
                <RankedStat
                  label="Barrel%"
                  stat={banner.statcast.barrel_rate}
                />
                <RankedStat
                  label="Hard-hit%"
                  stat={banner.statcast.hard_hit_rate}
                />
                <RankedStat label="xwOBA" stat={banner.statcast.avg_xwoba} />
                <RankedStat
                  label="Sprint"
                  stat={banner.statcast.avg_sprint_speed}
                />
                <RankedStat label="CQI" stat={banner.statcast.cqi} />
              </StatGroup>
            ) : null}

            {banner.wpr ? (
              <>
                <StatGroup title="WPR · Hitting">
                  <RankedStat label="bWPR" stat={banner.wpr.hitting.bwpr} />
                  <RankedStat label="fWPR" stat={banner.wpr.hitting.fwpr} />
                  <RankedStat label="brWPR" stat={banner.wpr.hitting.brwpr} />
                  <RankedStat label="WPR" stat={banner.wpr.hitting.wpr} />
                </StatGroup>
                <StatGroup title="WPR · Pitching">
                  <RankedStat label="pWPR" stat={banner.wpr.pitching.pwpr} />
                </StatGroup>
              </>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-[#7a8fa8] rounded-lg border border-[#d0daea] bg-white/60 px-4 py-3">
            Team metrics could not be loaded. Counting stats below may still be
            available.
          </p>
        )}
      </div>
    </header>
  );
}
