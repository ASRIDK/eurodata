import { FlagName } from "@/components/flag";
import type { Row } from "@/lib/api";

export type ProvenanceRow = {
  country: string;
  period: string;
  source: string;
  value: number;
  unit: string;
  reliability_score: number;
  is_best: boolean;
};

/** Rows where more than one source reported a value for the same
 * country/period — i.e. actual disagreement, not just multi-vintage noise. */
export function disagreements(byCountry: Record<string, Row[]>): ProvenanceRow[] {
  const out: ProvenanceRow[] = [];
  for (const [country, rows] of Object.entries(byCountry)) {
    const byPeriod = new Map<string, Row[]>();
    for (const r of rows) {
      const key = String(r.period);
      (byPeriod.get(key) ?? byPeriod.set(key, []).get(key)!).push(r);
    }
    for (const group of byPeriod.values()) {
      const sources = new Set(group.map((r) => r.source));
      if (sources.size < 2) continue;
      // Two sources reporting the same number is agreement, not disagreement —
      // don't raise the banner for it.
      if (new Set(group.map((r) => Number(r.value))).size < 2) continue;
      for (const r of group) {
        out.push({
          country,
          period: String(r.period),
          source: String(r.source),
          value: Number(r.value),
          unit: String(r.unit ?? ""),
          reliability_score: Number(r.reliability_score),
          is_best: Boolean(r.is_best),
        });
      }
    }
  }
  return out;
}

export function SourceComparison({ rows }: { rows: ProvenanceRow[] }) {
  if (!rows.length) return null;
  // group into one line per (country, period)
  const groups = new Map<string, ProvenanceRow[]>();
  for (const r of rows) {
    const key = `${r.country}__${r.period}`;
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(r);
  }

  return (
    <div className="rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-3 text-xs text-blue-900 dark:text-blue-200">
      <div className="mb-2 font-medium">
        Sources disagree for {groups.size} {groups.size === 1 ? "period" : "periods"} shown
        below — eurodata uses the higher-reliability source (bold).
      </div>
      <div className="space-y-1.5">
        {[...groups.entries()].map(([key, group]) => (
          <div key={key} className="flex flex-wrap items-baseline gap-x-1.5">
            <span className="font-medium">
              <FlagName value={group[0].country} /> {group[0].period}:
            </span>
            {group.map((r, i) => (
              <span key={r.source}>
                {i > 0 ? <span className="opacity-50"> vs </span> : null}
                <span className={r.is_best ? "font-semibold" : "opacity-70"}>
                  {r.source} {r.value.toLocaleString()}
                  {r.unit}
                </span>
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
