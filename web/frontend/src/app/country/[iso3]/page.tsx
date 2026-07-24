"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Choropleth } from "@/components/choropleth-lazy";
import type { GeoJSON } from "@/components/choropleth";
import { CountrySummary } from "@/components/country-summary";
import { Flag } from "@/components/flag";
import { formatKpi, KPI_INDICATORS, type KpiData } from "@/components/country-popup";
import { api, type CountryProfile, type Row } from "@/lib/api";

const NUTS_INDICATOR = "GDP per capita (NUTS 2 region)";
// Indicators the Europe-in-context map can shade by. All exist for ~all 50.
const MAP_INDICATORS = ["GDP per capita", "Unemployment Rate", "Inflation (HICP)"] as const;

// Cache the two geometry files across navigations — they are static and ~200KB.
let geoCache: { countries?: GeoJSON; nuts?: GeoJSON } = {};
async function loadGeo(which: "europe-countries" | "nuts2"): Promise<GeoJSON> {
  const key = which === "nuts2" ? "nuts" : "countries";
  if (geoCache[key]) return geoCache[key]!;
  const g = (await fetch(`/geo/${which}.geojson`).then((r) => r.json())) as GeoJSON;
  geoCache = { ...geoCache, [key]: g };
  return g;
}

export default function CountryProfilePage() {
  const params = useParams<{ iso3: string }>();
  const iso3 = params.iso3?.toUpperCase() ?? "";

  const [profile, setProfile] = useState<CountryProfile | null>(null);
  const [kpis, setKpis] = useState<KpiData | null>(null);
  const [events, setEvents] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Maps
  const [countriesGeo, setCountriesGeo] = useState<GeoJSON | null>(null);
  const [nutsGeo, setNutsGeo] = useState<GeoJSON | null>(null);
  const [mapIndicator, setMapIndicator] = useState<(typeof MAP_INDICATORS)[number]>("GDP per capita");
  const [euValues, setEuValues] = useState<Record<string, number>>({});
  const [euUnit, setEuUnit] = useState<string>("");
  const [regionValues, setRegionValues] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    if (!/^[A-Z]{3}$/.test(iso3)) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-change: loading/error reset before the async load below
    setLoading(true);
    setError(null);

    Promise.all([
      api<CountryProfile>(`/api/country-profile?country=${iso3}`),
      Promise.all(
        KPI_INDICATORS.map((k) =>
          api<{ rows: Row[] }>(`/api/latest?indicator=${encodeURIComponent(k)}`)
            .then((r) => [k, r.rows.find((row) => row.iso3 === iso3)] as const)
            .catch(() => [k, undefined] as const),
        ),
      ),
      api<{ rows: Row[] }>(`/api/events?country=${iso3}`),
    ])
      .then(([prof, kpiEntries, eventsRes]) => {
        if (cancelled) return;
        setProfile(prof);
        const kpiData: KpiData = {};
        for (const [k, row] of kpiEntries) {
          kpiData[k] =
            row && row.value != null
              ? { value: Number(row.value), unit: row.unit == null ? null : String(row.unit), period: String(row.period) }
              : null;
        }
        setKpis(kpiData);
        setEvents(
          [...eventsRes.rows]
            .sort((a, b) => String(b.start_date).localeCompare(String(a.start_date)))
            .slice(0, 6),
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [iso3]);

  // Europe-in-context map: geometry + the selected indicator's latest per country.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      loadGeo("europe-countries"),
      api<{ rows: Row[] }>(`/api/latest?indicator=${encodeURIComponent(mapIndicator)}`),
    ])
      .then(([geo, res]) => {
        if (cancelled) return;
        setCountriesGeo(geo);
        const values: Record<string, number> = {};
        for (const r of res.rows) if (r.value != null) values[String(r.iso3)] = Number(r.value);
        setEuValues(values);
        setEuUnit(res.rows.length ? String(res.rows[0].unit ?? "") : "");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [mapIndicator]);

  // Regional map: this country's NUTS 2 regions, GDP per capita. iso2 prefixes
  // the region codes (FR10 -> FR), so filter both geometry and values by it.
  const iso2 = profile?.iso2 ?? "";
  useEffect(() => {
    if (!iso2) return;
    let cancelled = false;
    Promise.all([
      loadGeo("nuts2"),
      api<{ rows: Row[] }>(`/api/latest?indicator=${encodeURIComponent(NUTS_INDICATOR)}`),
    ])
      .then(([geo, res]) => {
        if (cancelled) return;
        const mine = geo.features.filter((f) => f.properties.id.startsWith(iso2));
        const values: Record<string, number> = {};
        for (const r of res.rows) {
          const code = String(r.iso3);
          if (code.startsWith(iso2) && r.value != null) values[code] = Number(r.value);
        }
        setNutsGeo(mine.length ? { type: "FeatureCollection", features: mine } : null);
        setRegionValues(Object.keys(values).length ? values : null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [iso2]);

  if (!/^[A-Z]{3}$/.test(iso3)) {
    return (
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <p className="text-sm text-black/50 dark:text-white/50">Invalid country code.</p>
      </main>
    );
  }

  const money = (v: number) =>
    euUnit === "USD"
      ? v >= 1e3
        ? `$${(v / 1e3).toFixed(0)}k`
        : `$${v.toFixed(0)}`
      : v.toLocaleString(undefined, { maximumFractionDigits: 1 });

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
      {error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">{error}</div>
      ) : loading || !profile ? (
        <p className="text-sm text-black/50 dark:text-white/50">Loading…</p>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <Flag code={iso3} className="h-7" />
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{profile.name}</h1>
              <p className="text-xs text-black/40 dark:text-white/40">
                {iso3}
                {profile.iso2 ? ` · ${profile.iso2}` : ""}
              </p>
            </div>
          </div>

          {profile.blocs.length ? (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {profile.blocs.map((b) => (
                <span
                  key={b.code}
                  className="rounded-full bg-black/5 px-2.5 py-1 text-xs dark:bg-white/10"
                >
                  {b.name}
                  {b.until_year ? ` (until ${b.until_year})` : b.since_year ? ` since ${b.since_year}` : ""}
                </span>
              ))}
            </div>
          ) : null}

          <div className="mt-5">
            <CountrySummary profile={profile} />
          </div>

          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {KPI_INDICATORS.map((k) => {
              const v = kpis?.[k];
              return (
                <div key={k} className="rounded-xl border border-black/10 px-3 py-2.5 dark:border-white/10">
                  <div className="text-xs text-black/50 dark:text-white/50">{k}</div>
                  {v ? (
                    <>
                      <div className="mt-0.5 text-lg font-semibold tabular-nums">{formatKpi(v)}</div>
                      <div className="text-[11px] text-black/35 dark:text-white/35">{v.period}</div>
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

          {/* Europe in context */}
          <section className="mt-8">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold">{profile.name} in Europe</h2>
              <select
                value={mapIndicator}
                onChange={(e) => setMapIndicator(e.target.value as (typeof MAP_INDICATORS)[number])}
                className="rounded-lg border border-black/15 px-2 py-1 text-xs dark:border-white/15 dark:bg-black"
              >
                {MAP_INDICATORS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </div>
            <p className="mt-1 text-xs text-black/40 dark:text-white/40">
              {mapIndicator}
              {profile.headline.find((h) => h.indicator === mapIndicator)
                ? ` — ${profile.name} ranks ${profile.headline.find((h) => h.indicator === mapIndicator)!.rank} of ${profile.headline.find((h) => h.indicator === mapIndicator)!.of}`
                : ""}
            </p>
            {countriesGeo ? (
              <div className="mt-3">
                <Choropleth
                  geojson={countriesGeo}
                  values={euValues}
                  highlight={iso3}
                  unit={euUnit}
                  format={euUnit === "%" ? (v) => v.toFixed(1) : money}
                />
              </div>
            ) : (
              <div className="mt-3 h-72 w-full animate-pulse rounded-lg bg-black/5 dark:bg-white/5" />
            )}
          </section>

          {/* Regional spread */}
          <section className="mt-8">
            <h2 className="text-sm font-semibold">Regional spread</h2>
            {nutsGeo && regionValues ? (
              <>
                <p className="mt-1 text-xs text-black/40 dark:text-white/40">
                  GDP per capita by NUTS 2 region, latest year
                </p>
                <div className="mt-3">
                  <Choropleth
                    geojson={nutsGeo}
                    values={regionValues}
                    unit="EUR"
                    format={(v) => (v >= 1000 ? `€${(v / 1000).toFixed(0)}k` : `€${v.toFixed(0)}`)}
                    height={300}
                  />
                </div>
              </>
            ) : (
              <p className="mt-2 max-w-prose text-xs text-black/40 dark:text-white/40">
                No sub-national (NUTS 2) data is available for {profile.name}. Regional
                accounts cover EU, EFTA and candidate countries; others are shown at
                the national level only.
              </p>
            )}
          </section>

          <section className="mt-8">
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
                No curated events for {profile.name}.
              </p>
            )}
            <Link href="/events" className="mt-3 inline-block text-xs font-medium underline underline-offset-4">
              Browse all events →
            </Link>
          </section>

          <p className="mt-8 text-[11px] text-black/30 dark:text-white/30">
            Map boundaries © EuroGeographics / Eurostat GISCO. Kosovo is not
            distinguished in the source geometry.
          </p>
        </>
      )}
    </main>
  );
}
