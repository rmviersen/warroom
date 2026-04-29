export interface Player {
    id: number;
    full_name: string;
    team: string;
    position: string;
    jersey_number?: string;
  }
  
  export interface Team {
    id: number;
    name: string;
    abbreviation: string;
    division: string;
    league: string;
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
