"use client";

import type { PropagationRow } from "@/lib/api";

// One column per hop, so the ripple reads left to right as a chain of
// consequences. A force-directed view of this graph (median degree 14) would
// render as a hairball; columns stay legible and work on a phone.
export function PropagationCascade({
  rows,
  source,
}: {
  rows: PropagationRow[];
  source: string;
}) {
  if (!rows.length) return null;
  const hops = [...new Set(rows.map((r) => r.hop))].sort((a, b) => a - b);
  const peak = Math.max(...rows.map((r) => Math.abs(r.activation)));

  return (
    <div className="mt-6 overflow-x-auto">
      <div className="flex min-w-max gap-4">
        <div className="w-48 shrink-0">
          <div className="text-xs font-medium text-black/40 dark:text-white/40">
            SHOCK
          </div>
          <div className="mt-2 rounded-lg border border-black/15 px-3 py-2 text-sm font-medium dark:border-white/15">
            {source}
          </div>
        </div>
        {hops.map((hop) => (
          <div key={hop} className="w-56 shrink-0">
            <div className="text-xs font-medium text-black/40 dark:text-white/40">
              HOP {hop}
            </div>
            <ul className="mt-2 space-y-1.5">
              {rows
                .filter((r) => r.hop === hop)
                .map((r) => (
                  <li
                    key={r.node}
                    title={r.via ? `via ${r.via}` : "direct"}
                    className="rounded-lg border border-black/10 px-2.5 py-1.5 dark:border-white/10"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-xs">{r.node}</span>
                      <span
                        className={`shrink-0 text-xs tabular-nums ${
                          r.activation >= 0
                            ? "text-emerald-700 dark:text-emerald-400"
                            : "text-orange-700 dark:text-orange-400"
                        }`}
                      >
                        {r.activation >= 0 ? "+" : ""}
                        {r.activation.toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-1 h-1 rounded-full bg-black/5 dark:bg-white/10">
                      <div
                        className={`h-1 rounded-full ${
                          r.activation >= 0 ? "bg-emerald-600" : "bg-orange-600"
                        }`}
                        style={{
                          width: `${(Math.abs(r.activation) / peak) * 100}%`,
                        }}
                      />
                    </div>
                    {/* Granger-confirmed paths are the minority; mark them
                        rather than letting every arrival look equally causal. */}
                    {r.directed ? (
                      <div className="mt-1 text-[10px] text-black/40 dark:text-white/40">
                        directed
                      </div>
                    ) : null}
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
