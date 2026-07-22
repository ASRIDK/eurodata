"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  type LabelProps,
} from "recharts";

import type { ChartSpec } from "@/lib/api";
import { FlagName } from "@/components/flag";
import { flagUrl } from "@/lib/flags";

const COLORS = [
  "#2563eb", "#dc2626", "#16a34a", "#9333ea",
  "#ea580c", "#0891b2", "#ca8a04", "#db2777",
];

function compactNumber(v: unknown): string {
  if (typeof v !== "number") return String(v ?? "");
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(v);
}

export function BlockChart({
  spec,
  horizontal = false,
}: {
  spec: ChartSpec;
  /** Render bar charts with categories on the vertical axis and values on the horizontal axis. */
  horizontal?: boolean;
}) {
  if (!spec.series.length) return null;

  if (spec.kind === "bar") {
    const s = spec.series[0];
    const data = s.points.map((p) => ({ x: p.x, y: p.y }));
    // Country rankings show just the flag on the axis; hover reveals the name.
    const allCountries = data.every((d) => flagUrl(d.x) !== null);

    if (horizontal) {
      return (
        <ChartFrame unit={spec.unit} title={spec.title}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ left: allCountries ? 8 : 24, right: 16 }}
          >
            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
            <XAxis type="number" fontSize={11} tickFormatter={compactNumber} />
            {allCountries ? (
              <YAxis
                dataKey="x"
                type="category"
                interval={0}
                width={34}
                tick={<FlagTick orientation="vertical" />}
              />
            ) : (
              <YAxis
                dataKey="x"
                type="category"
                fontSize={11}
                interval={0}
                width={90}
              />
            )}
            <Tooltip
              formatter={(v) => compactNumber(v)}
              labelFormatter={(l) => (allCountries ? <FlagName value={l} /> : String(l))}
            />
            <Bar dataKey="y" name={s.name} fill={COLORS[0]} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ChartFrame>
      );
    }

    return (
      <ChartFrame unit={spec.unit} title={spec.title}>
        <BarChart data={data} margin={{ left: 8, right: 8 }}>
          <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
          {allCountries ? (
            <XAxis dataKey="x" interval={0} height={26} tick={<FlagTick />} />
          ) : (
            <XAxis dataKey="x" fontSize={11} interval={0} angle={-40} textAnchor="end" height={50} />
          )}
          <YAxis fontSize={11} tickFormatter={compactNumber} width={55} />
          <Tooltip
            formatter={(v) => compactNumber(v)}
            labelFormatter={(l) => (allCountries ? <FlagName value={l} /> : String(l))}
          />
          <Bar dataKey="y" name={s.name} fill={COLORS[0]} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ChartFrame>
    );
  }

  if (spec.kind === "pie") {
    const data = spec.series[0].points
      .filter((p) => p.y !== null)
      .map((p) => ({ name: String(p.x), value: p.y as number }));
    if (!data.length) return null;
    return (
      <ChartFrame unit={spec.unit} title={spec.title}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" outerRadius="75%" strokeOpacity={0}>
            {data.map((d, i) => (
              <Cell key={d.name} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(v, name) => [compactNumber(v), <FlagName key="n" value={name} />]} />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => <FlagName value={v} />} />
        </PieChart>
      </ChartFrame>
    );
  }

  if (spec.kind === "scatter") {
    return (
      <ChartFrame unit={spec.unit} title={spec.title}>
        <ScatterChart margin={{ left: 8, right: 8 }}>
          <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
          <XAxis dataKey="x" type="number" fontSize={11} tickFormatter={compactNumber} domain={["auto", "auto"]} />
          <YAxis dataKey="y" fontSize={11} tickFormatter={compactNumber} width={55} />
          <Tooltip formatter={(v) => compactNumber(v)} />
          {spec.series.length > 1 ? (
            <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => <FlagName value={v} />} />
          ) : null}
          {spec.series.map((s, i) => (
            <Scatter
              key={s.name}
              name={s.name}
              data={s.points.filter((p) => p.y !== null)}
              fill={COLORS[i % COLORS.length]}
            />
          ))}
        </ScatterChart>
      </ChartFrame>
    );
  }

  const byX = new Map<number | string, Record<string, number | string | null | [number, number]>>();
  for (const s of spec.series) {
    for (const p of s.points) {
      const row = byX.get(p.x) ?? { x: p.x };
      row[s.name] = p.y;
      byX.set(p.x, row);
    }
    for (const b of s.band ?? []) {
      const row = byX.get(b.x) ?? { x: b.x };
      row[`${s.name}__band`] = [b.lo, b.hi];
      byX.set(b.x, row);
    }
  }
  // String-aware sort: x may be a year (2020) or a period label ("2020-Q1",
  // "2020-03"); Number() on the latter is NaN and would scramble the axis.
  const data = [...byX.values()].sort((a, b) =>
    String(a.x).localeCompare(String(b.x), "en", { numeric: true }),
  );

  const hasBand = spec.series.some((s) => s.band && s.band.length > 0);
  const Chart = spec.kind === "area" ? AreaChart : hasBand ? ComposedChart : LineChart;
  return (
    <>
      <ChartFrame unit={spec.unit} title={spec.title}>
        <Chart data={data} margin={{ left: 8, right: 8, top: spec.events?.length ? 18 : 0 }}>
          <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
          <XAxis dataKey="x" fontSize={11} />
          <YAxis fontSize={11} tickFormatter={compactNumber} width={55} />
          <Tooltip formatter={(v, name) => [compactNumber(v), <FlagName key="n" value={name} />]} />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => <FlagName value={v} />} />
          {spec.events?.map((e, idx) => (
            <ReferenceLine
              key={`event-${e.x}-${e.label}`}
              x={e.x}
              stroke="currentColor"
              strokeOpacity={0.4}
              strokeDasharray="2 3"
              label={(props: LabelProps) => <EventBadge {...props} index={idx + 1} />}
            />
          ))}
          {spec.series.map((s, i) =>
            s.band ? (
              <Area
                key={`${s.name}__band`}
                dataKey={`${s.name}__band`}
                stroke="none"
                fill={s.color ?? COLORS[i % COLORS.length]}
                fillOpacity={0.12}
                legendType="none"
                tooltipType="none"
                connectNulls
                isAnimationActive={false}
              />
            ) : null,
          )}
          {spec.series.map((s, i) =>
            spec.kind === "area" ? (
              <Area
                key={s.name}
                dataKey={s.name}
                stroke={s.color ?? COLORS[i % COLORS.length]}
                fill={s.color ?? COLORS[i % COLORS.length]}
                fillOpacity={0.15}
                strokeWidth={2}
                strokeDasharray={s.dashed ? "5 4" : undefined}
                connectNulls
              />
            ) : (
              <Line
                key={s.name}
                dataKey={s.name}
                stroke={s.color ?? COLORS[i % COLORS.length]}
                dot={false}
                strokeWidth={2}
                strokeDasharray={s.dashed ? "5 4" : undefined}
                connectNulls
              />
            ),
          )}
        </Chart>
      </ChartFrame>
      {spec.events?.length ? <EventLegend events={spec.events} /> : null}
    </>
  );
}

