"use client";

import Image from "next/image";
import { useState } from "react";

import { getPlayerHeadshotUrl } from "@/lib/mlb-images";
import type { PlayerProfileApiResponse } from "@/types";

function computeAge(
  birthDate: string | null | undefined,
  mlbAge: unknown,
): string {
  if (mlbAge != null && Number.isFinite(Number(mlbAge))) {
    return String(Math.trunc(Number(mlbAge)));
  }
  if (!birthDate) return "—";
  const born = new Date(birthDate);
  if (Number.isNaN(born.getTime())) return "—";
  const today = new Date();
  let age = today.getFullYear() - born.getFullYear();
  const monthDelta = today.getMonth() - born.getMonth();
  if (monthDelta < 0 || (monthDelta === 0 && today.getDate() < born.getDate())) {
    age -= 1;
  }
  return String(age);
}

function handCode(side: unknown): string | null {
  if (side == null) return null;
  if (typeof side === "object" && side !== null && "code" in side) {
    const c = (side as { code?: string }).code;
    return c?.trim() ? c.trim().toUpperCase() : null;
  }
  const s = String(side).trim();
  return s ? s.toUpperCase() : null;
}

export default function PlayerProfileBanner({
  profile,
  playerId,
  season,
}: {
  profile: PlayerProfileApiResponse;
  playerId: number;
  season: number;
}) {
  const [hidePhoto, setHidePhoto] = useState(false);

  const person = profile.player;
  const db = profile.supabasePlayer;

  const fullName =
    (person?.fullName != null ? String(person.fullName) : null) ??
    db?.full_name?.trim() ??
    `Player ${playerId}`;

  const pos =
    (person?.primaryPosition as { abbreviation?: string } | undefined)
      ?.abbreviation ??
    db?.position ??
    "—";

  const team =
    (person?.currentTeam as { name?: string } | undefined)?.name ??
    db?.team ??
    "—";

  const bats =
    handCode(person?.batSide) ?? db?.bats?.trim()?.toUpperCase() ?? "—";
  const throws =
    handCode(person?.pitchHand) ?? db?.throws?.trim()?.toUpperCase() ?? "—";

  const age = computeAge(db?.birth_date, person?.currentAge);

  return (
    <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 p-3">
        {!hidePhoto ? (
          <span className="relative h-16 w-16 shrink-0 overflow-hidden rounded-full border-2 border-[#d0daea] bg-white">
            <Image
              src={getPlayerHeadshotUrl(playerId)}
              alt=""
              fill
              className="object-cover object-top"
              sizes="64px"
              onError={() => setHidePhoto(true)}
            />
          </span>
        ) : (
          <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border-2 border-[#d0daea] bg-white text-base font-bold text-[#7a8fa8]">
            {fullName.charAt(0)}
          </span>
        )}

        <div className="min-w-0 flex-1 space-y-1.5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-[#7a8fa8]">
              {team}
            </p>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[#0f2044] truncate">
              {fullName}
            </h1>
          </div>

          <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs sm:text-sm">
            <div className="flex gap-1.5">
              <dt className="text-[#7a8fa8]">Pos</dt>
              <dd className="font-mono font-semibold text-[#0f2044]">{pos}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-[#7a8fa8]">Age</dt>
              <dd className="font-mono tabular-nums text-[#0f2044]">{age}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-[#7a8fa8]">B/T</dt>
              <dd className="font-mono tabular-nums text-[#0f2044]">
                {bats}/{throws}
              </dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-[#7a8fa8]">Season</dt>
              <dd className="font-mono tabular-nums font-semibold text-[#0f2044]">
                {season}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
