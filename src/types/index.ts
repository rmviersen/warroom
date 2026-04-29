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