/** Small numbered dot drawn at the top of an event's reference line — fixed
 * size regardless of title length, so it can never overflow the chart or
 * collide with a neighboring event's marker the way a full text label did. */
function EventBadge({ viewBox, index }: LabelProps & { index: number }) {
  if (!viewBox || !("x" in viewBox) || !("y" in viewBox)) return null;
  const x = viewBox.x;
  const y = viewBox.y - 8;
  return (
    <g>
      <circle cx={x} cy={y} r={7} fill="#475569" fillOpacity={0.9} />
      <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={9} fontWeight={600} fill="#fff">
        {index}
      </text>
    </g>
  );
}

/** Full event titles, keyed to the numbered badges on the chart above — the
 * badges alone can't carry a readable title, so the legend is where the
 * actual text lives. */
function EventLegend({ events }: { events: NonNullable<ChartSpec["events"]> }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-black/50 dark:text-white/50">
      {events.map((e, i) => (
        <span key={`${e.x}-${e.label}`} className="inline-flex items-center gap-1">
          <span className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-[#475569] text-[9px] font-semibold text-white">
            {i + 1}
          </span>
          {e.label}
        </span>
      ))}
    </div>
  );
}

/** Axis tick that draws the country's real flag instead of a text label. */
function FlagTick({
  x,
  y,
  payload,
  orientation = "horizontal",
}: {
  x?: number;
  y?: number;
  payload?: { value?: unknown };
  /** "horizontal" for an x-axis tick, "vertical" for a y-axis tick. */
  orientation?: "horizontal" | "vertical";
}) {
  const url = flagUrl(payload?.value);
  if (!url) return <g />;
  if (orientation === "vertical") {
    return (
      <image
        href={url}
        x={(x ?? 0) - 28}
        y={(y ?? 0) - 7}
        width={20}
        height={14}
        preserveAspectRatio="xMidYMid meet"
      />
    );
  }
  return (
    <image
      href={url}
      x={(x ?? 0) - 10}
      y={(y ?? 0) + 6}
      width={20}
      height={14}
      preserveAspectRatio="xMidYMid meet"
    />
  );
}

function ChartFrame({
  unit,
  title,
  children,
}: {
  unit: string | null;
  title?: string | null;
  children: React.ReactElement;
}) {
  return (
    <div className="w-full">
      {title ? (
        <div className="mb-0.5 text-sm font-medium">{title}</div>
      ) : null}
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
