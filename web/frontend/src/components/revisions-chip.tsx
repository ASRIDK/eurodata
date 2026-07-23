"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, type RevisionRow, type RevisionSummaryRow } from "@/lib/api";

/**
 * Compact "N values revised" chip for an indicator/country series. Expands to
 * the vintage-by-vintage trail. Renders nothing while loading or when the
 * series has never been revised, so it can be dropped next to any chart.
 */
export function RevisionsChip({
  indicator,
  country,
}: {
  indicator: string;
  country: string;
}) {
  const [summary, setSummary] = useState<RevisionSummaryRow[]>([]);
  const [rows, setRows] = useState<RevisionRow[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-change: reset the chip when the indicator/country changes
    setOpen(false);
    setSummary([]);
    setRows([]);
    api<{ rows: RevisionRow[]; summary: RevisionSummaryRow[]; n_revised: number }>(
      `/api/revisions?indicator=${encodeURIComponent(indicator)}&country=${encodeURIComponent(country)}`,
    )
      .then((r) => {
        if (cancelled) return;
        setSummary(r.summary);
        setRows(r.rows);
      })
      .catch(() => {
        /* revisions are supplementary; stay silent on failure */
      });
    return () => {
      cancelled = true;
    };
  }, [indicator, country]);

  if (!summary.length) return null;

  return (
    <div className="inline-block align-middle">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-full bg-sky-500/15 px-2 py-0.5 text-xs font-medium text-sky-700 hover:bg-sky-500/25 dark:text-sky-300"
      >
        <span aria-hidden className={open ? "rotate-90 transition-transform" : "transition-transform"}>
          ▸
        </span>
        {summary.length} value{summary.length === 1 ? "" : "s"} revised
      </button>

      {open ? (
        <div className="mt-2 overflow-x-auto rounded-xl border border-black/10 dark:border-white/10">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-black/10 bg-black/[.03] text-left dark:border-white/10 dark:bg-white/[.04]">
                {["period", "source", "as of", "value", "Δ vs prior"].map((c) => (
                  <th key={c} className="whitespace-nowrap px-3 py-1.5 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={i}
                  className="border-b border-black/5 last:border-0 dark:border-white/5"
                >
                  <td className="whitespace-nowrap px-3 py-1 tabular-nums">{r.period}</td>
                  <td className="whitespace-nowrap px-3 py-1">{r.source}</td>
                  <td className="whitespace-nowrap px-3 py-1 tabular-nums">
                    {String(r.vintage_date).slice(0, 10)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-1 tabular-nums">
                    {r.value === null ? "—" : r.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </td>
                  <td
                    className={
                      "whitespace-nowrap px-3 py-1 tabular-nums " +
                      (r.delta === null
                        ? "text-black/40 dark:text-white/40"
                        : r.delta >= 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-red-600 dark:text-red-400")
                    }
                  >
                    {r.delta === null
                      ? "first"
                      : `${r.delta >= 0 ? "+" : ""}${r.delta.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-3 py-1.5 text-[11px] text-black/40 dark:text-white/40">
            Full revision history across the dataset →{" "}
            <Link href="/revisions" className="underline">
              /revisions
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
