"use client";

import { X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { BlockChart } from "@/components/block-chart";
import { DataTable } from "@/components/data-table";
import { api, type ChartSpec, type Row } from "@/lib/api";
import { Flag, FlagName } from "@/components/flag";

const DEFAULT_COUNTRIES = ["FRA", "DEU", "ITA"];

export default function Explore() {
  const [countries, setCountries] = useState<Row[]>([]);
  const [indicators, setIndicators] = useState<Row[]>([]);
  const [indicator, setIndicator] = useState("GDP per capita");
  const [selected, setSelected] = useState<string[]>(DEFAULT_COUNTRIES);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForecast, setShowForecast] = useState(false);
  const [horizon, setHorizon] = useState(5);
  const [forecasts, setForecasts] = useState<
    Record<string, { forecast: { t: number; period: string; value: number; lo: number; hi: number }[]; disclaimer: string; method: string }>
  >({});

  useEffect(() => {
    Promise.all([
      api<{ rows: Row[] }>("/api/countries"),
      api<{ rows: Row[] }>("/api/indicators"),
    ])
      .then(([c, i]) => {
        setCountries(c.rows);
        setIndicators(i.rows);
      })
      .catch((e) => setError(e.message));
  }, []);

  const load = useCallback(async (ind: string, isos: string[]) => {
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(
        isos.map((iso) =>
          api<{ rows: Row[] }>(
            `/api/series?indicator=${encodeURIComponent(ind)}&country=${iso}`,
          ),
        ),
      );
      setRows(results.flatMap((r) => r.rows));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (indicator && selected.length) void load(indicator, selected);
    else setRows([]);
  }, [indicator, selected, load]);

  useEffect(() => {
    if (!showForecast || !indicator || !selected.length) {
      setForecasts({});
      return;
    }
    let cancelled = false;
    Promise.all(
      selected.map((iso) =>
        api<{ forecast: { t: number; period: string; value: number; lo: number; hi: number }[]; disclaimer: string; method: string }>(
          `/api/forecast?indicator=${encodeURIComponent(indicator)}&country=${iso}&horizon=${horizon}`,
        )
          .then((r) => [iso, r] as const)
          .catch(() => [iso, null] as const),
      ),
    ).then((entries) => {
      if (cancelled) return;
      const map: typeof forecasts = {};
      for (const [iso, r] of entries) if (r) map[iso] = r;
      setForecasts(map);
    });
    return () => {
      cancelled = true;
    };
  }, [showForecast, indicator, selected, horizon]);

  const meta = indicators.find((i) => i.name === indicator);
  const unit = rows.length ? String(rows[0].unit ?? "") : "";
  const sources = [...new Set(rows.map((r) => String(r.source)))];

  const spec: ChartSpec | null = rows.length
    ? {
        kind: "line",
        unit,
        series: selected
          .map((iso) => ({
            name: String(rows.find((r) => r.iso3 === iso)?.country ?? iso),
            points: rows
              .filter((r) => r.iso3 === iso)
              .map((r) => ({ x: r.year as number, y: r.value as number })),
          }))
          .filter((s) => s.points.length),
      }
    : null;

  const COLORS = [
    "#2563eb", "#dc2626", "#16a34a", "#9333ea",
    "#ea580c", "#0891b2", "#ca8a04", "#db2777",
  ];
  const specWithForecast: ChartSpec | null =
    spec && showForecast
      ? {
          ...spec,
          series: [
            ...spec.series.map((s, i) => ({ ...s, color: COLORS[i % COLORS.length] })),
            ...selected.flatMap((iso, i) => {
              const f = forecasts[iso];
              if (!f) return [];
              const hist = rows.filter((r) => r.iso3 === iso && r.value !== null);
              const lastX = hist.length ? (hist[hist.length - 1].year as number) : null;
              const lastY = hist.length ? (hist[hist.length - 1].value as number) : null;
              const color = COLORS[i % COLORS.length];
              // include the last history point so the dashed line connects
              const points = [
                ...(lastX !== null ? [{ x: lastX, y: lastY }] : []),
                ...f.forecast.map((p) => ({ x: p.t, y: p.value })),
              ];
              const band = f.forecast.map((p) => ({ x: p.t, lo: p.lo, hi: p.hi }));
              return [{ name: `${iso} forecast`, points, dashed: true, color, band }];
            }),
          ],
        }
      : spec;

  const latestByCountry = selected.map((iso) => {
    const c = rows.filter((r) => r.iso3 === iso);
    return c.length ? c[c.length - 1] : null;
  });

  // Per-country first/last non-null points, in the API's chronological order,
  // used to detail the situation two extra ways: a current-value ranking and
  // the net change over each country's covered span.
  const perCountry = selected
    .map((iso) => {
      const pts = rows.filter((r) => r.iso3 === iso && r.value !== null);
      return {
        iso,
        country: String(pts[0]?.country ?? iso),
        first: pts[0] ?? null,
        last: pts[pts.length - 1] ?? null,
      };
    })
    .filter((c) => c.last !== null);

  const latestYear = perCountry.length
    ? Math.max(...perCountry.map((c) => Number(c.last!.year)))
    : null;

  const rankSpec: ChartSpec | null = perCountry.length
    ? {
        kind: "bar",
        unit,
        title: latestYear ? `Latest value — ${latestYear}` : "Latest value",
        series: [
          {
            name: indicator,
            points: [...perCountry]
              .sort((a, b) => Number(b.last!.value) - Number(a.last!.value))
              .map((c) => ({ x: c.iso, y: c.last!.value as number })),
          },
        ],
      }
    : null;

  const changeSpec: ChartSpec | null = perCountry.some((c) => c.first !== c.last)
    ? {
        kind: "bar",
        unit,
        title: "Net change over available years",
        series: [
          {
            name: "change",
            points: perCountry.map((c) => ({
              x: c.iso,
              y:
                c.first && c.last
                  ? (c.last.value as number) - (c.first.value as number)
                  : null,
            })),
          },
        ],
      }
    : null;

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Explore</h1>

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
          value=""
          onChange={(e) => {
            const iso = e.target.value;
            if (iso && !selected.includes(iso)) setSelected([...selected, iso]);
          }}
          className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          <option value="">+ add country…</option>
          {countries.map((c) => (
            <option key={String(c.iso3)} value={String(c.iso3)}>
              {String(c.name)}
            </option>
          ))}
        </select>

        <div className="flex flex-wrap gap-1.5">
          {selected.map((iso) => (
            <button
              key={iso}
              type="button"
              onClick={() => setSelected(selected.filter((s) => s !== iso))}
              className="inline-flex items-center gap-1 rounded-full bg-black/5 px-2.5 py-1 text-xs hover:bg-black/10 dark:bg-white/10 dark:hover:bg-white/15"
            >
              <Flag code={iso} className="h-3" /> {iso} <X className="h-3 w-3" />
            </button>
          ))}
        </div>

        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showForecast}
            onChange={(e) => setShowForecast(e.target.checked)}
          />
          Forecast →
        </label>
        {showForecast ? (
          <select
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
            className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
          >
            {[3, 5, 10].map((h) => (
              <option key={h} value={h}>
                +{h}
              </option>
            ))}
          </select>
        ) : null}
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
          <BlockChart spec={specWithForecast ?? spec} />
          <div className="text-xs text-black/50 dark:text-white/50">
            Source: {sources.join(", ")}
            {meta?.is_proxy ? (
              <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 font-medium text-amber-700 dark:text-amber-300">
                proxy — {String(meta.proxy_note ?? "stand-in for the official concept")}
              </span>
            ) : null}
            {meta?.definition ? <div className="mt-1">{String(meta.definition)}</div> : null}
          </div>
          {showForecast && Object.keys(forecasts).length ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800 dark:text-amber-200">
              {Object.values(forecasts)[0].disclaimer}
              {" "}Methods:{" "}
              {selected
                .filter((iso) => forecasts[iso])
                .map((iso) => `${iso}: ${forecasts[iso].method}`)
                .join(", ")}
              .
            </div>
          ) : null}
          {rankSpec || changeSpec ? (
            <div className="grid gap-6 sm:grid-cols-2">
              {rankSpec ? <BlockChart spec={rankSpec} horizontal /> : null}
              {changeSpec ? <BlockChart spec={changeSpec} /> : null}
            </div>
          ) : null}
          <DataTable
            columns={["country", "latest year", "value", "unit"]}
            rows={latestByCountry
              .filter((r): r is Row => r !== null)
              .map((r) => [
                <FlagName key={String(r.iso3)} value={r.country} />,
                r.year,
                r.value,
                r.unit,
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
