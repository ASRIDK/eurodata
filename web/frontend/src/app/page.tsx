"use client";

import Link from "next/link";
import { ExternalLink, GitBranch, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { api, type Row } from "@/lib/api";
import { cn } from "@/lib/utils";

const ROADMAP = [
  {
    title: "Correlation graph",
    href: "/correlations",
    body:
      "CORRELATES_WITH edges built the rigorous way: growth-rate/first-difference " +
      "correlation, multiple-comparison (FDR) correction, and lagged directionality " +
      "— not raw levels, which produce spurious relationships.",
  },
  {
    title: "Neuro engine",
    body:
      "Spreading-activation propagation over the correlation graph, to trace how a " +
      "shock to one indicator or country ripples through the others.",
  },
  {
    title: "Forecasting",
    body: "Trend projections per indicator, once the dataset's trustworthiness work is done.",
  },
  {
    title: "More domains",
    href: "/explore",
    body: "Health, AI & Innovation, Startups & Investment, and Social Media.",
  },
  {
    title: "Sub-national data",
    body:
      "NUTS-region breakdowns below the country level — the schema is already " +
      "forward-compatible for this.",
  },
] as const;

export default function Home() {
  const [years, setYears] = useState<[number, number] | null>(null);
  const [coverage, setCoverage] = useState<Row[]>([]);
  const [countries, setCountries] = useState<number | null>(null);
  const [sources, setSources] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<{ years: [number, number] }>("/api/health"),
      api<{ rows: Row[] }>("/api/coverage"),
      api<{ rows: Row[] }>("/api/countries"),
      api<{ rows: Row[] }>("/api/sources"),
    ])
      .then(([h, cov, c, src]) => {
        setYears(h.years);
        setCoverage(cov.rows);
        setCountries(c.rows.length);
        setSources(src.rows);
      })
      .catch((e) => setError(e.message));
  }, []);

  const populated = coverage.filter((r) => Number(r.rows) > 0);
  const totalRows = coverage.reduce((acc, r) => acc + Number(r.rows ?? 0), 0);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">
        European data
      </h1>
      <p className="mt-2 max-w-2xl text-black/60 dark:text-white/60">
        Official statistics on economy, demographics, digital, energy &amp;
        climate and AI &amp; technology — provenance-first, with a curated
        event layer.{" "}
        <Link href="/chat" className="font-medium underline underline-offset-4">
          Ask the AI analyst
        </Link>{" "}
        or{" "}
        <Link href="/explore" className="font-medium underline underline-offset-4">
          explore the data
        </Link>
        .
      </p>

      {error ? (
        <div className="mt-8 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : (
        <>
          <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Indicators with data" value={coverage.length ? String(populated.length) : "…"} />
            <Stat label="Countries" value={countries === null ? "…" : String(countries)} />
            <Stat label="Years" value={years ? `${years[0]}–${years[1]}` : "…"} />
            <Stat label="Data points" value={coverage.length ? totalRows.toLocaleString("en") : "…"} />
          </div>

          <h2 className="mb-1 mt-10 flex items-center gap-2 text-lg font-medium">
            <ShieldCheck className="h-5 w-5 text-black/50 dark:text-white/50" />
            Sources &amp; reliability
          </h2>
          <p className="mb-4 max-w-2xl text-sm text-black/50 dark:text-white/50">
            Every record keeps its source. When several sources cover the same
            indicator, eurodata keeps the reading from the source with the
            highest reliability score below.
          </p>
          {sources.length ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {sources.map((s) => (
                <SourceCard key={String(s.name)} source={s} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-black/50 dark:text-white/50">Loading…</p>
          )}

          <h2 className="mb-1 mt-10 flex items-center gap-2 text-lg font-medium">
            <GitBranch className="h-5 w-5 text-black/50 dark:text-white/50" />
            What&apos;s coming next
          </h2>
          <p className="mb-4 max-w-2xl text-sm text-black/50 dark:text-white/50">
            v1 focuses on getting the dataset right. These are deliberately
            deferred until they can be built properly.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {ROADMAP.map((r) => {
              const href = "href" in r ? r.href : null;
              const shipped = Boolean(href);
              const card = (
                <div
                  className={cn(
                    "h-full rounded-2xl border px-4 py-3",
                    shipped
                      ? "border-black/15 transition-colors hover:bg-black/[0.03] dark:border-white/20 dark:hover:bg-white/[0.04]"
                      : "border-black/10 dark:border-white/10",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{r.title}</span>
                    {shipped ? (
                      <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
                        shipped
                      </span>
                    ) : (
                      <span className="rounded-full bg-black/5 px-2 py-0.5 text-[11px] font-medium text-black/50 dark:bg-white/10 dark:text-white/50">
                        planned
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-black/50 dark:text-white/50">{r.body}</p>
                </div>
              );
              return href ? (
                <Link key={r.title} href={href}>
                  {card}
                </Link>
              ) : (
                <div key={r.title}>{card}</div>
              );
            })}
          </div>
        </>
      )}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-black/10 px-4 py-3 dark:border-white/10">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-black/50 dark:text-white/50">{label}</div>
    </div>
  );
}

function SourceCard({ source }: { source: Row }) {
  const score = Number(source.reliability_score ?? 0);
  const pct = Math.round(score * 100);
  return (
    <div className="rounded-2xl border border-black/10 px-4 py-3 dark:border-white/10">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium">{String(source.name)}</div>
          <div className="text-xs text-black/50 dark:text-white/50">
            {String(source.organization ?? "")}
          </div>
        </div>
        {source.url ? (
          <a
            href={String(source.url)}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 rounded-lg p-1 text-black/40 hover:bg-black/5 hover:text-black/70 dark:text-white/40 dark:hover:bg-white/10 dark:hover:text-white/70"
            aria-label={`Open ${String(source.name)} website`}
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        ) : null}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
          <div
            className="h-full rounded-full bg-emerald-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs font-medium tabular-nums text-black/60 dark:text-white/60">
          {pct}%
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-black/50 dark:text-white/50">
        <span>{String(source.license ?? "")}</span>
        <span>· updates {String(source.update_frequency ?? "—")}</span>
      </div>
    </div>
  );
}
