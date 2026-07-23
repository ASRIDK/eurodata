"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Flag } from "@/components/flag";
import { formatKpi, KPI_INDICATORS, type KpiData } from "@/components/country-popup";
import { api, type Row } from "@/lib/api";

type Correlation = {
  a: string;
  b: string;
  weight: number;
  arrow: string;
};

// "GDP" / "GDP per capita", "Unemployment Rate" / "Unemployment Rate (monthly)"
// — a pair where one name extends the other is the same underlying series at a
// different frequency or normalization, so its ~1.0 correlation is a tautology,
// not a finding. Strip parentheticals and compare stems.
function sameUnderlyingSeries(a: string, b: string): boolean {
  const stem = (s: string) => s.replace(/\s*\(.*?\)/g, "").trim().toLowerCase();
  const [x, y] = [stem(a), stem(b)];
  return x === y || x.startsWith(y) || y.startsWith(x);
}

export default function CountryProfile() {
  const params = useParams<{ iso3: string }>();
  const iso3 = params.iso3?.toUpperCase() ?? "";

  const [country, setCountry] = useState<Row | null>(null);
  const [blocs, setBlocs] = useState<Row[]>([]);
  const [kpis, setKpis] = useState<KpiData | null>(null);
  const [events, setEvents] = useState<Row[]>([]);
  const [correlations, setCorrelations] = useState<Correlation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!iso3) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-change: loading/error reset before the async load below
    setLoading(true);
    setError(null);

    Promise.all([
      api<{ rows: Row[] }>("/api/countries"),
      api<{ rows: Row[] }>(`/api/country-blocs?country=${iso3}`),
      Promise.all(
        KPI_INDICATORS.map((k) =>
          api<{ rows: Row[] }>(`/api/latest?indicator=${encodeURIComponent(k)}`)
            .then((r) => [k, r.rows.find((row) => row.iso3 === iso3)] as const)
            .catch(() => [k, undefined] as const),
        ),
      ),
      api<{ rows: Row[] }>(`/api/events?country=${iso3}`),
      api<{ rows: Row[] }>(`/api/country-indicators?country=${iso3}`),
    ])
      .then(([countriesRes, blocsRes, kpiEntries, eventsRes, indicatorsRes]) => {
        if (cancelled) return;
        const match = countriesRes.rows.find((r) => r.iso3 === iso3);
        setCountry(match ?? null);
        setBlocs(blocsRes.rows);
        const kpiData: KpiData = {};
        for (const [k, row] of kpiEntries) {
          kpiData[k] =
            row && row.value != null
              ? {
                  value: Number(row.value),
                  unit: row.unit == null ? null : String(row.unit),
                  period: String(row.period),
                }
              : null;
        }
        setKpis(kpiData);
        setEvents(
          [...eventsRes.rows]
            .sort((a, b) => String(b.start_date).localeCompare(String(a.start_date)))
            .slice(0, 6),
        );

        const ownIndicators = new Set(indicatorsRes.rows.map((r) => String(r.indicator)));
        return api<{ rows: Row[] }>("/api/correlation-graph").then((graphRes) => {
          if (cancelled) return;
          const top = graphRes.rows
            .filter(
              (r) =>
                ownIndicators.has(String(r.indicator_a)) &&
                ownIndicators.has(String(r.indicator_b)) &&
                !sameUnderlyingSeries(String(r.indicator_a), String(r.indicator_b)),
            )
            .map((r) => ({
              a: String(r.indicator_a),
              b: String(r.indicator_b),
              weight: Number(r.weight),
              arrow:
                r.direction === "a_leads_b" ? "→" : r.direction === "b_leads_a" ? "←" : "↔",
            }))
            .sort((x, y) => Math.abs(y.weight) - Math.abs(x.weight))
            .slice(0, 8);
          setCorrelations(top);
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [iso3]);

  if (!/^[A-Z]{3}$/.test(iso3)) {
    return (
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <p className="text-sm text-black/50 dark:text-white/50">Invalid country code.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
      {error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : loading ? (
        <p className="text-sm text-black/50 dark:text-white/50">Loading…</p>
      ) : !country ? (
        <p className="text-sm text-black/50 dark:text-white/50">
          No country found for &ldquo;{iso3}&rdquo;.
        </p>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <Flag code={iso3} className="h-7" />
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">
                {String(country.name)}
              </h1>
              <p className="text-xs text-black/40 dark:text-white/40">
                {iso3} · {String(country.iso2)}
              </p>
            </div>
          </div>

          {blocs.length ? (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {blocs.map((b) => (
                <span
                  key={String(b.bloc_code)}
                  className="rounded-full bg-black/5 px-2.5 py-1 text-xs dark:bg-white/10"
                >
                  {String(b.bloc_name)}
                  {b.until_year ? ` (until ${b.until_year})` : ` since ${b.since_year}`}
                </span>
              ))}
            </div>
          ) : null}

          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {KPI_INDICATORS.map((k) => {
              const v = kpis?.[k];
              return (
                <div
                  key={k}
                  className="rounded-xl border border-black/10 px-3 py-2.5 dark:border-white/10"
                >
                  <div className="text-xs text-black/50 dark:text-white/50">{k}</div>
                  {v ? (
                    <>
                      <div className="mt-0.5 text-lg font-semibold tabular-nums">
                        {formatKpi(v)}
                      </div>
                      <div className="text-[11px] text-black/35 dark:text-white/35">
                        {v.period}
                      </div>
                    </>
                  ) : (
                    <div className="mt-0.5 text-lg text-black/25 dark:text-white/25">—</div>
                  )}
                </div>
              );
            })}
          </div>

          <Link
            href={`/explore?country=${iso3}`}
            className="mt-4 inline-block text-sm font-medium underline underline-offset-4"
          >
            Explore full time series →
          </Link>

          <div className="mt-8 grid gap-8 sm:grid-cols-2">
            <section>
              <h2 className="text-sm font-semibold">Recent events</h2>
              {events.length ? (
                <ul className="mt-3 space-y-3">
                  {events.map((e) => (
                    <li key={String(e.code)} className="text-sm">
                      <div className="flex items-baseline gap-2">
                        <span className="text-xs tabular-nums text-black/40 dark:text-white/40">
                          {String(e.start_date).slice(0, 4)}
                        </span>
                        <span className="font-medium">{String(e.title)}</span>
                      </div>
                      {e.description ? (
                        <p className="mt-0.5 text-xs text-black/50 dark:text-white/50">
                          {String(e.description)}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-xs text-black/40 dark:text-white/40">
                  No curated events for {String(country.name)}.
                </p>
              )}
              <Link
                href="/events"
                className="mt-3 inline-block text-xs font-medium underline underline-offset-4"
              >
                Browse all events →
              </Link>
            </section>

            <section>
              <h2 className="text-sm font-semibold">Strongest correlations</h2>
              {/* correlation_graph is pooled across all countries — these are
                  Europe-wide relationships, narrowed to indicators this country
                  has data for, NOT correlations computed on its own series. */}
              <p className="mt-1 text-xs text-black/40 dark:text-white/40">
                Europe-wide, among indicators covered for {String(country.name)}
              </p>
              {correlations.length ? (
                <ul className="mt-3 space-y-2">
                  {correlations.map((c) => (
                    <li key={`${c.a}-${c.b}`} className="text-sm">
                      <span className="tabular-nums text-black/40 dark:text-white/40">
                        {c.weight >= 0 ? "+" : ""}
                        {c.weight.toFixed(2)}
                      </span>{" "}
                      {c.a} {c.arrow} {c.b}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-xs text-black/40 dark:text-white/40">
                  No significant correlations among indicators covered for{" "}
                  {String(country.name)}.
                </p>
              )}
              <Link
                href="/correlations"
                className="mt-3 inline-block text-xs font-medium underline underline-offset-4"
              >
                Browse full graph →
              </Link>
            </section>
          </div>
        </>
      )}
    </main>
  );
}
