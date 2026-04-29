"use client";

import { FormEvent, useState } from "react";

import type { PlayerSearchHit } from "@/types";

export default function PlayersPage() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [players, setPlayers] = useState<PlayerSearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(search: string) {
    const q = search.trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    setSubmittedQuery(q);

    try {
      const res = await fetch(
        `/api/players?search=${encodeURIComponent(q)}`,
      );
      if (!res.ok) {
        if (res.status === 400) {
          setError("Invalid search request.");
        } else {
          setError("Could not search players. Try again later.");
        }
        setPlayers([]);
        return;
      }
      const data = (await res.json()) as { players?: PlayerSearchHit[] };
      setPlayers(data.players ?? []);
    } catch {
      setError("Something went wrong while searching.");
      setPlayers([]);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void runSearch(query);
  }

  const showEmptyPrompt = submittedQuery === null && !loading;
  const showNoResults =
    submittedQuery !== null && !loading && players.length === 0 && !error;

  return (
    <div className="space-y-8 max-w-3xl mx-auto">
      <header className="space-y-2 text-center sm:text-left">
        <h1 className="text-3xl sm:text-4xl font-black tracking-tight">
          <span className="text-red-500">WAR</span>
          <span className="text-white">room</span>
          <span className="text-gray-400 font-semibold text-2xl sm:text-3xl ml-2">
            Players
          </span>
        </h1>
        <p className="text-gray-500">
          Search the MLB player registry by name (Stats API).
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="flex flex-col sm:flex-row gap-3 rounded-xl border border-gray-800 bg-gray-900/50 p-4"
      >
        <label className="sr-only" htmlFor="player-search">
          Search players
        </label>
        <input
          id="player-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. Judge, Ohtani…"
          className="flex-1 rounded-lg bg-gray-950 border border-gray-800 px-4 py-3 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-red-500/40 focus:border-red-900/50"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-40 disabled:pointer-events-none text-white font-semibold px-6 py-3 text-sm transition-colors"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error ? (
        <div
          className="rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-3 text-red-200 text-sm"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 py-16 flex flex-col items-center justify-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-red-500 border-t-transparent animate-spin" />
          <p className="text-sm text-gray-500">Searching MLB rosters…</p>
        </div>
      ) : null}

      {showEmptyPrompt ? (
        <div className="rounded-xl border border-dashed border-gray-800 bg-gray-900/20 py-16 px-6 text-center">
          <p className="text-gray-500 text-sm">
            Search for a player by name to see matches from the MLB Stats API.
          </p>
        </div>
      ) : null}

      {showNoResults ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/30 py-12 text-center">
          <p className="text-gray-400 text-sm">No players found for that name.</p>
        </div>
      ) : null}

      {!loading && players.length > 0 ? (
        <ul className="space-y-2">
          {players.map((p) => (
            <li
              key={p.id}
              className="rounded-xl border border-gray-800 bg-gray-900/50 px-4 py-4 hover:border-gray-700 transition-colors"
            >
              <p className="text-white font-medium">
                {p.fullName ?? "Unknown player"}
              </p>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                <span>
                  Team:{" "}
                  <span className="text-gray-300">
                    {p.currentTeam?.name ?? "—"}
                  </span>
                </span>
                <span>
                  Position:{" "}
                  <span className="text-gray-300 font-mono">
                    {p.primaryPosition?.abbreviation ??
                      p.primaryPosition?.name ??
                      "—"}
                  </span>
                </span>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
