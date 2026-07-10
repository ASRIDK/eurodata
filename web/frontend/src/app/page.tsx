"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { DataTable } from "@/components/data-table";
import { api, type Row } from "@/lib/api";

export default function Home() {
  const [years, setYears] = useState<[number, number] | null>(null);
  const [coverage, setCoverage] = useState<Row[]>([]);
  const [countries, setCountries] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<{ years: [number, number] }>("/api/health"),
      api<{ rows: Row[] }>("/api/coverage"),
      api<{ rows: Row[] }>("/api/countries"),
    ])
      .then(([h, cov, c]) => {
        setYears(h.years);
        setCoverage(cov.rows);
        setCountries(c.rows.length);
      })
      .catch((e) => setError(e.message));
  }, []);

  const populated = coverage.filter((r) => Number(r.rows) > 0);
  const totalRows = coverage.reduce((acc, r) => acc + Number(r.rows ?? 0), 0);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">
        European data intelligence
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

          <h2 className="mb-3 mt-10 text-lg font-medium">Coverage by indicator</h2>
          {coverage.length ? (
            <DataTable
              columns={["indicator", "domain", "rows", "countries", "first_year", "last_year", "is_proxy"]}
              rows={coverage.map((r) => [
                r.indicator as string, r.domain as string, r.rows as number,
                r.countries as number, r.first_year as number,
                r.last_year as number, r.is_proxy as boolean,
              ])}
            />
          ) : (
            <p className="text-sm text-black/50 dark:text-white/50">Loading…</p>
          )}
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
