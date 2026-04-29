export interface Player {
  id: number;
  full_name: string;
  team: string;
  position: string;
  jersey_number?: string;
}

/** Row returned by GET /api/teams (maps to SCHEMA.teams). */
export interface Team {
  id: number;
  name: string | null;
  abbreviation: string | null;
  team_name?: string | null;
  location_name?: string | null;
  division: string | null;
  division_id?: number | null;
  league: string | null;
  league_id?: number | null;
  venue?: string | null;
}

/** Team hitting line for GET /api/teams/[id] (season totals). */
export interface TeamSeasonHittingSummary {
  avg: string | null;
  ops: string | null;
  homeRuns: number | null;
  rbi: number | null;
  runs: number | null;
}

/** Team pitching line for GET /api/teams/[id] (season totals). */
export interface TeamSeasonPitchingSummary {
  era: string | null;
  whip: string | null;
  strikeOuts: number | null;
  baseOnBalls: number | null;
  saves: number | null;
}

/** Parsed MLB team season stats. */
export interface TeamSeasonStats {
  season: number;
  hitting: TeamSeasonHittingSummary | null;
  pitching: TeamSeasonPitchingSummary | null;
}

/** Roster position bucket for sorting / filtering. */
export type TeamRosterPositionGroup =
  | "pitchers"
  | "catchers"
  | "infielders"
  | "outfielders"
  | "dh"
  | "other";

/** One active roster player from GET /api/teams/[id]. */
export interface TeamRosterPlayer {
  playerId: number;
  fullName: string;
  jerseyNumber: string | null;
  positionAbbrev: string | null;
  positionName: string | null;
  positionCode: string | null;
  positionGroup: TeamRosterPositionGroup;
  batSide: string | null;
  pitchHand: string | null;
}

/** GET /api/teams/[id] JSON body. */
export interface TeamDetailApiResponse {
  team: Record<string, unknown>;
  roster: TeamRosterPlayer[];
  stats: TeamSeasonStats | null;
}

/** Aggregated Statcast batting metrics for a team (season). */
export interface TeamStatcastAggregates {
  season: number;
  /** Sum of player ``pa`` weights (Savant attempts / expected PA) for rows with pa > 0. */
  total_pa: number;
  avg_exit_velocity: number | null;
  max_exit_velocity: number | null;
  avg_launch_angle: number | null;
  barrel_rate: number | null;
  hard_hit_rate: number | null;
  avg_xwoba: number | null;
  avg_sprint_speed: number | null;
}

/** One row in top-by-exit-velo list from GET /api/teams/[id]/statcast. */
export interface TeamStatcastTopPlayer {
  player_id: number;
  player_name: string | null;
  pa: number | null;
  avg_exit_velocity: number | null;
  barrel_rate: number | null;
  xwoba: number | null;
}

/** GET /api/teams/[id]/statcast JSON body. */
export interface TeamStatcastApiResponse {
  teamStatcast: TeamStatcastAggregates | null;
  topPlayers: TeamStatcastTopPlayer[];
  playerCount: number;
}

/** Single team row for standings tables on the dashboard. */
export interface StandingRow {
  teamName: string;
  wins: number;
  losses: number;
  pct: string;
  gamesBack: string;
  divisionName: string;
}

/** Subset of MLB Stats API person object from /api/players?search= */
export interface PlayerSearchHit {
  id: number;
  fullName?: string;
  primaryPosition?: { abbreviation?: string; name?: string };
  currentTeam?: { name?: string };
}

/** Season hitting line from MLB Stats API ``stats[].splits[].stat``. */
export interface MlbSeasonHittingLine {
  gamesPlayed?: number | null;
  atBats?: number | null;
  runs?: number | null;
  hits?: number | null;
  doubles?: number | null;
  triples?: number | null;
  homeRuns?: number | null;
  rbi?: number | null;
  baseOnBalls?: number | null;
  strikeOuts?: number | null;
  stolenBases?: number | null;
  avg?: string | null;
  obp?: string | null;
  slg?: string | null;
  ops?: string | null;
}

/** Season pitching line from MLB Stats API ``stats[].splits[].stat``. */
export interface MlbSeasonPitchingLine {
  gamesPlayed?: number | null;
  gamesStarted?: number | null;
  wins?: number | null;
  losses?: number | null;
  saves?: number | null;
  inningsPitched?: string | null;
  earnedRuns?: number | null;
  era?: string | null;
  strikeOuts?: number | null;
  baseOnBalls?: number | null;
  whip?: string | null;
}

/** Parsed MLB season stats for GET /api/players/[id]. */
export interface PlayerProfileMlbStats {
  season: number;
  isPitcherPrimary: boolean;
  hitting: MlbSeasonHittingLine | null;
  pitching: MlbSeasonPitchingLine | null;
}

/** GET /api/players/[id] JSON body. */
export interface PlayerProfileApiResponse {
  player: Record<string, unknown> | null;
  mlbStats: PlayerProfileMlbStats | null;
  statcastBatting: StatcastBatting | null;
}

/** GET /api/players/[id]/pitches JSON body. */
export interface PlayerProfilePitchesApiResponse {
  pitches: StatcastPitch[];
}

/** Row in statcast_batting (SCHEMA.md). */
export interface StatcastBatting {
  id: number;
  player_id: number | null;
  player_name: string | null;
  team_id: number | null;
  season: number | null;
  /** Plate appearances / qualifying attempts (see SCHEMA.md); used for team weighting. */
  pa: number | null;
  avg_exit_velocity: number | null;
  max_exit_velocity: number | null;
  avg_launch_angle: number | null;
  barrel_rate: number | null;
  hard_hit_rate: number | null;
  xba: number | null;
  xslg: number | null;
  xwoba: number | null;
  sprint_speed: number | null;
  updated_at?: string | null;
}

/** GET /api/statcast/leaderboard row: batting row + resolved team abbreviation. */
export interface StatcastBattingLeaderboardRow extends StatcastBatting {
  /** Teams.abbreviation when team_id resolves; otherwise "—". */
  team_display: string;
}

/** Row in statcast_pitches (SCHEMA.md). */
export interface StatcastPitch {
  id: number;
  player_id: number | null;
  player_name: string | null;
  team_id: number | null;
  game_date: string | null;
  game_pk: number | null;
  pitch_type: string | null;
  pitch_name: string | null;
  release_speed: number | null;
  release_spin_rate: number | null;
  pfx_x: number | null;
  pfx_z: number | null;
  plate_x: number | null;
  plate_z: number | null;
  launch_angle: number | null;
  launch_speed: number | null;
  hit_distance: number | null;
  events: string | null;
  description: string | null;
  zone: number | null;
  stand: string | null;
  p_throws: string | null;
  home_team: string | null;
  away_team: string | null;
  created_at?: string | null;
}
