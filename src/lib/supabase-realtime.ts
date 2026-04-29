"use client";

import { useEffect, useRef, useState } from "react";

import { supabase } from "@/lib/supabase";
import type { StatcastPitch } from "@/types";

const CHANNEL = "warroom-statcast-pitches";

function logRealtimeStatus(status: string, err?: unknown) {
  if (err != null) {
    const msg = err instanceof Error ? err.message : String(err);
    console.log(`[statcast_pitches realtime] ${status}`, msg);
  } else {
    console.log(`[statcast_pitches realtime] ${status}`);
  }
}

function toNum(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Normalize Supabase Realtime row payload to StatcastPitch. */
function mapRealtimePitchRow(
  record: Record<string, unknown>,
): StatcastPitch {
  return {
    id: toNum(record.id) ?? 0,
    player_id: toNum(record.player_id),
    player_name:
      record.player_name == null ? null : String(record.player_name),
    team_id: toNum(record.team_id),
    game_date: record.game_date == null ? null : String(record.game_date),
    game_pk: toNum(record.game_pk),
    pitch_type:
      record.pitch_type == null ? null : String(record.pitch_type),
    pitch_name:
      record.pitch_name == null ? null : String(record.pitch_name),
    release_speed: toNum(record.release_speed),
    release_spin_rate: toNum(record.release_spin_rate),
    pfx_x: toNum(record.pfx_x),
    pfx_z: toNum(record.pfx_z),
    plate_x: toNum(record.plate_x),
    plate_z: toNum(record.plate_z),
    launch_angle: toNum(record.launch_angle),
    launch_speed: toNum(record.launch_speed),
    hit_distance: toNum(record.hit_distance),
    events: record.events == null ? null : String(record.events),
    description:
      record.description == null ? null : String(record.description),
    zone: toNum(record.zone),
    stand: record.stand == null ? null : String(record.stand),
    p_throws: record.p_throws == null ? null : String(record.p_throws),
    home_team:
      record.home_team == null ? null : String(record.home_team),
    away_team:
      record.away_team == null ? null : String(record.away_team),
    created_at:
      record.created_at == null ? null : String(record.created_at),
  };
}

/**
 * Subscribes to INSERT events on `statcast_pitches` for live pipeline updates.
 * `onNewPitch` always receives the latest closure via ref (stable subscription).
 */
export function useStatcastRealtime(onNewPitch: (row: StatcastPitch) => void): {
  isLive: boolean;
} {
  const onNewPitchRef = useRef(onNewPitch);
  onNewPitchRef.current = onNewPitch;

  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const channel = supabase
      .channel(CHANNEL)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "statcast_pitches",
        },
        (payload) => {
          const raw = payload.new as Record<string, unknown>;
          if (!raw || typeof raw !== "object") return;
          const row = mapRealtimePitchRow(raw);
          onNewPitchRef.current(row);
        },
      )
      .subscribe((status, err) => {
        logRealtimeStatus(status, err);
        if (cancelled) return;
        setIsLive(status === "SUBSCRIBED");
        if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          setIsLive(false);
        }
      });

    return () => {
      cancelled = true;
      logRealtimeStatus("CLOSED (cleanup)");
      void supabase.removeChannel(channel);
    };
  }, []);

  return { isLive };
}
