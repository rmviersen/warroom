const MLB_API_BASE = process.env.NEXT_PUBLIC_MLB_API_BASE;

export async function mlbFetch(endpoint: string) {
  const res = await fetch(`${MLB_API_BASE}${endpoint}`);
  if (!res.ok) throw new Error(`MLB API error: ${res.status}`);
  return res.json();
}

export async function getStandings(season: number = new Date().getFullYear()) {
  return mlbFetch(`/standings?leagueId=103,104&season=${season}&standingsTypes=regularSeason`);
}

export async function getTeams() {
  return mlbFetch(`/teams?sportId=1`);
}

export async function getPlayer(playerId: number) {
  return mlbFetch(`/people/${playerId}?hydrate=stats(group=[hitting,pitching],type=[season])`);
}
