"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Flag } from "@/components/flag";
import type { CountryMarker } from "@/components/european-markers";

// Indicator names as the backend resolves them (indicator.name in the catalog).
export const KPI_INDICATORS = [
  "GDP",
  "GDP per capita",
  "Population",
  "Unemployment Rate",
  "Inflation (HICP)",
] as const;

export type Kpi = { value: number; unit: string | null; period: string };
export type KpiData = Record<string, Kpi | null>;

export function formatKpi(k: Kpi): string {
  const { value, unit } = k;
  if (unit === "%") return `${value.toFixed(1)}%`;
  if (unit === "USD") {
    return value >= 1e9
      ? `$${Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(value)}`
      : `$${Math.round(value).toLocaleString("en")}`;
  }
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function CountryPopup({
  country,
  anchor,
  data,
  loading,
  error,
  onClose,
}: {
  country: CountryMarker;
  /** Marker position in px within the globe container (desktop placement). */
  anchor: { x: number; y: number };
  data: KpiData | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const desktopRef = useRef<HTMLDivElement>(null);
  // The anchor is in the globe container's coordinate space, but that
  // container can extend past the viewport (the zoomed hero), so the card is
  // nudged back inside the viewport after render.
  const [nudgeY, setNudgeY] = useState(0);

  useLayoutEffect(() => {
    const el = desktopRef.current;
    if (!el) return;
    const b = el.getBoundingClientRect();
    const topBound = 64; // clear of the fixed navbar
    if (b.top - nudgeY < topBound) setNudgeY(topBound - (b.top - nudgeY));
    else if (b.bottom - nudgeY > window.innerHeight - 8)
      setNudgeY(Math.min(0, window.innerHeight - 8 - (b.bottom - nudgeY)));
    else setNudgeY(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchor]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const onPointerDown = (e: PointerEvent) => {
      if (cardRef.current && !cardRef.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [onClose]);

  const hasData = data && KPI_INDICATORS.some((k) => data[k]);

  const body = (
    <>
      <div className="flex items-center gap-2">
        <Flag code={country.iso3} className="h-4" />
        <span className="text-sm font-semibold">{country.name}</span>
        <span className="text-xs text-black/40 dark:text-white/40">{country.city}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="ml-auto rounded-lg p-1 text-black/40 hover:bg-black/5 hover:text-black/70 dark:text-white/40 dark:hover:bg-white/10 dark:hover:text-white/70"
        >
          ✕
        </button>
      </div>

      <div className="mt-3 space-y-1.5">
        {error ? (
          <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
        ) : loading ? (
          KPI_INDICATORS.map((k) => (
            <div key={k} className="flex items-center justify-between gap-4">
              <span className="text-xs text-black/50 dark:text-white/50">{k}</span>
              <span className="h-3 w-16 animate-pulse rounded bg-black/10 dark:bg-white/10" />
            </div>
          ))
        ) : !hasData ? (
          <p className="text-xs text-black/50 dark:text-white/50">
            No data available for {country.name}.
          </p>
        ) : (
          KPI_INDICATORS.map((k) => {
            const v = data?.[k];
            return (
              <div key={k} className="flex items-baseline justify-between gap-4">
                <span className="text-xs text-black/50 dark:text-white/50">{k}</span>
                {v ? (
                  <span className="text-xs font-medium tabular-nums">
                    {formatKpi(v)}
                    <span className="ml-1 font-normal text-black/35 dark:text-white/35">
                      {v.period}
                    </span>
                  </span>
                ) : (
                  <span className="text-xs text-black/30 dark:text-white/30">—</span>
                )}
              </div>
            );
          })
        )}
      </div>

      <Link
        href={`/country/${country.iso3}`}
        className="mt-3 block text-xs font-medium underline underline-offset-4"
      >
        View full profile →
      </Link>
    </>
  );

  // Desktop: card anchored near the marker, flipped below when the marker is
  // high in the hero. Mobile: bottom sheet with a dismissable backdrop.
  const placeBelow = anchor.y < 250;
  return (
    <div ref={cardRef}>
      <div
        ref={desktopRef}
        className="popup-in absolute z-30 hidden w-64 rounded-2xl border border-black/10 bg-white p-4 shadow-xl sm:block dark:border-white/15 dark:bg-neutral-900"
        style={{
          left: `clamp(8px, calc(${anchor.x}px - 8rem), calc(100% - 264px))`,
          top: placeBelow ? anchor.y + 16 : anchor.y - 14,
          transform: placeBelow
            ? `translateY(${nudgeY}px)`
            : `translateY(calc(-100% + ${nudgeY}px))`,
        }}
      >
        {body}
      </div>
      <div className="sheet-in fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border-t border-black/10 bg-white p-4 pb-6 shadow-2xl sm:hidden dark:border-white/15 dark:bg-neutral-900">
        {body}
      </div>
    </div>
  );
}
