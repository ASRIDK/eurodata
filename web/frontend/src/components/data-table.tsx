import { isValidElement, type ReactNode } from "react";

function fmt(v: ReactNode): ReactNode {
  if (v === null || v === undefined) return "–";
  if (isValidElement(v)) return v;
  if (typeof v === "number") {
    return Number.isInteger(v) && Math.abs(v) < 10000
      ? String(v)
      : Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(v);
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

export function DataTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: ReactNode[][];
}) {
  if (!rows.length) return null;
  return (
    <div className="w-full overflow-x-auto rounded-xl border border-black/10 dark:border-white/10">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-black/10 bg-black/[.03] text-left dark:border-white/10 dark:bg-white/[.04]">
            {columns.map((c) => (
              <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-black/5 last:border-0 dark:border-white/5">
              {r.map((v, j) => (
                <td key={j} className="whitespace-nowrap px-3 py-1.5 tabular-nums">
                  {fmt(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
