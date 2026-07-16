"use client";

import Link from "next/link";
import { ExternalLink, GitBranch, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { CountryPopup, KPI_INDICATORS, type KpiData } from "@/components/country-popup";
import { EUROPEAN_MARKERS, type CountryMarker } from "@/components/european-markers";
import { Globe } from "@/components/ui/globe";
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
    href: "/explore",
    body: "Trend projections per indicator with an uncertainty band, available as an overlay in Explore and via the AI analyst.",
  },
  {
    title: "More domains",
    href: "/explore",
    body: "Health, AI & Innovation, Startups & Investment, and Social Media.",
  },
  {
    title: "Sub-national data",
    body:
      "NUTS-region breakdowns below the country level. First indicator live in the " +
      "database (GDP per capita, 285 NUTS 2 regions) — not yet browsable in Explore.",
  },
] as const;

type KpiCache = Map<string, Map<string, Row>>;

export default function Home() {
  const [sources, setSources] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [selectedCountry, setSelectedCountry] = useState<CountryMarker | null>(null);
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const [countryData, setCountryData] = useState<KpiData | null>(null);
  const [loading, setLoading] = useState(false);
  const [kpiError, setKpiError] = useState<string | null>(null);
  // One /api/latest fetch per KPI covers every country; the shared promise
  // means concurrent first clicks reuse the same in-flight batch.
  const kpiCacheRef = useRef<Promise<KpiCache> | null>(null);

  useEffect(() => {
    api<{ rows: Row[] }>("/api/sources")
      .then((src) => setSources(src.rows))
      .catch((e) => setError(e.message));
  }, []);

  const closePopup = useCallback(() => {
    setSelectedCountry(null);
    setAnchor(null);
  }, []);

  const handleMarkerClick = useCallback((marker: CountryMarker, pos: { x: number; y: number }) => {
    setSelectedCountry(marker);
    setAnchor(pos);
    setKpiError(null);
    kpiCacheRef.current ??= Promise.all(
      KPI_INDICATORS.map((k) =>
        api<{ rows: Row[] }>(`/api/latest?indicator=${encodeURIComponent(k)}`),
      ),
    ).then((results) => {
      const cache: KpiCache = new Map();
      KPI_INDICATORS.forEach((k, i) =>
        cache.set(k, new Map(results[i].rows.map((r) => [String(r.iso3), r]))),
      );
      return cache;
    });
    setLoading(true);
    kpiCacheRef.current
      .then((cache) => {
        const data: KpiData = {};
        for (const k of KPI_INDICATORS) {
          const row = cache.get(k)?.get(marker.iso3);
          data[k] =
            row && row.value != null
              ? {
                  value: Number(row.value),
                  unit: row.unit == null ? null : String(row.unit),
                  period: String(row.period),
                }
              : null;
        }
        setCountryData(data);
      })
      .catch((e) => {
        kpiCacheRef.current = null; // let a later click retry
        setKpiError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
      <h1 className="sr-only">European data</h1>

      <section className="relative mx-auto w-full max-w-[600px]">
        <Globe
          markers={EUROPEAN_MARKERS}
          selectedId={selectedCountry?.id ?? null}
          paused={selectedCountry !== null}
          onMarkerClick={handleMarkerClick}
          onBackgroundClick={closePopup}
        />
        {selectedCountry && anchor && (
          <CountryPopup
            country={selectedCountry}
            anchor={anchor}
            data={countryData}
            loading={loading}
            error={kpiError}
            onClose={closePopup}
          />
        )}
      </section>

      {error ? (
        <div className="mt-8 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : (
        <>
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
