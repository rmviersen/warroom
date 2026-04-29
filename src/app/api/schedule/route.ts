import { NextResponse } from 'next/server';

import { mlbFetch } from '@/lib/mlb-api';

function todayYmdLocal(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export async function GET() {
  try {
    const date = todayYmdLocal();
    const data = (await mlbFetch(
      `/schedule?sportId=1&date=${date}&hydrate=team,linescore`,
    )) as { dates?: unknown[] };
    return NextResponse.json({ dates: data.dates ?? [] });
  } catch {
    return NextResponse.json(
      { error: 'Failed to fetch schedule from MLB API' },
      { status: 500 },
    );
  }
}
