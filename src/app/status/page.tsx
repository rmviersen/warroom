"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { RagStatus, StatusApiResponse, StatusCheck, StatusCategory } from "@/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 60_000;

const CATEGORY_LABELS: Record<StatusCategory, string> = {
  pitch_ingest: "Pitch Ingest",
  season_seeds: "Season Seeds",
  wpr_health:   "WPR Health",
};

const CATEGORY_ORDER: StatusCategory[] = [
  "pitch_ingest",
  "season_seeds",
  "wpr_health",
];

const RAG_CONFIG: Record<
  RagStatus,
  { dot: string; badge: string; label: string }
> = {
  green: { dot: "#22c55e", badge: "#dcfce7", label: "LIVE"  },
  amber: { dot: "#f59e0b", badge: "#fef9c3", label: "STALE" },
  red:   { dot: "#ef4444", badge: "#fee2e2", label: "DOWN"  },
};

const RAG_TEXT: Record<RagStatus, string> = {
  green: "#15803d",
  amber: "#92400e",
  red:   "#991b1b",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RagDot({ status }: { status: RagStatus }) {
  const color = RAG_CONFIG[status].dot;
  return (
    <span
      className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 mt-0.5"
      style={{ backgroundColor: color }}
      aria-hidden="true"
    />
  );
}

function RagBadge({ status }: { status: RagStatus }) {
  const { badge, label } = RAG_CONFIG[status];
  const textColor = RAG_TEXT[status];
  return (
    <span
      className="inline-block text-[10px] font-bold tracking-widest px-2 py-0.5 rounded"
      style={{ backgroundColor: badge, color: textColor }}
    >
      {label}
    </span>
  );
}

function SummaryBanner({
  summary,
}: {
  summary: StatusApiResponse["summary"];
}) {
  const total = summary.green + summary.amber + summary.red;
  const allGreen = summary.amber === 0 && summary.red === 0;

  return (
    <div
      className="rounded-xl border px-5 py-4 flex flex-wrap items-center gap-x-6 gap-y-2"
      style={{
        backgroundColor: allGreen ? "#f0fdf4" : summary.red > 0 ? "#fff1f2" : "#fefce8",
        borderColor:     allGreen ? "#bbf7d0" : summary.red > 0 ? "#fecdd3" : "#fef08a",
      }}
    >
      <p
        className="text-sm font-semibold"
        style={{ color: allGreen ? "#15803d" : summary.red > 0 ? "#991b1b" : "#92400e" }}
      >
        {allGreen
          ? `All ${total} checks healthy`
          : `${summary.red} issue${summary.red !== 1 ? "s" : ""} detected`}
      </p>
      <div className="flex items-center gap-4 text-sm">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
          <span className="text-[#374151]">{summary.green} live</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-amber-400" />
          <span className="text-[#374151]">{summary.amber} stale</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
          <span className="text-[#374151]">{summary.red} down</span>
        </span>
      </div>
    </div>
  );
}

function CheckRow({ check }: { check: StatusCheck }) {
  return (
    <div className="flex items-start gap-3 py-3 px-4 border-b border-[#f0f4f9] last:border-0 hover:bg-[#f9fbfd] transition-colors">
      <RagDot status={check.status} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[#0f2044] leading-snug">
          {check.label}
        </p>
        <p className="text-xs text-[#7a8fa8] mt-0.5 truncate">{check.detail}</p>
      </div>
      <RagBadge status={check.status} />
    </div>
  );
}

function CategorySection({
  category,
  checks,
  season,
}: {
  category: StatusCategory;
  checks: StatusCheck[];
  season: number;
}) {
  if (checks.length === 0) return null;

  const worstStatus: RagStatus =
    checks.some((c) => c.status === "red")
      ? "red"
      : checks.some((c) => c.status === "amber")
      ? "amber"
      : "green";

  const headerSuffix =
    category !== "pitch_ingest" ? ` · ${season}` : "";

  return (
    <section>
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#d0daea] bg-[#f4f7fb]">
        <RagDot status={worstStatus} />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[#0f2044]">
          {CATEGORY_LABELS[category]}
          <span className="font-normal text-[#7a8fa8]">{headerSuffix}</span>
        </h2>
      </div>
      <div>
        {checks.map((c) => (
          <CheckRow key={c.id} check={c} />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Countdown helper
// ---------------------------------------------------------------------------

function useCountdown(targetMs: number | null): number {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    if (targetMs === null) return;
    const tick = () =>
      setSecs(Math.max(0, Math.ceil((targetMs - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetMs]);
  return secs;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function StatusPage() {
  const [data, setData] = useState<StatusApiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const nextRefreshAt = useRef<number | null>(null);
  const [nextRefreshMs, setNextRefreshMs] = useState<number | null>(null);
  const countdown = useCountdown(nextRefreshMs);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as StatusApiResponse;
      setData(json);
      const next = Date.now() + REFRESH_INTERVAL_MS;
      nextRefreshAt.current = next;
      setNextRefreshMs(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  // Auto-refresh
  useEffect(() => {
    const id = setInterval(() => void fetchStatus(), REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const generatedAt = data?.generatedAt
    ? new Date(data.generatedAt).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })
    : null;

  const checksByCategory =
    data?.checks.reduce<Partial<Record<StatusCategory, StatusCheck[]>>>(
      (acc, c) => {
        (acc[c.category] ??= []).push(c);
        return acc;
      },
      {},
    ) ?? {};

  return (
    <div className="bg-white text-[#1e3050] max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <header className="space-y-1 border-b border-[#d0daea] pb-6">
        <p className="text-xs font-black tracking-tight">
          <span className="text-[#b8922a]">WAR</span>
          <span className="text-[#0f2044]">room</span>
        </p>
        <h1 className="text-3xl font-black tracking-tight text-[#0f2044]">
          Pipeline Status
        </h1>
        <p className="text-sm text-[#7a8fa8]">
          Live health check across all data sources. Refreshes every 60 seconds.
        </p>
      </header>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-[#7a8fa8] space-y-0.5">
          {generatedAt ? (
            <p>Last checked: <span className="text-[#0f2044] font-medium">{generatedAt}</span></p>
          ) : null}
          {!loading && countdown > 0 ? (
            <p>Next refresh in <span className="font-mono tabular-nums">{countdown}s</span></p>
          ) : null}
        </div>
        <button
          onClick={() => void fetchStatus()}
          disabled={loading}
          className="rounded-lg border border-[#d0daea] bg-[#f4f7fb] hover:bg-[#e8eef5] disabled:opacity-50 disabled:pointer-events-none px-4 py-2 text-sm font-medium text-[#0f2044] transition-colors"
        >
          {loading ? "Checking…" : "Refresh now"}
        </button>
      </div>

      {/* Error state */}
      {!loading && error ? (
        <div
          className="rounded-xl border border-[#fecdd3] bg-[#fff1f2] px-4 py-3 text-sm text-[#991b1b]"
          role="alert"
        >
          Could not load status: {error}
        </div>
      ) : null}

      {/* Loading skeleton */}
      {loading && !data ? (
        <div className="rounded-xl border border-[#d0daea] bg-[#f4f7fb] py-20 flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-[#1e3a6b] border-t-transparent animate-spin" />
          <p className="text-sm text-[#7a8fa8]">Querying data sources…</p>
        </div>
      ) : null}

      {/* Summary banner */}
      {data ? (
        <>
          <SummaryBanner summary={data.summary} />

          {/* RAG grid */}
          <div className="rounded-xl border border-[#d0daea] overflow-hidden divide-y divide-[#d0daea]">
            {CATEGORY_ORDER.map((cat) => (
              <CategorySection
                key={cat}
                category={cat}
                checks={checksByCategory[cat] ?? []}
                season={data.season}
              />
            ))}
          </div>

          {/* Footer note */}
          <p className="text-xs text-[#7a8fa8] text-center pb-4">
            Pitch ingest: green ≤ 2 days old, amber 3–5 days, red &gt; 5 days.
            Season seeds &amp; WPR health: green ≥ 100 rows, amber 1–99, red = 0.
          </p>
        </>
      ) : null}
    </div>
  );
}
