import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";

/** Columns of ``player_batting_seasons`` allowed for ``sort_by`` (server-side only). */
const SORTABLE_COLUMNS = [
  "id",
  "player_id",
  "season",
  "team",
  "pa",
  "avg",
  "obp",
  "slg",
  "hr",
  "wrc_plus",
  "ops_plus",
  "woba",
  "bwpr",
  "cqi",
] as const;

type SortableColumn = (typeof SORTABLE_COLUMNS)[number];

function isSortableColumn(s: string): s is SortableColumn {
  return (SORTABLE_COLUMNS as readonly string[]).includes(s);
}

const MAX_LIMIT = 500;

function parseRequiredSeason(raw: string | null): number | null {
  if (raw == null || raw === "") return null;
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n)) return null;
  return n;
}

function parsePositiveInt(
  raw: string | null,
  defaultValue: number,
): number {
  if (raw == null || raw === "") return defaultValue;
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n)) return defaultValue;
  return n;
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);

    const season = parseRequiredSeason(searchParams.get("season"));
    if (season === null) {
      return NextResponse.json(
        { error: "Missing or invalid required query param: season" },
        { status: 400 },
      );
    }

    let minPa = parsePositiveInt(searchParams.get("min_pa"), 50);
    if (minPa < 0) {
      return NextResponse.json(
        { error: "min_pa must be >= 0" },
        { status: 400 },
      );
    }

    const sortByRaw = searchParams.get("sort_by");
    const sortBy =
      sortByRaw == null || sortByRaw === "" ? "cqi" : sortByRaw;
    if (!isSortableColumn(sortBy)) {
      return NextResponse.json(
        {
          error: `Invalid sort_by. Allowed: ${SORTABLE_COLUMNS.join(", ")}`,
        },
        { status: 400 },
      );
    }

    const sortDirRaw = searchParams.get("sort_dir");
    const sortDir =
      sortDirRaw == null || sortDirRaw === "" ? "desc" : sortDirRaw;
    if (sortDir !== "asc" && sortDir !== "desc") {
      return NextResponse.json(
        { error: "sort_dir must be asc or desc" },
        { status: 400 },
      );
    }
    const ascending = sortDir === "asc";

    let limit = parsePositiveInt(searchParams.get("limit"), 100);
    if (limit < 1) limit = 100;
    if (limit > MAX_LIMIT) limit = MAX_LIMIT;

    const selectList = `
        id,
        player_id,
        player_name,
        season,
        team,
        pa,
        avg,
        obp,
        slg,
        hr,
        wrc_plus,
        ops_plus,
        woba,
        bwpr,
        cqi
      `;

    const { data, error, count } = await supabase
      .from("player_batting_seasons")
      .select(selectList, { count: "exact" })
      .eq("season", season)
      .gte("pa", minPa)
      .order(sortBy, { ascending, nullsFirst: false })
      .limit(limit);

    if (error) {
      console.error("leaderboards batting:", error);
      return NextResponse.json(
        { error: "Could not load batting leaderboard" },
        { status: 500 },
      );
    }

    const players = data ?? [];
    const total = count ?? 0;

    return NextResponse.json({
      players,
      season,
      total,
    });
  } catch (e) {
    console.error("leaderboards batting:", e);
    return NextResponse.json(
      { error: "Unexpected server error" },
      { status: 500 },
    );
  }
}
