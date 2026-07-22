"use client";

import { useEffect, useState } from "react";

import { BlockChart } from "@/components/block-chart-lazy";
import { api, type ChartSpec, type Row } from "@/lib/api";

const TOP_OPTIONS = [20, 50, 100, "All"] as const;

export default function Correlations() {
  const [indicators, setIndicators] = useState<Row[]>([]);
  const [indicator, setIndicator] = useState("");
  const [top, setTop] = useState<(typeof TOP_OPTIONS)[number]>(50);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ rows: Row[] }>("/api/indicators")
      .then((r) => setIndicators(r.rows))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (indicator) params.set("indicator", indicator);
    api<{ rows: Row[] }>(`/api/correlation-graph?${params}`)
      .then((r) => setRows(r.rows))
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [indicator]);

  const shown = top === "All" ? rows : rows.slice(0, top);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Correlations</h1>
      <p className="mt-1 max-w-2xl text-sm text-black/50 dark:text-white/50">
        Indicator pairs whose year-over-year growth rates correlate across
        Europe, after Benjamini-Hochberg FDR correction. Arrows only appear
        when a per-country Granger causality test confirms a lead/lag
        direction one-sidedly; otherwise the pair just moves together.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <select
          value={indicator}
          onChange={(e) => setIndicator(e.target.value)}
          className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          <option value="">All pairs</option>
          {indicators.map((i) => (
            <option key={String(i.name)} value={String(i.name)}>
              {String(i.domain)} · {String(i.name)}
            </option>
          ))}
        </select>

        <div className="flex rounded-xl border border-black/15 p-0.5 dark:border-white/20">
          {TOP_OPTIONS.map((n) => (
            <button
              key={String(n)}
              type="button"
              onClick={() => setTop(n)}
              className={
                n === top
                  ? "rounded-[10px] bg-black/10 px-3 py-1.5 text-sm font-medium dark:bg-white/15"
                  : "rounded-[10px] px-3 py-1.5 text-sm text-black/60 hover:bg-black/5 dark:text-white/60 dark:hover:bg-white/10"
              }
            >
              {n === "All" ? "All" : `Top ${n}`}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : null}

      {loading ? (
        <p className="mt-6 text-sm text-black/50 dark:text-white/50">Loading…</p>
      ) : shown.length ? (
        <>
          <p className="mt-6 text-xs text-black/40 dark:text-white/40">
            {rows.length} pair{rows.length === 1 ? "" : "s"} survive FDR correction
            {indicator ? ` for ${indicator}` : ""}
            {top !== "All" && rows.length > shown.length ? ` — showing the strongest ${shown.length}` : ""}.
          </p>
          <div className="mt-3 grid grid-cols-1 gap-3">
            {shown.map((r, i) => (
              <CorrelationCard key={i} row={r} />
            ))}
          </div>
        </>
      ) : (
        <p className="mt-6 text-sm text-black/50 dark:text-white/50">
          No FDR-significant relationships for this selection.
        </p>
      )}
    </main>
  );
}

function CorrelationCard({ row }: { row: Row }) {
  const a = String(row.indicator_a);
  const b = String(row.indicator_b);
  const weight = Number(row.weight ?? 0);
  const direction = String(row.direction ?? "undetermined");
  const relationship = String(row.relationship ?? "contemporaneous");
  const qValue = Number(row.q_value ?? 0);
  const nCountries = row.n_countries;
  const domainA = String(row.domain_a ?? "");
  const domainB = String(row.domain_b ?? "");

  const arrow = direction === "a_leads_b" ? "→" : direction === "b_leads_a" ? "←" : "↔";
  const lagLabel = relationship === "contemporaneous" ? "same year" : "1-year lag";
  const positive = weight >= 0;
  const pct = Math.min(100, Math.round(Math.abs(weight) * 100));

  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-2xl border border-black/10 dark:border-white/10">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full rounded-2xl px-4 py-3 text-left transition-colors hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <div className="flex items-center gap-1.5 text-sm font-medium">
            <span
              className={`text-black/30 transition-transform dark:text-white/30 ${open ? "rotate-90" : ""}`}
              aria-hidden
            >
              ▸
            </span>
            <span>
              {a} <span className="text-black/40 dark:text-white/40">{arrow}</span> {b}
            </span>
          </div>
          <span
            className={
              positive
                ? "text-sm font-semibold tabular-nums text-emerald-600 dark:text-emerald-400"
                : "text-sm font-semibold tabular-nums text-red-600 dark:text-red-400"
            }
          >
            {positive ? "+" : ""}
            {weight.toFixed(3)}
          </span>
        </div>

        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
          <div
            className={positive ? "h-full rounded-full bg-emerald-500" : "h-full rounded-full bg-red-500"}
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-black/50 dark:text-white/50">
          <span>{domainA === domainB ? domainA : `${domainA} × ${domainB}`}</span>
          <span>· {lagLabel}</span>
          <span>· q={qValue < 0.0001 ? "<0.0001" : qValue.toFixed(4)}</span>
          <span>· {nCountries} countries</span>
        </div>
      </button>

      {open ? (
        <div className="border-t border-black/10 px-4 py-3 dark:border-white/10">
          <TrendComparison a={a} b={b} />
        </div>
      ) : null}
    </div>
  );
}

function TrendComparison({ a, b }: { a: string; b: string }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    const params = new URLSearchParams({ indicators: `${a},${b}` });
    api<{ rows: Row[] }>(`/api/indicator-trend?${params}`)
      .then((r) => {
        if (!cancelled) setRows(r.rows);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [a, b]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs">
        {error}
      </div>
    );
  }
  if (rows === null) {
    return <p className="text-xs text-black/50 dark:text-white/50">Loading trend…</p>;
  }
  if (!rows.length) {
    return (
      <p className="text-xs text-black/50 dark:text-white/50">
        No overlapping years to chart for this pair.
      </p>
    );
  }

  const baseYear = rows[0]?.base_year;
  const build = (name: string) => ({
    name,
    points: rows
      .filter((r) => r.indicator === name)
      .map((r) => ({ x: Number(r.year), y: r.value as number | null })),
  });
  const spec: ChartSpec = {
    kind: "line",
    unit: `European median · indexed to 100 at ${baseYear}`,
    title: null,
    series: [build(a), build(b)],
  };

  return (
    <div>
      <BlockChart spec={spec} />
      <p className="mt-1 text-xs text-black/40 dark:text-white/40">
        Cross-country median for each indicator, rebased so both start at 100 —
        the shape shows how they move together (or apart) over time, not their
        real units.
      </p>
    </div>
  );
}
