import { rankByValue, statCell } from "@/lib/mlb-team-overview";
import type { TeamStandingsDetail } from "@/lib/mlb-standings-detail";
import {
  estimateBattersFaced,
  maxOfMetrics,
  weightedOrSimple,
} from "@/lib/team-statcast-aggregate";
import type {
  TeamBannerApiResponse,
  TeamBannerStat,
  TeamBannerStatcastBlock,
  TeamBannerWprBlock,
  TeamOverviewStat,
} from "@/types";

type BattingRow = {
  team_id: number;
  avg: number | null;
  obp: number | null;
  slg: number | null;
  ops: number | null;
  r: number | null;
  hr: number | null;
  woba: number | null;
  wrc_plus: number | null;
  iso: number | null;
  pa: number | null;
  bb: number | null;
  so: number | null;
};

type PitchingRow = {
  team_id: number;
  era: number | null;
  whip: number | null;
  r: number | null;
  so: number | null;
  bb: number | null;
  ip: number | null;
  h: number | null;
  fip: number | null;
};

type FieldingRow = {
  team_id: number;
  fld_pct: number | null;
  e: number | null;
};

type StatcastBattingRow = {
  team_id: number | null;
  pa: number | null;
  avg_exit_velocity: number | null;
  max_exit_velocity: number | null;
  avg_launch_angle: number | null;
  barrel_rate: number | null;
  hard_hit_rate: number | null;
  xwoba: number | null;
  sprint_speed: number | null;
  cqi: number | null;
};

type StatcastPitchingRow = {
  pitcher_id: number | null;
  pitches: number | null;
  stuff_plus: number | null;
};

type PitcherSeasonRow = {
  player_id: number;
  team_id: number | null;
  ip: number | null;
  xfip: number | null;
};

type OaaRow = {
  player_id: number;
  oaa: number | null;
};

type WprPositionRow = {
  team_id: number;
  position: string;
  bwpr: number | null;
  fwpr: number | null;
  brwpr: number | null;
  wpr: number | null;
  pwpr: number | null;
};

