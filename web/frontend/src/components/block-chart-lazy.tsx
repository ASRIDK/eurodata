"use client";

import dynamic from "next/dynamic";

// recharts is a heavy dependency pulled into every route that renders a
// chart (5 pages + chat). Loading it lazily keeps it out of the initial
// bundle for pages that don't end up rendering a chart on first paint.
export const BlockChart = dynamic(
  () => import("./block-chart").then((m) => m.BlockChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-72 w-full animate-pulse rounded-lg bg-black/5 dark:bg-white/5" />
    ),
  },
);
