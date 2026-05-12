import { NextResponse } from "next/server";

import { mlbFetch } from "@/lib/mlb-api";
import { parseHydratedPitchingSeasonSummary } from "@/lib/mlb-player-stats";

function todayYmdLocal(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const PEOPLE_IDS_CHUNK = 40;

type ScheduleSide = {
  probablePitcher?: {
    id?: number;
    fullName?: string;
    seasonPitching?: {
      wins: number;
      losses: number;
      era: string | null;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

type ScheduleGameRaw = {
  teams?: {
    away?: ScheduleSide;
    home?: ScheduleSide;
  };
  [key: string]: unknown;
};

type ScheduleDateRaw = {
  games?: ScheduleGameRaw[];
  [key: string]: unknown;
};

function collectProbablePitcherIds(dates: ScheduleDateRaw[]): Set<number> {
  const ids = new Set<number>();
  for (const d of dates) {
    for (const g of d.games ?? []) {
      for (const side of ["away", "home"] as const) {
        const pid = g.teams?.[side]?.probablePitcher?.id;
        if (typeof pid === "number" && Number.isFinite(pid)) ids.add(pid);
      }
    }
  }
  return ids;
}

function attachSeasonPitchingToSchedule(
  dates: ScheduleDateRaw[],
  summaries: Map<number, { wins: number; losses: number; era: string | null }>,
): void {
  for (const d of dates) {
    for (const g of d.games ?? []) {
      for (const side of ["away", "home"] as const) {
        const pitcher = g.teams?.[side]?.probablePitcher;
        const id = pitcher?.id;
        if (typeof id !== "number" || !pitcher) continue;
        const row = summaries.get(id);
        if (!row) continue;
        pitcher.seasonPitching = {
          wins: row.wins,
          losses: row.losses,
          era: row.era,
        };
      }
    }
  }
}

async function fetchPitcherSeasonSummaries(
  ids: number[],
  seasonYear: number,
): Promise<Map<number, { wins: number; losses: number; era: string | null }>> {
  const map = new Map<
    number,
    { wins: number; losses: number; era: string | null }
  >();
  if (ids.length === 0) return map;

  for (let i = 0; i < ids.length; i += PEOPLE_IDS_CHUNK) {
    const slice = ids.slice(i, i + PEOPLE_IDS_CHUNK);
    const idParam = slice.join(",");
    try {
      const res = (await mlbFetch(
        `/people?personIds=${idParam}&hydrate=stats(group=[pitching],type=[season])`,
      )) as { people?: Array<{ id?: number; stats?: unknown }> };
      for (const p of res.people ?? []) {
        const pid = p.id;
        if (typeof pid !== "number" || !Number.isFinite(pid)) continue;
        const summary = parseHydratedPitchingSeasonSummary(p.stats, seasonYear);
        if (summary) map.set(pid, summary);
      }
    } catch (e) {
      console.warn("schedule: pitcher stats batch failed:", e);
    }
  }

  return map;
}

export async function GET() {
  try {
    const date = todayYmdLocal();
    const seasonYear = new Date().getFullYear();
    const data = (await mlbFetch(
      `/schedule?sportId=1&date=${date}&hydrate=team,linescore,probablePitcher`,
    )) as { dates?: ScheduleDateRaw[] };

    const dates = data.dates ?? [];
    const ids = [...collectProbablePitcherIds(dates)];
    const summaries = await fetchPitcherSeasonSummaries(ids, seasonYear);
    attachSeasonPitchingToSchedule(dates, summaries);

    return NextResponse.json({ dates });
  } catch {
    return NextResponse.json(
      { error: "Failed to fetch schedule from MLB API" },
      { status: 500 },
    );
  }
}