function num(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtRate3(v: number): string {
  return v.toFixed(3);
}

function fmtRate2(v: number): string {
  return v.toFixed(2);
}

function fmtInt(v: number): string {
  return String(Math.trunc(v));
}

function fmtPct(v: number): string {
  const pct = v <= 1 ? v * 100 : v;
  return `${pct.toFixed(1)}%`;
}

function fmtWpr(v: number): string {
  return v.toFixed(1);
}

function bannerStat(
  value: string | null,
  rank: number | null | undefined,
  proprietary = false,
): TeamBannerStat {
  return { ...statCell(value, rank), proprietary };
}

function rankStat(
  teamValues: Map<number, number | null>,
  teamId: number,
  lowerIsBetter: boolean,
  format: (v: number) => string,
): TeamOverviewStat {
  const entries = [...teamValues.entries()].map(([id, value]) => ({
    id,
    value,
  }));
  const ranks = rankByValue(entries, lowerIsBetter);
  const value = teamValues.get(teamId);
  return statCell(value != null ? format(value) : null, ranks.get(teamId));
}

function rankBannerStat(
  teamValues: Map<number, number | null>,
  teamId: number,
  lowerIsBetter: boolean,
  format: (v: number) => string,
  proprietary = false,
): TeamBannerStat {
  const base = rankStat(teamValues, teamId, lowerIsBetter, format);
  return { ...base, proprietary };
}

function aggregateStatcastByTeam(
  rows: StatcastBattingRow[],
): Map<number, StatcastBattingRow[]> {
  const map = new Map<number, StatcastBattingRow[]>();
  for (const row of rows) {
    const tid = row.team_id;
    if (tid == null || !Number.isFinite(tid)) continue;
    const list = map.get(tid) ?? [];
    list.push(row);
    map.set(tid, list);
  }
  return map;
}

function buildTeamStatcastBlock(
  byTeam: Map<number, StatcastBattingRow[]>,
  teamId: number,
): TeamBannerStatcastBlock | null {
  const list = byTeam.get(teamId);
  if (!list?.length) return null;

  const teamAgg = new Map<number, Record<string, number | null>>();

  for (const [tid, players] of byTeam) {
    teamAgg.set(tid, {
      avg_exit_velocity: weightedOrSimple(
        players,
        (r) => r.avg_exit_velocity,
        (r) => r.pa,
      ),
      max_exit_velocity: maxOfMetrics(
        players,
        (r) => r.max_exit_velocity,
      ),
      avg_launch_angle: weightedOrSimple(
        players,
        (r) => r.avg_launch_angle,
        (r) => r.pa,
      ),
      barrel_rate: weightedOrSimple(
        players,
        (r) => r.barrel_rate,
        (r) => r.pa,
      ),
      hard_hit_rate: weightedOrSimple(
        players,
        (r) => r.hard_hit_rate,
        (r) => r.pa,
      ),
      avg_xwoba: weightedOrSimple(players, (r) => r.xwoba, (r) => r.pa),
      avg_sprint_speed: weightedOrSimple(
        players,
        (r) => r.sprint_speed,
        (r) => r.pa,
      ),
      cqi: weightedOrSimple(players, (r) => r.cqi, (r) => r.pa),
    });
  }

  const metrics: Array<{
    key: keyof TeamBannerStatcastBlock;
    lower: boolean;
    fmt: (v: number) => string;
    proprietary?: boolean;
  }> = [
    { key: "avg_exit_velocity", lower: false, fmt: (v) => `${v.toFixed(1)}` },
    { key: "max_exit_velocity", lower: false, fmt: (v) => `${v.toFixed(1)}` },
    { key: "avg_launch_angle", lower: false, fmt: (v) => `${v.toFixed(1)}°` },
    { key: "barrel_rate", lower: false, fmt: fmtPct },
    { key: "hard_hit_rate", lower: false, fmt: fmtPct },
    { key: "avg_xwoba", lower: false, fmt: (v) => v.toFixed(3) },
    { key: "avg_sprint_speed", lower: false, fmt: (v) => `${v.toFixed(1)}` },
    { key: "cqi", lower: false, fmt: (v) => v.toFixed(0), proprietary: true },
  ];

  const block = {} as TeamBannerStatcastBlock;
  for (const m of metrics) {
    const values = new Map<number, number | null>();
    for (const [tid, agg] of teamAgg) {
      values.set(tid, agg[m.key] ?? null);
    }
    block[m.key] = rankBannerStat(
      values,
      teamId,
      m.lower,
      m.fmt,
      m.proprietary,
    );
  }

  return block;
}

function buildTeamStuffPlus(
  pitchingRows: StatcastPitchingRow[],
  pitcherSeasons: PitcherSeasonRow[],
): Map<number, number | null> {
  const teamPitchers = new Map<number, Set<number>>();
  for (const row of pitcherSeasons) {
    if (row.team_id == null) continue;
    const set = teamPitchers.get(row.team_id) ?? new Set();
    set.add(row.player_id);
    teamPitchers.set(row.team_id, set);
  }

  const stuffByPitcher = new Map<number, StatcastPitchingRow>();
  for (const row of pitchingRows) {
    if (row.pitcher_id == null) continue;
    stuffByPitcher.set(row.pitcher_id, row);
  }

  const result = new Map<number, number | null>();
  for (const [teamId, pitchers] of teamPitchers) {
    let num = 0;
    let denom = 0;
    for (const pid of pitchers) {
      const sp = stuffByPitcher.get(pid);
      const stuff = sp?.stuff_plus;
      if (stuff == null || !Number.isFinite(stuff)) continue;
      const weight = sp?.pitches ?? 0;
      if (weight > 0) {
        num += stuff * weight;
        denom += weight;
      }
    }
    result.set(teamId, denom > 0 ? num / denom : null);
  }
  return result;
}

function buildTeamXfip(
  pitcherSeasons: PitcherSeasonRow[],
): Map<number, number | null> {
  const byTeam = new Map<number, { num: number; denom: number }>();
  for (const row of pitcherSeasons) {
    if (row.team_id == null || row.xfip == null || row.ip == null) continue;
    if (!Number.isFinite(row.xfip) || !Number.isFinite(row.ip) || row.ip <= 0) {
      continue;
    }
    const bucket = byTeam.get(row.team_id) ?? { num: 0, denom: 0 };
    bucket.num += row.xfip * row.ip;
    bucket.denom += row.ip;
    byTeam.set(row.team_id, bucket);
  }
  const result = new Map<number, number | null>();
  for (const [teamId, { num, denom }] of byTeam) {
    result.set(teamId, denom > 0 ? num / denom : null);
  }
  return result;
}

function buildTeamOaa(
  oaaRows: OaaRow[],
  playerTeamMap: Map<number, number>,
): Map<number, number | null> {
  const totals = new Map<number, number>();
  for (const row of oaaRows) {
    const teamId = playerTeamMap.get(row.player_id);
    const oaa = row.oaa;
    if (teamId == null || oaa == null || !Number.isFinite(oaa)) continue;
    totals.set(teamId, (totals.get(teamId) ?? 0) + oaa);
  }
  const result = new Map<number, number | null>();
  for (const [teamId, total] of totals) {
    result.set(teamId, total);
  }
  return result;
}

function buildTeamWprTotals(
  wprRows: WprPositionRow[],
): Map<
  number,
  { bwpr: number; fwpr: number; brwpr: number; wpr: number; pwpr: number }
> {
  const totals = new Map<
    number,
    { bwpr: number; fwpr: number; brwpr: number; wpr: number; pwpr: number }
  >();

  for (const row of wprRows) {
    const bucket = totals.get(row.team_id) ?? {
      bwpr: 0,
      fwpr: 0,
      brwpr: 0,
      wpr: 0,
      pwpr: 0,
    };
    if (row.position === "P") {
      bucket.pwpr += row.pwpr ?? 0;
    } else {
      bucket.bwpr += row.bwpr ?? 0;
      bucket.fwpr += row.fwpr ?? 0;
      bucket.brwpr += row.brwpr ?? 0;
      bucket.wpr += row.wpr ?? 0;
    }
    totals.set(row.team_id, bucket);
  }

  return totals;
}

function buildWprBlock(
  totals: Map<
    number,
    { bwpr: number; fwpr: number; brwpr: number; wpr: number; pwpr: number }
  >,
  teamId: number,
): TeamBannerWprBlock | null {
  if (!totals.has(teamId)) return null;

  const keys = ["bwpr", "fwpr", "brwpr", "wpr", "pwpr"] as const;
  const valueMaps = Object.fromEntries(
    keys.map((key) => [
      key,
      new Map<number, number | null>(
        [...totals.entries()].map(([id, t]) => [id, t[key]]),
      ),
    ]),
  ) as Record<(typeof keys)[number], Map<number, number | null>>;

  return {
    hitting: {
      bwpr: rankBannerStat(valueMaps.bwpr, teamId, false, fmtWpr, true),
      fwpr: rankBannerStat(valueMaps.fwpr, teamId, false, fmtWpr, true),
      brwpr: rankBannerStat(valueMaps.brwpr, teamId, false, fmtWpr, true),
      wpr: rankBannerStat(valueMaps.wpr, teamId, false, fmtWpr, true),
    },
    pitching: {
      pwpr: rankBannerStat(valueMaps.pwpr, teamId, false, fmtWpr, true),
    },
  };
}

export function buildTeamBannerResponse(input: {
  teamId: number;
  season: number;
  standings: TeamStandingsDetail | null;
  batting: BattingRow[];
  pitching: PitchingRow[];
  fielding: FieldingRow[];
  statcastBatting: StatcastBattingRow[];
  statcastPitching: StatcastPitchingRow[];
  pitcherSeasons: PitcherSeasonRow[];
  oaaRows: OaaRow[];
  playerTeamMap: Map<number, number>;
  wprRows: WprPositionRow[];
}): TeamBannerApiResponse {
  const { teamId, season, standings } = input;

  const bbPctByTeam = new Map<number, number | null>();
  const kPctBatByTeam = new Map<number, number | null>();
  for (const row of input.batting) {
    const pa = row.pa;
    bbPctByTeam.set(
      row.team_id,
      pa != null && pa > 0 && row.bb != null ? row.bb / pa : null,
    );
    kPctBatByTeam.set(
      row.team_id,
      pa != null && pa > 0 && row.so != null ? row.so / pa : null,
    );
  }

  const kPctPitchByTeam = new Map<number, number | null>();
  const bbPctPitchByTeam = new Map<number, number | null>();
  const kMinusBbByTeam = new Map<number, number | null>();
  for (const row of input.pitching) {
    const bf = estimateBattersFaced(row.ip, row.h, row.bb, row.so);
    kPctPitchByTeam.set(
      row.team_id,
      bf != null && bf > 0 && row.so != null ? row.so / bf : null,
    );
    bbPctPitchByTeam.set(
      row.team_id,
      bf != null && bf > 0 && row.bb != null ? row.bb / bf : null,
    );
    kMinusBbByTeam.set(
      row.team_id,
      bf != null && bf > 0 && row.so != null && row.bb != null
        ? (row.so - row.bb) / bf
        : null,
    );
  }

  const stuffPlusByTeam = buildTeamStuffPlus(
    input.statcastPitching,
    input.pitcherSeasons,
  );
  const xfipByTeam = buildTeamXfip(input.pitcherSeasons);
  const oaaByTeam = buildTeamOaa(input.oaaRows, input.playerTeamMap);
  const wprTotals = buildTeamWprTotals(input.wprRows);
  const fwprByTeam = new Map<number, number | null>(
    [...wprTotals.entries()].map(([id, t]) => [id, t.fwpr]),
  );

  const statcastByTeam = aggregateStatcastByTeam(input.statcastBatting);
  const statcast = buildTeamStatcastBlock(statcastByTeam, teamId);
  const wpr = buildWprBlock(wprTotals, teamId);

  const avgMap = new Map(
    input.batting.map((r) => [r.team_id, r.avg]),
  );
  const obpMap = new Map(input.batting.map((r) => [r.team_id, r.obp]));
  const slgMap = new Map(input.batting.map((r) => [r.team_id, r.slg]));
  const opsMap = new Map(input.batting.map((r) => [r.team_id, r.ops]));
  const runsMap = new Map(input.batting.map((r) => [r.team_id, num(r.r)]));
  const hrMap = new Map(input.batting.map((r) => [r.team_id, num(r.hr)]));
  const wobaMap = new Map(input.batting.map((r) => [r.team_id, r.woba]));
  const wrcMap = new Map(
    input.batting.map((r) => [r.team_id, num(r.wrc_plus)]),
  );
  const isoMap = new Map(input.batting.map((r) => [r.team_id, r.iso]));

  const eraMap = new Map(input.pitching.map((r) => [r.team_id, r.era]));
  const whipMap = new Map(input.pitching.map((r) => [r.team_id, r.whip]));
  const raMap = new Map(input.pitching.map((r) => [r.team_id, num(r.r)]));
  const soMap = new Map(input.pitching.map((r) => [r.team_id, num(r.so)]));
  const fipMap = new Map(input.pitching.map((r) => [r.team_id, r.fip]));

  const fldMap = new Map(input.fielding.map((r) => [r.team_id, r.fld_pct]));
  const errMap = new Map(input.fielding.map((r) => [r.team_id, num(r.e)]));

  return {
    season,
    record: standings
      ? {
          wins: standings.wins,
          losses: standings.losses,
          winPct: standings.winPct,
          divisionRank: standings.divisionRank,
          divisionName: standings.divisionName,
          gamesBack: standings.gamesBack,
          playoffPosition: standings.playoffPosition,
        }
      : null,
    batting: {
      avg: rankBannerStat(avgMap, teamId, false, fmtRate3),
      obp: rankBannerStat(obpMap, teamId, false, fmtRate3),
      slg: rankBannerStat(slgMap, teamId, false, fmtRate3),
      ops: rankBannerStat(opsMap, teamId, false, fmtRate3),
      runs: rankBannerStat(runsMap, teamId, false, fmtInt),
      homeRuns: rankBannerStat(hrMap, teamId, false, fmtInt),
      woba: rankBannerStat(wobaMap, teamId, false, fmtRate3),
      wrc_plus: rankBannerStat(wrcMap, teamId, false, fmtInt),
      iso: rankBannerStat(isoMap, teamId, false, fmtRate3),
      bb_pct: rankBannerStat(bbPctByTeam, teamId, false, fmtPct),
      k_pct: rankBannerStat(kPctBatByTeam, teamId, true, fmtPct),
    },
    pitching: {
      era: rankBannerStat(eraMap, teamId, true, fmtRate2),
      whip: rankBannerStat(whipMap, teamId, true, fmtRate2),
      runsAllowed: rankBannerStat(raMap, teamId, true, fmtInt),
      strikeOuts: rankBannerStat(soMap, teamId, false, fmtInt),
      fip: rankBannerStat(fipMap, teamId, true, fmtRate2),
      xfip: rankBannerStat(xfipByTeam, teamId, true, fmtRate2),
      k_pct: rankBannerStat(kPctPitchByTeam, teamId, false, fmtPct),
      bb_pct: rankBannerStat(bbPctPitchByTeam, teamId, true, fmtPct),
      k_bb_pct: rankBannerStat(kMinusBbByTeam, teamId, false, fmtPct),
      stuff_plus: rankBannerStat(
        stuffPlusByTeam,
        teamId,
        false,
        (v) => v.toFixed(0),
        true,
      ),
    },
    fielding: {
      fld_pct: rankBannerStat(fldMap, teamId, false, fmtRate3),
      errors: rankBannerStat(errMap, teamId, true, fmtInt),
      oaa: rankBannerStat(oaaByTeam, teamId, false, fmtInt),
      fwpr: rankBannerStat(fwprByTeam, teamId, false, fmtWpr, true),
    },
    statcast,
    wpr,
  };
}

export function mapDbRows(input: {
  batting: Record<string, unknown>[];
  pitching: Record<string, unknown>[];
  fielding: Record<string, unknown>[];
  statcastBatting: Record<string, unknown>[];
  statcastPitching: Record<string, unknown>[];
  pitcherSeasons: Record<string, unknown>[];
  oaaRows: Record<string, unknown>[];
  playerTeamRows: Record<string, unknown>[];
  wprRows: Record<string, unknown>[];
}) {
  return {
    batting: input.batting.map((r) => ({
      team_id: num(r.team_id) as number,
      avg: num(r.avg),
      obp: num(r.obp),
      slg: num(r.slg),
      ops: num(r.ops),
      r: num(r.r),
      hr: num(r.hr),
      woba: num(r.woba),
      wrc_plus: num(r.wrc_plus),
      iso: num(r.iso),
      pa: num(r.pa),
      bb: num(r.bb),
      so: num(r.so),
    })),
    pitching: input.pitching.map((r) => ({
      team_id: num(r.team_id) as number,
      era: num(r.era),
      whip: num(r.whip),
      r: num(r.r),
      so: num(r.so),
      bb: num(r.bb),
      ip: num(r.ip),
      h: num(r.h),
      fip: num(r.fip),
    })),
    fielding: input.fielding.map((r) => ({
      team_id: num(r.team_id) as number,
      fld_pct: num(r.fld_pct),
      e: num(r.e),
    })),
    statcastBatting: input.statcastBatting.map((r) => ({
      team_id: num(r.team_id),
      pa: num(r.pa),
      avg_exit_velocity: num(r.avg_exit_velocity),
      max_exit_velocity: num(r.max_exit_velocity),
      avg_launch_angle: num(r.avg_launch_angle),
      barrel_rate: num(r.barrel_rate),
      hard_hit_rate: num(r.hard_hit_rate),
      xwoba: num(r.xwoba),
      sprint_speed: num(r.sprint_speed),
      cqi: num(r.cqi),
    })),
    statcastPitching: input.statcastPitching.map((r) => ({
      pitcher_id: num(r.pitcher_id),
      pitches: num(r.pitches),
      stuff_plus: num(r.stuff_plus),
    })),
    pitcherSeasons: input.pitcherSeasons.map((r) => ({
      player_id: num(r.player_id) as number,
      team_id: num(r.team_id),
      ip: num(r.ip),
      xfip: num(r.xfip),
    })),
    oaaRows: input.oaaRows.map((r) => ({
      player_id: num(r.player_id) as number,
      oaa: num(r.oaa),
    })),
    playerTeamMap: new Map(
      input.playerTeamRows
        .map((r) => {
          const pid = num(r.player_id);
          const tid = num(r.team_id);
          if (pid == null || tid == null) return null;
          return [pid, tid] as const;
        })
        .filter((x): x is readonly [number, number] => x != null),
    ),
    wprRows: input.wprRows.map((r) => ({
      team_id: num(r.team_id) as number,
      position: String(r.position),
      bwpr: num(r.bwpr),
      fwpr: num(r.fwpr),
      brwpr: num(r.brwpr),
      wpr: num(r.wpr),
      pwpr: num(r.pwpr),
    })),
  };
}
