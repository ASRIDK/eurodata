"use client";

import dynamic from "next/dynamic";

// The two maps pull ~200KB of vendored GeoJSON. Loading Choropleth lazily keeps
// it off every other route's bundle, matching the block-chart-lazy pattern.
export const Choropleth = dynamic(
  () => import("./choropleth").then((m) => m.Choropleth),
  {
    ssr: false,
    loading: () => (
      <div className="h-72 w-full animate-pulse rounded-lg bg-black/5 dark:bg-white/5" />
    ),
  },
);
