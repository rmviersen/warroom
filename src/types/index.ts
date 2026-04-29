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
  
export interface StatcastPitch {
  id?: number;
  player_id: number;
  player_name: string;
  game_date: string;
  pitch_type: string;
  release_speed: number;
  launch_angle?: number;
  launch_speed?: number;
  events?: string;
}
