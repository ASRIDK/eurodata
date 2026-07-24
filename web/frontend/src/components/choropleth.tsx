"use client";

import { useSyncExternalStore } from "react";

// A minimal SVG choropleth. GeoJSON in lat/lng projects to SVG paths in a few
// dozen lines, so a map library would be disproportionate here (this codebase
// lazy-loads even recharts). Magnitude is a sequential single-hue ramp,
// light->dark, with a neutral fill for "no data" -- and its own steps per theme
// rather than an inverted light-mode ramp.

type Feature = {
  properties: { id: string; name?: string };
  geometry: { type: "Polygon" | "MultiPolygon"; coordinates: number[][][] | number[][][][] };
};
export type GeoJSON = { type: "FeatureCollection"; features: Feature[] };

// low -> high, per theme. Dark mode brightens with magnitude; light mode darkens.
const RAMP = {
  light: [0.93, 0.96, 0.96] as const, // near-surface teal tint
  lightHi: [0.06, 0.46, 0.43] as const, // teal-700
  dark: [0.04, 0.23, 0.22] as const, // just above dark surface
  darkHi: [0.18, 0.83, 0.75] as const, // teal-300
  noDataLight: "#e5e5e5",
  noDataDark: "#2a2a2a",
};

function lerp(a: readonly number[], b: readonly number[], t: number): string {
  const c = a.map((av, i) => Math.round((av + (b[i] - av) * t) * 255));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function polygons(f: Feature): number[][][] {
  return f.geometry.type === "Polygon"
    ? (f.geometry.coordinates as number[][][])
    : (f.geometry.coordinates as number[][][][]).flat();
}

// Subscribe to the OS colour scheme without a setState-in-effect. Returns false
// during SSR (server has no matchMedia); the first client render corrects it.
const prefersDark = {
  subscribe(cb: () => void) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", cb);
    return () => mq.removeEventListener("change", cb);
  },
  get: () => window.matchMedia("(prefers-color-scheme: dark)").matches,
};

