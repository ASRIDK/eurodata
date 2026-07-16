"use client";

import createGlobe from "cobe";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import type { CountryMarker } from "@/components/european-markers";

// cobe 2.x renders one frame per update() call and has no onRender callback —
// the rAF loop below drives rotation. Markers sit at radius 0.8 + elevation
// (cobe's ee + markerElevation); project() replicates cobe's internal U()/O()
// math for a square canvas at scale 1 so clicks and popups can be mapped to
// exact marker screen positions using the current phi/theta.

const THETA = 0.4; // fixed tilt toward the northern hemisphere
const MARKER_RADIUS = 0.85; // 0.8 sphere + 0.05 default markerElevation
// phi that puts ~10°E (central Europe) at the front-center of the globe
const EUROPE_PHI = 4.54;
const AUTO_SPEED = 0.005;
const DRAG_SENSITIVITY = 200; // px per radian, same feel as the cobe examples
const HIT_RADIUS = 0.045; // click threshold, as a fraction of canvas width

const ORANGE: [number, number, number] = [251 / 255, 100 / 255, 21 / 255];
const EMERALD: [number, number, number] = [16 / 255, 185 / 255, 129 / 255];

function project(location: [number, number], phi: number) {
  const lat = (location[0] * Math.PI) / 180;
  const lng = (location[1] * Math.PI) / 180 - Math.PI;
  const c = Math.cos(lat);
  const v = [-c * Math.cos(lng) * MARKER_RADIUS, Math.sin(lat) * MARKER_RADIUS, c * Math.sin(lng) * MARKER_RADIUS];
  const cT = Math.cos(THETA), sT = Math.sin(THETA);
  const cP = Math.cos(phi), sP = Math.sin(phi);
  const x = cP * v[0] + sP * v[2];
  const y = sP * sT * v[0] + cT * v[1] - cP * sT * v[2];
  const z = -sP * cT * v[0] + sT * v[1] + cP * cT * v[2];
  return { x: (x + 1) / 2, y: (1 - y) / 2, front: z >= 0 };
}

