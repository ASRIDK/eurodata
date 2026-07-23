"use client";

import { useEffect, useState } from "react";

import { PropagationCascade } from "@/components/propagation-cascade";
import { api, type PropagationRow, type Row } from "@/lib/api";

export default function Propagate() {
  const [indicators, setIndicators] = useState<Row[]>([]);
  const [node, setNode] = useState("Unemployment Rate");
  const [hops, setHops] = useState(3);
  const [floor, setFloor] = useState(0.3);
  const [rows, setRows] = useState<PropagationRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ rows: Row[] }>("/api/indicators")
      .then((r) => setIndicators(r.rows))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!node) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-change: loading/error reset before the async load below
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      node,
      max_hops: String(hops),
      edge_floor: String(floor),
    });
    api<{ rows: PropagationRow[] }>(`/api/propagate?${params}`)
      .then((r) => {
        if (!cancelled) setRows(r.rows);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [node, hops, floor]);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Propagate</h1>
      <p className="mt-1 max-w-prose text-sm text-black/60 dark:text-white/60">
        Shock one indicator and follow where it leads. Each hop multiplies by the
        correlation between two indicators, so a negative edge flips the sign.
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3 text-sm">
        <select
          value={node}
          onChange={(e) => setNode(e.target.value)}
          className="rounded-lg border border-black/15 px-3 py-1.5 dark:border-white/15 dark:bg-black"
        >
          {indicators.map((i) => (
            <option key={String(i.name)} value={String(i.name)}>
              {String(i.name)}
            </option>
          ))}
        </select>
        <label className="inline-flex items-center gap-2">
          Hops
          <input
            type="range"
            min={1}
            max={4}
            value={hops}
            onChange={(e) => setHops(Number(e.target.value))}
          />
          <span className="tabular-nums">{hops}</span>
        </label>
        <label className="inline-flex items-center gap-2">
          Min edge
          <input
            type="range"
            min={0}
            max={0.6}
            step={0.05}
            value={floor}
            onChange={(e) => setFloor(Number(e.target.value))}
          />
          <span className="tabular-nums">{floor.toFixed(2)}</span>
        </label>
      </div>

      <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800 dark:text-amber-200">
        These are indicators that moved together historically, not a forecast and
        not a causal claim. Most edges in the graph carry no confirmed direction;
        the few whose whole path is direction-confirmed are marked
        &ldquo;directed&rdquo;.
      </div>

      {error ? (
        <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : loading ? (
        <p className="mt-6 text-sm text-black/50 dark:text-white/50">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="mt-6 max-w-prose text-sm text-black/50 dark:text-white/50">
          Nothing cleared the threshold. Lower the minimum edge weight, or pick an
          indicator with more correlations — a weakly connected one has no ripple
          to show.
        </p>
      ) : (
        <PropagationCascade rows={rows} source={node} />
      )}
    </main>
  );
}
