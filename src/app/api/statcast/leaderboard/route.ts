import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";

const STAT_COLUMNS = {
  exit_velocity: "avg_exit_velocity",
  launch_angle: "avg_launch_angle",
  hard_hit_rate: "hard_hit_rate",
  barrel_rate: "barrel_rate",
  sprint_speed: "sprint_speed",
  xwoba: "xwoba",
} as const;

export type LeaderboardStatParam = keyof typeof STAT_COLUMNS;

function isLeaderboardStat(s: string): s is LeaderboardStatParam {
  return s in STAT_COLUMNS;
}

type BattingRow = {
  id: number;
  player_id: number | null;
  player_name: string | null;
  team_id: number | null;
  season: number | null;
  avg_exit_velocity: number | null;
  max_exit_velocity: number | null;
  avg_launch_angle: number | null;
  barrel_rate: number | null;
  hard_hit_rate: number | null;
  xba: number | null;
  xslg: number | null;
  xwoba: number | null;
  sprint_speed: number | null;
  updated_at: string | null;
};

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const statRaw = searchParams.get("stat");
    const statParam =
      statRaw == null || statRaw === "" ? "exit_velocity" : statRaw;
    const limitRaw = searchParams.get("limit");
    const seasonRaw = searchParams.get("season");

    if (!isLeaderboardStat(statParam)) {
      return NextResponse.json(
        {
          error:
            "Invalid stat. Use: exit_velocity, launch_angle, hard_hit_rate, barrel_rate, sprint_speed, xwoba",
        },
        { status: 400 },
      );
    }

    const orderColumn = STAT_COLUMNS[statParam];
    const season =
      seasonRaw != null && seasonRaw !== ""
        ? parseInt(seasonRaw, 10)
        : new Date().getFullYear();
    if (!Number.isFinite(season)) {
      return NextResponse.json({ error: "Invalid season" }, { status: 400 });
    }

    let limit =
      limitRaw != null && limitRaw !== ""
        ? parseInt(limitRaw, 10)
        : 25;
    if (!Number.isFinite(limit) || limit < 1) limit = 25;
    if (limit > 200) limit = 200;

    const { data, error } = await supabase
      .from("statcast_batting")
      .select(
        `
        id,
        player_id,
        player_name,
        team_id,
        season,
        avg_exit_velocity,
        max_exit_velocity,
        avg_launch_angle,
        barrel_rate,
        hard_hit_rate,
        xba,
        xslg,
        xwoba,
        sprint_speed,
        updated_at
      `,
      )
      .eq("season", season)
      .not(orderColumn, "is", null)
      .order(orderColumn, { ascending: false })
      .limit(limit);

    if (error) {
      console.error("statcast leaderboard:", error);
      return NextResponse.json(
        { error: "Could not load leaderboard" },
        { status: 500 },
      );
    }

    const rows = (data ?? []) as BattingRow[];
    const teamIdNums = [
      ...new Set(
        rows
          .map((r) => r.team_id)
          .filter(
            (id): id is number =>
              id != null && Number.isFinite(Number(id)),
          )
          .map((id) => Number(id)),
      ),
    ];

    const abbrevByTeamId = new Map<number, string>();

    if (teamIdNums.length > 0) {
      const { data: teamRows, error: teamErr } = await supabase
        .from("teams")
        .select("id, abbreviation")
        .in("id", teamIdNums);

      if (teamErr) {
        console.error("statcast leaderboard teams:", teamErr);
      } else {
        for (const t of teamRows ?? []) {
          const tid = t.id != null ? Number(t.id) : null;
          const abbr = t.abbreviation?.trim();
          if (tid != null && Number.isFinite(tid) && abbr) {
            abbrevByTeamId.set(tid, abbr);
          }
        }
      }
    }

    const leaderboard = rows.map((row) => {
      const tid =
        row.team_id != null && Number.isFinite(Number(row.team_id))
          ? Number(row.team_id)
          : null;
      const abbr = tid != null ? abbrevByTeamId.get(tid) : undefined;
      const team_display = abbr ?? "—";

      return {
        ...row,
        team_display,
      };
    });

    return NextResponse.json({
      leaderboard,
      stat: statParam,
      season,
    });
  } catch (e) {
    console.error("statcast leaderboard:", e);
    return NextResponse.json(
      { error: "Unexpected server error" },
      { status: 500 },
    );
  }
}
