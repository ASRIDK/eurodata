"use client";

import { useEffect, useMemo, useState } from "react";

import { BlockChart } from "@/components/block-chart-lazy";
import { DataTable } from "@/components/data-table";
import { api, type ChartSpec, type Row } from "@/lib/api";

export default function Events() {
  const [events, setEvents] = useState<Row[]>([]);
  const [types, setTypes] = useState<Row[]>([]);
  const [indicators, setIndicators] = useState<Row[]>([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [studyEvent, setStudyEvent] = useState("");
  const [studyIndicator, setStudyIndicator] = useState("Inflation (HICP)");
  const [study, setStudy] = useState<Row[]>([]);
  const [studyLoading, setStudyLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<{ rows: Row[] }>("/api/events"),
      api<{ rows: Row[] }>("/api/event-types"),
      api<{ rows: Row[] }>("/api/indicators"),
    ])
      .then(([e, t, i]) => {
        setEvents(e.rows);
        setTypes(t.rows);
        setIndicators(i.rows);
      })
      .catch((e) => setError(e.message));
  }, []);

  const visible = useMemo(
    () => (typeFilter ? events.filter((e) => e.event_type === typeFilter) : events),
    [events, typeFilter],
  );

  useEffect(() => {
    if (!studyEvent || !studyIndicator) {
      setStudy([]);
      return;
    }
    setStudyLoading(true);
    api<{ rows: Row[] }>(
      `/api/event-study?indicator=${encodeURIComponent(studyIndicator)}&event_code=${encodeURIComponent(studyEvent)}`,
    )
      .then((r) => setStudy(r.rows))
      .catch((e) => setError(e.message))
      .finally(() => setStudyLoading(false));
  }, [studyEvent, studyIndicator]);

  const studySpec: ChartSpec | null = study.length
    ? {
        kind: "bar",
        unit: "% change (after vs before mean)",
        series: [
          {
            name: studyEvent,
            points: [...study]
              .sort((a, b) => Math.abs(Number(b.pct_change ?? 0)) - Math.abs(Number(a.pct_change ?? 0)))
              .slice(0, 15)
              .map((r) => ({ x: String(r.iso3), y: r.pct_change as number })),
          },
        ],
      }
    : null;

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Events</h1>
      <p className="mt-1 text-sm text-black/60 dark:text-white/60">
        Curated, dated European events with primary sources — pick one to run a
        before/after event study. Deltas are descriptive, not causal.
      </p>

      {error ? (
        <div className="mt-5 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-3">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          <option value="">All event types</option>
          {types.map((t) => (
            <option key={String(t.event_type)} value={String(t.event_type)}>
              {String(t.event_type)} ({String(t.events)})
            </option>
          ))}
        </select>

        <select
          value={studyEvent}
          onChange={(e) => setStudyEvent(e.target.value)}
          className="max-w-72 rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          <option value="">Event study: pick an event…</option>
          {visible.map((ev) => (
            <option key={String(ev.code)} value={String(ev.code)}>
              {String(ev.start_date).slice(0, 4)} · {String(ev.title)}
            </option>
          ))}
        </select>

        <select
          value={studyIndicator}
          onChange={(e) => setStudyIndicator(e.target.value)}
          className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
        >
          {indicators.map((i) => (
            <option key={String(i.name)} value={String(i.name)}>
              {String(i.name)}
            </option>
          ))}
        </select>
      </div>

      {studyEvent ? (
        <section className="mt-6 space-y-4">
          {studyLoading ? (
            <p className="text-sm text-black/50 dark:text-white/50">Running event study…</p>
          ) : studySpec ? (
            <>
              <BlockChart spec={studySpec} />
              <DataTable
                columns={["iso3", "before_mean", "after_mean", "delta", "pct_change", "n_before", "n_after"]}
                rows={study.map((r) => [
                  r.iso3, r.before_mean, r.after_mean, r.delta,
                  r.pct_change, r.n_before, r.n_after,
                ])}
              />
            </>
          ) : (
            <p className="text-sm text-black/50 dark:text-white/50">
              Not enough data around this event for {studyIndicator}.
            </p>
          )}
        </section>
      ) : null}

      <h2 className="mb-3 mt-8 text-lg font-medium">
        {typeFilter ? `Events — ${typeFilter}` : "All events"} ({visible.length})
      </h2>
      <DataTable
        columns={["date", "title", "type", "scope", "source"]}
        rows={visible.map((ev) => [
          String(ev.start_date).slice(0, 10),
          ev.title,
          ev.event_type,
          (ev.iso3 as string) ?? (ev.bloc_code as string) ?? "Europe",
          ev.source,
        ])}
      />
    </main>
  );
}
