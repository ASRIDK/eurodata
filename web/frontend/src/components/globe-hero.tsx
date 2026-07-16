"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { CountryPopup, KPI_INDICATORS, type KpiData } from "@/components/country-popup";
import { EUROPEAN_MARKERS, type CountryMarker } from "@/components/european-markers";
import { Globe } from "@/components/ui/globe";
import { api, type Row } from "@/lib/api";

type KpiCache = Map<string, Map<string, Row>>;

// Scroll-driven hero: at rest the globe overflows the viewport (zoomed on
// Europe); scrolling shrinks and lifts the whole fixed layer so the full
// planet appears in the top area while the page content scrolls in below.
const MIN_SCALE = 0.35;
const END_Y_VH = -60; // translateY at full progress (pre-scale space)

function subscribeReducedMotion(cb: () => void) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

export function GlobeHero() {
  const [progress, setProgress] = useState(0);
  const reducedMotion = useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );

  const [selectedCountry, setSelectedCountry] = useState<CountryMarker | null>(null);
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const [countryData, setCountryData] = useState<KpiData | null>(null);
  const [loading, setLoading] = useState(false);
  const [kpiError, setKpiError] = useState<string | null>(null);
  // One /api/latest fetch per KPI covers every country; the shared promise
  // means concurrent first clicks reuse the same in-flight batch.
  const kpiCacheRef = useRef<Promise<KpiCache> | null>(null);
  const scrollAtOpenRef = useRef(0);

  const closePopup = useCallback(() => {
    setSelectedCountry(null);
    setAnchor(null);
  }, []);

  useEffect(() => {
    // Short viewports get a proportionally shorter animation range.
    let range = 400;
    const onResize = () => {
      range = Math.min(400, window.innerHeight * 0.6);
    };
    const onScroll = () => {
      setProgress(Math.min(window.scrollY / range, 1));
      // A popup anchored to a marker stops making sense once the globe
      // starts shrinking under it — dismiss after modest scroll movement.
      if (Math.abs(window.scrollY - scrollAtOpenRef.current) > 50) closePopup();
    };
    onResize();
    onScroll();
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onScroll);
    };
  }, [closePopup]);

  const handleMarkerClick = useCallback((marker: CountryMarker, pos: { x: number; y: number }) => {
    scrollAtOpenRef.current = window.scrollY;
    setSelectedCountry(marker);
    setAnchor(pos);
    setKpiError(null);
    kpiCacheRef.current ??= Promise.all(
      KPI_INDICATORS.map((k) =>
        api<{ rows: Row[] }>(`/api/latest?indicator=${encodeURIComponent(k)}`),
      ),
    ).then((results) => {
      const cache: KpiCache = new Map();
      KPI_INDICATORS.forEach((k, i) =>
        cache.set(k, new Map(results[i].rows.map((r) => [String(r.iso3), r]))),
      );
      return cache;
    });
    setLoading(true);
    kpiCacheRef.current
      .then((cache) => {
        const data: KpiData = {};
        for (const k of KPI_INDICATORS) {
          const row = cache.get(k)?.get(marker.iso3);
          data[k] =
            row && row.value != null
              ? {
                  value: Number(row.value),
                  unit: row.unit == null ? null : String(row.unit),
                  period: String(row.period),
                }
              : null;
        }
        setCountryData(data);
      })
      .catch((e) => {
        kpiCacheRef.current = null; // let a later click retry
        setKpiError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setLoading(false));
  }, []);

  const scale = 1 - progress * (1 - MIN_SCALE);
  const y = progress * END_Y_VH;

  return (
    <div
      className="fixed inset-0 z-0 flex items-center justify-center overflow-hidden"
      style={{
        transform: `scale(${scale}) translateY(${y}vh)`,
        willChange: "transform",
      }}
    >
      <div className="relative w-[135vmin] max-w-none shrink-0">
        <Globe
          className="max-w-none"
          markers={EUROPEAN_MARKERS}
          selectedId={selectedCountry?.id ?? null}
          paused={selectedCountry !== null}
          rotateSpeed={reducedMotion ? 0 : 0.002}
          onMarkerClick={handleMarkerClick}
          onBackgroundClick={closePopup}
        />
        {selectedCountry && anchor && (
          <CountryPopup
            country={selectedCountry}
            anchor={anchor}
            data={countryData}
            loading={loading}
            error={kpiError}
            onClose={closePopup}
          />
        )}
      </div>
      <div
        className="pointer-events-none absolute bottom-8 left-1/2 -translate-x-1/2 text-sm text-black/40 transition-opacity duration-500 dark:text-white/40"
        style={{ opacity: Math.max(0, 1 - progress * 2) }}
      >
        Scroll to explore ↓
      </div>
    </div>
  );
}
