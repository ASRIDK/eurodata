"use client";

import { X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { BlockChart } from "@/components/block-chart-lazy";
import { DataTable } from "@/components/data-table";
import { api, type ChartSpec, type Row } from "@/lib/api";
import { Flag, FlagName } from "@/components/flag";
import { disagreements, SourceComparison } from "@/components/source-comparison";

const DEFAULT_COUNTRIES = ["FRA", "DEU", "ITA"];
// Starter comparison for sub-national indicators: Île-de-France, Oberbayern,
// Lombardia, Comunidad de Madrid.
const DEFAULT_REGIONS = ["FR10", "DE21", "ITC4", "ES30"];

export default function Explore() {
  const [countries, setCountries] = useState<Row[]>([]);
  const [indicators, setIndicators] = useState<Row[]>([]);
  const [regions, setRegions] = useState<Row[]>([]);
  // indicators whose data is per NUTS 2 region rather than per country
  const [nutsIndicators, setNutsIndicators] = useState<Set<string>>(new Set());
  const [indicator, setIndicator] = useState("GDP per capita");
  const [selected, setSelected] = useState<string[]>(DEFAULT_COUNTRIES);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<Row[]>([]);
  const [showEvents, setShowEvents] = useState(true);
  const [provenance, setProvenance] = useState<Record<string, Row[]>>({});
  const [showForecast, setShowForecast] = useState(false);
  const [horizon, setHorizon] = useState(5);
  const [forecasts, setForecasts] = useState<
    Record<string, { forecast: { t: number; period: string; value: number; lo: number; hi: number }[]; disclaimer: string; method: string }>
  >({});

  useEffect(() => {
    // deep link from the home-page globe popup: /explore?country=FRA.
    // Read post-hydration (an initializer would mismatch the prerendered
    // HTML); a one-shot mount read cannot cascade.
    const c = new URLSearchParams(window.location.search).get("country")?.toUpperCase();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (c && /^[A-Z]{3}$/.test(c)) setSelected([c]);
    Promise.all([
      api<{ rows: Row[] }>("/api/countries"),
      api<{ rows: Row[] }>("/api/indicators"),
      api<{ rows: Row[] }>("/api/coverage"),
    ])
      .then(([c, i, cov]) => {
        setCountries(c.rows);
        setIndicators(i.rows);
        setNutsIndicators(
          new Set(
            cov.rows
              .filter((r) => r.geo_level === "NUTS2")
              .map((r) => String(r.indicator)),
          ),
        );
      })
      .catch((e) => setError(e.message));
  }, []);

  const isRegional = nutsIndicators.has(indicator);

  useEffect(() => {
    if (!isRegional || regions.length) return;
    api<{ rows: Row[] }>("/api/regions")
      .then((r) => setRegions(r.rows))
      .catch((e) => setError(e.message));
  }, [isRegional, regions.length]);

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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-change: load() flips the loading flag, the else clears stale rows
    if (indicator && selected.length) void load(indicator, selected);
    else setRows([]);
  }, [indicator, selected, load]);

  useEffect(() => {
    if (!showForecast || !indicator || !selected.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clearing stale forecasts when the overlay turns off
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

  useEffect(() => {
    // Event markers only make sense for country-level time series, not
    // NUTS 2 regions (no per-region event data) or the rank/change charts.
    if (isRegional || !selected.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clearing stale markers when the selection stops qualifying
      setEvents([]);
      return;
    }
    let cancelled = false;
    Promise.all(
      selected.map((iso) =>
        api<{ rows: Row[] }>(`/api/events?country=${iso}`).catch(() => ({ rows: [] })),
      ),
    ).then((results) => {
      if (cancelled) return;
      const byCode = new Map<string, Row>();
      for (const r of results.flatMap((r) => r.rows)) byCode.set(String(r.code), r);
      setEvents([...byCode.values()]);
    });
    return () => {
      cancelled = true;
    };
  }, [isRegional, selected]);

  useEffect(() => {
    if (isRegional || !indicator || !selected.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clearing stale provenance when the selection stops qualifying
      setProvenance({});
      return;
    }
    let cancelled = false;
    Promise.all(
      selected.map((iso) =>
        api<{ rows: Row[] }>(
          `/api/provenance?indicator=${encodeURIComponent(indicator)}&country=${iso}`,
        )
          .then((r) => [iso, r.rows] as const)
          .catch(() => [iso, []] as const),
      ),
    ).then((entries) => {
      if (cancelled) return;
      setProvenance(Object.fromEntries(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [isRegional, indicator, selected]);

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
  const colorByIso = new Map(selected.map((iso, i) => [iso, COLORS[i % COLORS.length]]));
  const specWithForecast: ChartSpec | null =
    spec && showForecast
      ? {
          ...spec,
          series: selected.flatMap((iso) => {
            const histPts = rows
              .filter((r) => r.iso3 === iso && r.value !== null)
              .map((r) => ({ x: r.year as number, y: r.value as number }));
            if (!histPts.length) return [];
            const color = colorByIso.get(iso)!;
            const name = String(rows.find((r) => r.iso3 === iso)?.country ?? iso);
            const historySeries = { name, points: histPts, color };

            const f = forecasts[iso];
            if (!f) return [historySeries];

            const last = histPts[histPts.length - 1];
            // include the last history point so the dashed line connects
            const points = [last, ...f.forecast.map((p) => ({ x: p.t, y: p.value }))];
            const band = f.forecast.map((p) => ({ x: p.t, lo: p.lo, hi: p.hi }));
            const forecastSeries = {
              name: `${iso} forecast`,
              points,
              dashed: true,
              color,
              band,
            };
            return [historySeries, forecastSeries];
          }),
        }
      : spec;

  const years = rows.map((r) => Number(r.year)).filter((y) => !Number.isNaN(y));
  const eventMarkers =
    showEvents && years.length
      ? events
          .map((e) => ({
            x: Number(String(e.start_date).slice(0, 4)),
            label: String(e.title),
          }))
          .filter((e) => e.x >= Math.min(...years) && e.x <= Math.max(...years))
          // cap to keep the chart legible; a full list is one click away on /events
          .slice(0, 6)
      : [];
  const chartSpec: ChartSpec | null =
    (specWithForecast ?? spec) && eventMarkers.length
      ? { ...(specWithForecast ?? spec)!, events: eventMarkers }
      : (specWithForecast ?? spec);

  const sourceDisagreements = disagreements(provenance);

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
          onChange={(e) => {
            const name = e.target.value;
            // crossing the country <-> region boundary invalidates the
            // current geography selection
            if (nutsIndicators.has(name) !== isRegional)
              setSelected(nutsIndicators.has(name) ? DEFAULT_REGIONS : DEFAULT_COUNTRIES);
            setIndicator(name);
          }}
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
          <option value="">{isRegional ? "+ add region…" : "+ add country…"}</option>
          {isRegional
            ? regions.map((r) => (
                <option key={String(r.code)} value={String(r.code)}>
                  {String(r.country)} · {String(r.name)} ({String(r.code)})
                </option>
              ))
            : countries.map((c) => (
                <option key={String(c.iso3)} value={String(c.iso3)}>
                  {String(c.name)}
                </option>
              ))}
        </select>

        <div className="flex flex-wrap gap-1.5">
          {selected.map((iso) => {
            const region = isRegional ? regions.find((r) => r.code === iso) : null;
            return (
              <button
                key={iso}
                type="button"
                onClick={() => setSelected(selected.filter((s) => s !== iso))}
                className="inline-flex items-center gap-1 rounded-full bg-black/5 px-2.5 py-1 text-xs hover:bg-black/10 dark:bg-white/10 dark:hover:bg-white/15"
              >
                <Flag code={region ? region.country_iso3 : iso} className="h-3" /> {iso}{" "}
                <X className="h-3 w-3" />
              </button>
            );
          })}
        </div>

        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showForecast}
            onChange={(e) => setShowForecast(e.target.checked)}
          />
          Forecast →
        </label>
        {!isRegional ? (
          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showEvents}
              onChange={(e) => setShowEvents(e.target.checked)}
            />
            Events
          </label>
        ) : null}
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
          <BlockChart spec={chartSpec ?? spec} />
          <div className="text-xs text-black/50 dark:text-white/50">
            Source: {sources.join(", ")}
            {meta?.is_proxy ? (
              <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 font-medium text-amber-700 dark:text-amber-300">
                proxy — {String(meta.proxy_note ?? "stand-in for the official concept")}
              </span>
            ) : null}
            {meta?.definition ? <div className="mt-1">{String(meta.definition)}</div> : null}
          </div>
          <SourceComparison rows={sourceDisagreements} />
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