export function Globe({
  markers,
  selectedId,
  paused = false,
  rotateSpeed = AUTO_SPEED,
  onMarkerClick,
  onBackgroundClick,
  className,
}: {
  markers: CountryMarker[];
  selectedId?: string | null;
  paused?: boolean;
  /** Radians per frame of auto-rotation; 0 disables (reduced motion). */
  rotateSpeed?: number;
  /** Marker chosen by canvas hit detection or a label click; pos is in px within the globe container. */
  onMarkerClick?: (marker: CountryMarker, pos: { x: number; y: number }) => void;
  /** Click that hit no marker, or the start of a drag. */
  onBackgroundClick?: () => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const phiRef = useRef(EUROPE_PHI);
  const dragDeltaRef = useRef(0);
  const draggingRef = useRef<{ startX: number; moved: boolean } | null>(null);
  const pausedRef = useRef(paused);
  const speedRef = useRef(rotateSpeed);
  const callbacksRef = useRef({ onMarkerClick, onBackgroundClick });
  const globeRef = useRef<ReturnType<typeof createGlobe> | null>(null);
  const [dark, setDark] = useState<boolean | null>(null);

  pausedRef.current = paused;
  speedRef.current = rotateSpeed;
  callbacksRef.current = { onMarkerClick, onBackgroundClick };

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setDark(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const cobeMarkers = (selected: string | null | undefined) =>
    markers.map((m) => ({
      location: m.location,
      size: m.size,
      id: m.id,
      ...(m.id === selected ? { color: EMERALD } : {}),
    }));

  useEffect(() => {
    if (dark === null || !canvasRef.current || !containerRef.current) return;
    const canvas = canvasRef.current;
    let width = containerRef.current.offsetWidth || 600;
    let sizeDirty = false;

    const globe = createGlobe(canvas, {
      width,
      height: width,
      devicePixelRatio: 2,
      phi: phiRef.current,
      theta: THETA,
      dark: dark ? 1 : 0,
      diffuse: dark ? 1.2 : 0.4,
      mapSamples: 16000,
      mapBrightness: dark ? 6 : 1.2,
      baseColor: dark ? [0.22, 0.22, 0.25] : [1, 1, 1],
      markerColor: ORANGE,
      glowColor: dark ? [0.08, 0.08, 0.1] : [1, 1, 1],
      markers: cobeMarkers(selectedId),
    });
    globeRef.current = globe;
    setTimeout(() => {
      canvas.style.opacity = "1";
    });

    const ro = new ResizeObserver(() => {
      const w = containerRef.current?.offsetWidth;
      if (w && w !== width) {
        width = w;
        sizeDirty = true;
      }
    });
    ro.observe(containerRef.current);

    let raf = requestAnimationFrame(function frame() {
      if (!draggingRef.current && !pausedRef.current) phiRef.current += speedRef.current;
      const state: Parameters<typeof globe.update>[0] = {
        phi: phiRef.current + dragDeltaRef.current / DRAG_SENSITIVITY,
      };
      if (sizeDirty) {
        state.width = width;
        state.height = width;
        sizeDirty = false;
      }
      globe.update(state);
      raf = requestAnimationFrame(frame);
    });

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      globe.destroy();
      globeRef.current = null;
    };
    // markers identity is stable (module constant); selectedId changes are
    // applied via the lightweight update() effect below, not by re-creating.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dark]);

  useEffect(() => {
    globeRef.current?.update({ markers: cobeMarkers(selectedId) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const currentPhi = () => phiRef.current + dragDeltaRef.current / DRAG_SENSITIVITY;

  const markerAtPoint = (clientX: number, clientY: number) => {
    const box = containerRef.current!.getBoundingClientRect();
    const fx = (clientX - box.left) / box.width;
    const fy = (clientY - box.top) / box.height;
    const phi = currentPhi();
    let best: { m: CountryMarker; d: number } | null = null;
    for (const m of markers) {
      const p = project(m.location, phi);
      if (!p.front) continue;
      const d = Math.hypot(p.x - fx, p.y - fy);
      if (d < HIT_RADIUS && (!best || d < best.d)) best = { m, d };
    }
    return best?.m ?? null;
  };

  const selectMarker = (m: CountryMarker) => {
    // offsetWidth/Height (layout px), not getBoundingClientRect: the popup is
    // positioned in the container's untransformed coordinate space, and an
    // ancestor may carry a CSS scale (the scroll-shrinking hero).
    const el = containerRef.current!;
    const p = project(m.location, currentPhi());
    callbacksRef.current.onMarkerClick?.(m, { x: p.x * el.offsetWidth, y: p.y * el.offsetHeight });
  };

  return (
    <div
      ref={containerRef}
      className={cn("relative mx-auto aspect-square w-full max-w-[600px]", className)}
    >
      <canvas
        ref={canvasRef}
        className="size-full cursor-grab opacity-0 transition-opacity duration-500 [contain:layout_paint_size] [touch-action:pan-y]"
        onPointerDown={(e) => {
          draggingRef.current = { startX: e.clientX, moved: false };
          try {
            e.currentTarget.setPointerCapture(e.pointerId);
          } catch {
            // synthetic events carry no active pointer; drag still works
          }
          e.currentTarget.style.cursor = "grabbing";
        }}
        onPointerMove={(e) => {
          const drag = draggingRef.current;
          if (!drag) return;
          const delta = e.clientX - drag.startX;
          if (!drag.moved && Math.abs(delta) > 5) {
            drag.moved = true;
            callbacksRef.current.onBackgroundClick?.(); // dismiss popup on drag
          }
          if (drag.moved) dragDeltaRef.current = delta;
        }}
        onPointerUp={(e) => {
          const drag = draggingRef.current;
          draggingRef.current = null;
          e.currentTarget.style.cursor = "grab";
          phiRef.current += dragDeltaRef.current / DRAG_SENSITIVITY;
          dragDeltaRef.current = 0;
          if (drag && !drag.moved) {
            const hit = markerAtPoint(e.clientX, e.clientY);
            if (hit) selectMarker(hit);
            else callbacksRef.current.onBackgroundClick?.();
          }
        }}
        onPointerCancel={() => {
          draggingRef.current = null;
          phiRef.current += dragDeltaRef.current / DRAG_SENSITIVITY;
          dragDeltaRef.current = 0;
        }}
      />
      {markers
        .filter((m) => m.labeled)
        .map((m) => (
          <button
            key={m.id}
            type="button"
            tabIndex={-1}
            className="marker-label rounded-full bg-white/75 px-1.5 py-0.5 text-[10px] font-medium text-black/70 shadow-sm backdrop-blur-sm dark:bg-black/60 dark:text-white/80"
            style={
              {
                positionAnchor: `--cobe-${m.id}`,
                // --cobe-visible-{id} only exists while the marker faces the
                // camera; when set, these declarations become invalid at
                // computed-value time and fall back to their initial (visible)
                // values — when unset, the var() fallbacks hide the label.
                opacity: `var(--cobe-visible-${m.id}, 0)`,
                filter: `blur(calc((1 - var(--cobe-visible-${m.id}, 0)) * 4px))`,
                pointerEvents: `var(--cobe-visible-${m.id}, none)`,
              } as unknown as React.CSSProperties
            }
            onClick={() => selectMarker(m)}
          >
            {m.city}
          </button>
        ))}
    </div>
  );
}