export function Choropleth({
  geojson,
  values,
  highlight,
  unit,
  format = (v) => v.toLocaleString(undefined, { maximumFractionDigits: 1 }),
  height = 340,
}: {
  geojson: GeoJSON;
  values: Record<string, number>;
  highlight?: string;
  unit?: string;
  format?: (v: number) => string;
  height?: number;
}) {
  const dark = useSyncExternalStore(prefersDark.subscribe, prefersDark.get, () => false);

  // Project [lng, lat] with a cos(mean-lat) correction so the continent is not
  // horizontally stretched, then fit every point into the viewBox.
  const pts = geojson.features.flatMap((f) => polygons(f).flat());
  if (!pts.length) return null;
  const lats = pts.map((p) => p[1]);
  const meanLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const k = Math.cos((meanLat * Math.PI) / 180);
  const px = (lng: number) => lng * k;
  const py = (lat: number) => -lat;

  // Frame the main landmass, not the outliers: many geographies carry distant
  // overseas territories (French Guiana, Réunion, the Azores, the NUTS "FRY"
  // regions) that would otherwise blow the bounding box out and shrink the map
  // to a sliver. Trim at *feature* granularity by median-absolute-deviation of
  // feature centroids -- robust to a handful of far territories, where a
  // per-point percentile is not (5 overseas regions carry many vertices). The
  // trimmed features still render; they simply fall outside the viewBox and
  // clip, which is the intended crop.
  const median = (a: number[]) => {
    const s = [...a].sort((x, z) => x - z);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  const centroids = geojson.features.map((f) => {
    const cp = polygons(f).flat();
    return [px(median(cp.map((p) => p[0]))) , py(median(cp.map((p) => p[1])))] as const;
  });
  const mcx = median(centroids.map((c) => c[0]));
  const mcy = median(centroids.map((c) => c[1]));
  const dists = centroids.map((c) => Math.hypot(c[0] - mcx, c[1] - mcy));
  const medD = median(dists);
  const madD = median(dists.map((d) => Math.abs(d - medD))) || medD || 1;
  const keep = geojson.features.filter((_, i) => dists[i] <= medD + 5 * madD);
  const framePts = (keep.length ? keep : geojson.features).flatMap((f) => polygons(f).flat());
  // Feature-level trimming drops overseas-only regions; a point percentile on
  // the survivors then trims a kept country's *own* far territories (e.g.
  // metropolitan France is kept, but its overseas points still reach in).
  const pct = (arr: number[], q: number) => {
    const s = [...arr].sort((a, z) => a - z);
    return s[Math.min(s.length - 1, Math.max(0, Math.round(q * (s.length - 1))))];
  };
  const xs = framePts.map((p) => px(p[0]));
  const ys = framePts.map((p) => py(p[1]));
  let minX = pct(xs, 0.01), maxX = pct(xs, 0.99);
  let minY = pct(ys, 0.01), maxY = pct(ys, 0.99);
  // Guarantee the focus country is fully framed. It may be a geographic outlier
  // that the centroid trim above dropped from the frame set (Iceland, sitting far
  // northwest, is), but a page titled "<country> in Europe" must never crop its
  // own subject -- so widen the box to contain every point of the highlight.
  if (highlight) {
    const hf = geojson.features.find((f) => f.properties.id === highlight);
    if (hf) {
      for (const p of polygons(hf).flat()) {
        const hx = px(p[0]), hy = py(p[1]);
        if (hx < minX) minX = hx;
        else if (hx > maxX) maxX = hx;
        if (hy < minY) minY = hy;
        else if (hy > maxY) maxY = hy;
      }
    }
  }
  const maxW = 640;
  const pad = 4;
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  // Fit the frame inside a maxW-wide, `height`-tall box, preserving aspect ratio.
  // Scale is bounded by whichever dimension binds, so the whole frame stays
  // visible. A width-only scale overflows and crops top *and* bottom whenever the
  // data is taller than `height` -- and Lisbon-to-North-Cape is, in this
  // projection -- which is what clipped Iceland and northern Scandinavia.
  const scale = Math.min((maxW - 2 * pad) / spanX, (height - 2 * pad) / spanY);
  const W = spanX * scale + 2 * pad;
  const H = spanY * scale + 2 * pad;
  const sx = (lng: number) => pad + (px(lng) - minX) * scale;
  const sy = (lat: number) => pad + (py(lat) - minY) * scale;

  const vals = Object.values(values);
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 1;
  const span = hi - lo || 1;
  const noData = dark ? RAMP.noDataDark : RAMP.noDataLight;
  const fill = (id: string): string => {
    const v = values[id];
    if (v == null) return noData;
    const t = (v - lo) / span;
    return dark ? lerp(RAMP.dark, RAMP.darkHi, t) : lerp(RAMP.light, RAMP.lightHi, t);
  };

  const path = (f: Feature): string =>
    polygons(f)
      .map((ring) => "M" + ring.map((p) => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("L") + "Z")
      .join("");

  // Draw the highlighted feature last so its outline sits above its neighbours.
  const ordered = [...geojson.features].sort(
    (a, b) => Number(a.properties.id === highlight) - Number(b.properties.id === highlight),
  );
  const stroke = dark ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.2)";

  return (
    <div>
      <svg
        viewBox={`0 0 ${W.toFixed(0)} ${H.toFixed(0)}`}
        className="h-auto w-full"
        role="img"
        aria-label={
          highlight
            ? `Map of Europe with ${highlight} highlighted, shaded by value`
            : "Map shaded by value"
        }
      >
        {ordered.map((f) => {
          const isHi = f.properties.id === highlight;
          const v = values[f.properties.id];
          return (
            <path
              key={f.properties.id}
              d={path(f)}
              fill={fill(f.properties.id)}
              stroke={isHi ? (dark ? "#fff" : "#000") : stroke}
              strokeWidth={isHi ? 1.5 : 0.4}
            >
              <title>
                {f.properties.name ?? f.properties.id}
                {v != null ? `: ${format(v)}${unit ? ` ${unit}` : ""}` : " — no data"}
              </title>
            </path>
          );
        })}
      </svg>
      {vals.length ? (
        <div className="mt-2 flex items-center gap-2 text-[11px] text-black/50 dark:text-white/50">
          <span className="tabular-nums">
            {format(lo)}
            {unit ? ` ${unit}` : ""}
          </span>
          <span
            className="h-2 flex-1 rounded-full"
            style={{
              background: `linear-gradient(to right, ${
                dark ? lerp(RAMP.dark, RAMP.darkHi, 0) : lerp(RAMP.light, RAMP.lightHi, 0)
              }, ${dark ? lerp(RAMP.dark, RAMP.darkHi, 1) : lerp(RAMP.light, RAMP.lightHi, 1)})`,
            }}
          />
          <span className="tabular-nums">
            {format(hi)}
            {unit ? ` ${unit}` : ""}
          </span>
        </div>
      ) : null}
    </div>
  );
}
