"use client";

import { useEffect, useMemo, useState } from "react";

import { DataTable } from "@/components/data-table";
import { FlagName } from "@/components/flag";
import { api, type RevisionDigestRow, type Row } from "@/lib/api";

function fmt(n: number | null): string {
  if (n === null || Number.isNaN(n)) return "—";
  return Math.abs(n) >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function pct(n: number | null): string {
  return n === null || Number.isNaN(n) ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

export default function Revisions() {
  const [indicators, setIndicators] = useState<Row[]>([]);
  const [countries, setCountries] = useState<Row[]>([]);
  const [indicator, setIndicator] = useState("");
  const [country, setCountry] = useState("");
  const [rows, setRows] = useState<RevisionDigestRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<{ rows: Row[] }>("/api/indicators"),
      api<{ rows: Row[] }>("/api/countries"),
    ])
      .then(([i, c]) => {
        setIndicators(i.rows);
        setCountries(c.rows);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-change: flip the loading flag when filters change
    setLoading(true);
    setError(null);
    const qs = new URLSearchParams();
    if (indicator) qs.set("indicator", indicator);
    if (country) qs.set("country", country);
    api<{ rows: RevisionDigestRow[] }>(`/api/revisions-summary?${qs}`)
      .then((r) => {
        if (!cancelled) setRows(r.rows);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setRows([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [indicator, country]);

  // "Most-revised" leaderboard: how many periods each indicator has revised.
  const mostRevised = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of rows) counts.set(r.indicator, (counts.get(r.indicator) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  }, [rows]);

  const largest = rows.slice(0, 40); // already sorted by |pct_change| server-side

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Revisions</h1>
      <p className="mt-1 max-w-2xl text-sm text-black/50 dark:text-white/50">
        Official statistics get revised as sources restate earlier figures. This
        tracks every value that changed across data vintages — what the number
        was, what it became, and by how much.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <select
          value={indicator}
          onChange={(e) => setIndicator(e.target.value)}
          className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          <option value="">All indicators</option>
          {indicators.map((i) => (
            <option key={String(i.name)} value={String(i.name)}>
              {String(i.domain)} · {String(i.name)}
            </option>
          ))}
        </select>
        <select
          value={country}
          onChange={(e) => setCountry(e.target.value)}
          className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          <option value="">All countries</option>
          {countries.map((c) => (
            <option key={String(c.iso3)} value={String(c.iso3)}>
              {String(c.name)}
            </option>
          ))}
        </select>
      </div>

      {error ? (
        <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : loading ? (
        <p className="mt-6 text-sm text-black/50 dark:text-white/50">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="mt-6 text-sm text-black/50 dark:text-white/50">
          No revisions recorded for this selection.
        </p>
      ) : (
        <div className="mt-6 space-y-8">
          {mostRevised.length > 1 ? (
            <section>
              <h2 className="text-sm font-medium text-black/70 dark:text-white/70">
                Most-revised indicators
              </h2>
              <div className="mt-2 flex flex-wrap gap-2">
                {mostRevised.map(([name, n]) => (
                  <span
                    key={name}
                    className="inline-flex items-center gap-1.5 rounded-full bg-black/5 px-3 py-1 text-xs dark:bg-white/10"
                  >
                    {name}
                    <span className="rounded-full bg-black/10 px-1.5 font-medium dark:bg-white/15">
                      {n}
                    </span>
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          <section>
            <h2 className="text-sm font-medium text-black/70 dark:text-white/70">
              Largest revisions
            </h2>
            <div className="mt-2">
              <DataTable
                columns={["indicator", "country", "period", "first", "latest", "change", "as of"]}
                rows={largest.map((r) => [
                  r.indicator,
                  <FlagName key={`${r.indicator}-${r.country}-${r.period}`} value={r.country} />,
                  r.period,
                  fmt(r.first_value),
                  fmt(r.latest_value),
                  pct(r.pct_change),
                  String(r.latest_vintage).slice(0, 10),
                ])}
              />
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
