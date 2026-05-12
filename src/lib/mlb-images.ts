/** Placeholder until a default asset is chosen. */
export const FALLBACK_TEAM_LOGO = "";

/** Placeholder until a default asset is chosen. */
export const FALLBACK_PLAYER_HEADSHOT = "";

function normalizeId(id: number | string): string {
  return String(id).trim();
}

/**
 * MLB static CDN SVG logo for a team (MLBAM team id).
 * @see https://www.mlbstatic.com/team-logos/{teamId}.svg
 */
export function getTeamLogoUrl(teamId: number | string): string {
  return `https://www.mlbstatic.com/team-logos/${normalizeId(teamId)}.svg`;
}

/**
 * MLB CDN headshot JPG for a player (MLBAM player id), 60px tier.
 * @see https://img.mlb.com/headshots/current/60/{playerId}.jpg
 */
export function getPlayerHeadshotUrl(playerId: number | string): string {
  return `https://img.mlb.com/headshots/current/60/${normalizeId(playerId)}.jpg`;
}
