"use client";

import { useEffect, useState } from "react";

import { BlockChart } from "@/components/block-chart-lazy";
import { DataTable } from "@/components/data-table";
import { api, type ChartSpec, type Row } from "@/lib/api";
import { FlagName } from "@/components/flag";

const TOP_OPTIONS = [5, 10, 20] as const;

export default function Ranking() {
  const [indicators, setIndicators] = useState<Row[]>([]);
  const [blocs, setBlocs] = useState<Row[]>([]);
  const [indicator, setIndicator] = useState("GDP per capita");
  const [bloc, setBloc] = useState("");
  const [top, setTop] = useState<number>(10);
  const [order, setOrder] = useState<"highest" | "lowest">("highest");
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<{ rows: Row[] }>("/api/indicators"),
      api<{ rows: Row[] }>("/api/blocs"),
    ])
      .then(([i, b]) => {
        setIndicators(i.rows);
        setBlocs(b.rows);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!indicator) return;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ indicator });
    if (bloc) params.set("bloc", bloc);
    api<{ rows: Row[] }>(`/api/latest?${params}`)
      .then((r) => setRows(r.rows))
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [indicator, bloc]);

  // /api/latest is sorted by value descending; slice from the wanted end.
  const ranked =
    order === "highest" ? rows.slice(0, top) : rows.slice(-top).reverse();

  const meta = indicators.find((i) => i.name === indicator);
  const unit = ranked.length ? String(ranked[0].unit ?? "") : "";
  const sources = [...new Set(ranked.map((r) => String(r.source)))];

  const spec: ChartSpec | null = ranked.length
    ? {
        kind: "bar",
        unit,
        title: `${order === "highest" ? "Top" : "Bottom"} ${ranked.length} — ${indicator}`,
        series: [
          {
            name: indicator,
            points: ranked.map((r) => ({
              x: String(r.iso3),
              y: r.value as number,
            })),
          },
        ],
      }
    : null;

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Ranking</h1>
      <p className="mt-1 text-sm text-black/50 dark:text-white/50">
        Rank European countries by any indicator, on its most recent value.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <select
          value={indicator}
          onChange={(e) => setIndicator(e.target.value)}
          className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          {indicators.map((i) => (
            <option key={String(i.name)} value={String(i.name)}>
              {String(i.domain)} · {String(i.name)}
            </option>
          ))}
        </select>

        <select
          value={bloc}
          onChange={(e) => setBloc(e.target.value)}
          className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          <option value="">All Europe</option>
          {blocs.map((b) => (
            <option key={String(b.code)} value={String(b.code)}>
              {String(b.name)}
            </option>
          ))}
        </select>

        <Segmented
          options={TOP_OPTIONS.map((n) => ({ value: String(n), label: `Top ${n}` }))}
          value={String(top)}
          onChange={(v) => setTop(Number(v))}
        />

        <Segmented
          options={[
            { value: "highest", label: "Highest" },
            { value: "lowest", label: "Lowest" },
          ]}
          value={order}
          onChange={(v) => setOrder(v as "highest" | "lowest")}
        />
      </div>

      {error ? (
        <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : null}

      {loading ? (
        <p className="mt-6 text-sm text-black/50 dark:text-white/50">Loading…</p>
      ) : spec ? (
        <div className="mt-6 space-y-4">
          <BlockChart spec={spec} horizontal />
          <div className="text-xs text-black/50 dark:text-white/50">
            Source: {sources.join(", ")}
            {meta?.is_proxy ? (
              <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 font-medium text-amber-700 dark:text-amber-300">
                proxy — {String(meta.proxy_note ?? "stand-in for the official concept")}
              </span>
            ) : null}
            {meta?.definition ? <div className="mt-1">{String(meta.definition)}</div> : null}
          </div>
          <DataTable
            columns={["rank", "country", "value", "unit", "year"]}
            rows={ranked.map((r, i) => [
              i + 1,
              <FlagName key={`c${i}`} value={r.country} />,
              r.value,
              r.unit,
              r.period ?? r.year,
            ])}
          />
        </div>
      ) : (
        <p className="mt-6 text-sm text-black/50 dark:text-white/50">
          No data for this selection.
        </p>
      )}
    </main>
  );
}

function Segmented({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex rounded-xl border border-black/15 p-0.5 dark:border-white/20">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={
            o.value === value
              ? "rounded-[10px] bg-black/10 px-3 py-1.5 text-sm font-medium dark:bg-white/15"
              : "rounded-[10px] px-3 py-1.5 text-sm text-black/60 hover:bg-black/5 dark:text-white/60 dark:hover:bg-white/10"
          }
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
