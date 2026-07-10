"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartSpec } from "@/lib/api";

const COLORS = [
  "#2563eb", "#dc2626", "#16a34a", "#9333ea",
  "#ea580c", "#0891b2", "#ca8a04", "#db2777",
];

function compactNumber(v: unknown): string {
  if (typeof v !== "number") return String(v ?? "");
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(v);
}

export function BlockChart({ spec }: { spec: ChartSpec }) {
  if (!spec.series.length) return null;

  if (spec.kind === "bar") {
    const s = spec.series[0];
    const data = s.points.map((p) => ({ x: p.x, y: p.y }));
    return (
      <ChartFrame unit={spec.unit}>
        <BarChart data={data} margin={{ left: 8, right: 8 }}>
          <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
          <XAxis dataKey="x" fontSize={11} interval={0} angle={-40} textAnchor="end" height={50} />
          <YAxis fontSize={11} tickFormatter={compactNumber} width={55} />
          <Tooltip formatter={(v) => compactNumber(v)} />
          <Bar dataKey="y" name={s.name} fill={COLORS[0]} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ChartFrame>
    );
  }

  const byX = new Map<number | string, Record<string, number | string | null>>();
  for (const s of spec.series) {
    for (const p of s.points) {
      const row = byX.get(p.x) ?? { x: p.x };
      row[s.name] = p.y;
      byX.set(p.x, row);
    }
  }
  const data = [...byX.values()].sort((a, b) => Number(a.x) - Number(b.x));

  return (
    <ChartFrame unit={spec.unit}>
      <LineChart data={data} margin={{ left: 8, right: 8 }}>
        <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
        <XAxis dataKey="x" fontSize={11} />
        <YAxis fontSize={11} tickFormatter={compactNumber} width={55} />
        <Tooltip formatter={(v) => compactNumber(v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {spec.series.map((s, i) => (
          <Line
            key={s.name}
            dataKey={s.name}
            stroke={COLORS[i % COLORS.length]}
            dot={false}
            strokeWidth={2}
            connectNulls
          />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

function ChartFrame({ unit, children }: { unit: string | null; children: React.ReactElement }) {
  return (
    <div className="w-full">
      {unit ? (
        <div className="mb-1 text-xs text-black/50 dark:text-white/50">{unit}</div>
      ) : null}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
