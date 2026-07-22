"use client";

import createGlobe from "cobe";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import type { CountryMarker } from "@/components/european-markers";

// cobe 2.x renders one frame per update() call and has no onRender callback —
// the rAF loop below drives rotation. Markers sit at radius 0.8 + elevation
// (cobe's ee + markerElevation); project() replicates cobe's internal U()/O()
// math for a square canvas so clicks and popups can be mapped to exact marker
// screen positions using the current phi/theta/scale.

// The centre of the visible disc sits at latitude ~= theta (radians). At 0.4
// (23°N) that centred the Sahara and pushed Europe off the top edge; 0.80
// (~46°N) frames the continent, keeping Scandinavia and the Mediterranean in
// view together.
const THETA_INIT = 0.8;
// Clamp range for free vertical drag — stays short of the poles so the globe
// never flips upside down or rotates through a degenerate view.
const THETA_MIN = -1.4;
const THETA_MAX = 1.4;
const MARKER_RADIUS = 0.85; // 0.8 sphere + 0.05 default markerElevation
// cobe sizes markers as a fraction of the globe, and the hero globe is far
// wider than the viewport — at the catalog's authored sizes the dots rendered
// ~45px across and merged into blobs over dense western Europe. Scale them
// down here rather than rewriting all 56 catalog entries.
const MARKER_SCALE = 0.34;
// phi that puts ~10°E (central Europe) at the front-center of the globe
const EUROPE_PHI = 4.54;
const AUTO_SPEED = 0.005;
const DRAG_SENSITIVITY = 200; // px per radian, same feel as the cobe examples
const HIT_RADIUS = 0.045; // click threshold, as a fraction of canvas width

// Scroll-to-zoom: wheel up over the globe grows `scale` (cobe's native zoom
// factor) toward SCALE_MAX; wheel down shrinks it back down to SCALE_MIN —
// never below it, so this never triggers/duplicates the page's own
// scroll-driven hero shrink animation.
const SCALE_MIN = 1;
const SCALE_MAX = 2.5;
const ZOOM_SENSITIVITY = 0.0015;

const ORANGE: [number, number, number] = [251 / 255, 100 / 255, 21 / 255];
const EMERALD: [number, number, number] = [16 / 255, 185 / 255, 129 / 255];

// Mirrors cobe's internal projection (see O() in cobe/dist/index.esm.js) so
// marker hit-testing and label placement stay accurate as phi/theta/scale change.
function project(location: [number, number], phi: number, theta: number, scale: number) {
  const lat = (location[0] * Math.PI) / 180;
  const lng = (location[1] * Math.PI) / 180 - Math.PI;
  const c = Math.cos(lat);
  const v = [-c * Math.cos(lng) * MARKER_RADIUS, Math.sin(lat) * MARKER_RADIUS, c * Math.sin(lng) * MARKER_RADIUS];
  const cT = Math.cos(theta), sT = Math.sin(theta);
  const cP = Math.cos(phi), sP = Math.sin(phi);
  const x = cP * v[0] + sP * v[2];
  const y = sP * sT * v[0] + cT * v[1] - cP * sT * v[2];
  const z = -sP * cT * v[0] + sT * v[1] + cP * cT * v[2];
  return { x: (x * scale + 1) / 2, y: (1 - y * scale) / 2, front: z >= 0 };
}

function clamp(v: number, min: number, max: number) {
  return Math.min(max, Math.max(min, v));
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
  const thetaRef = useRef(THETA_INIT);
  const scaleRef = useRef(SCALE_MIN);
  const dragDeltaRef = useRef(0);
  const dragDeltaYRef = useRef(0);
  const draggingRef = useRef<{ startX: number; startY: number; mouse: boolean; moved: boolean } | null>(null);
  const pausedRef = useRef(paused);
  const speedRef = useRef(rotateSpeed);
  const selectedIdRef = useRef(selectedId);
  const callbacksRef = useRef({ onMarkerClick, onBackgroundClick });
  const globeRef = useRef<ReturnType<typeof createGlobe> | null>(null);
  const [dark, setDark] = useState<boolean | null>(null);
  // Only eight anchors carry a resting label; every other marker reveals its
  // name on hover, which keeps dense western Europe readable at rest.
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  pausedRef.current = paused;
  speedRef.current = rotateSpeed;
  selectedIdRef.current = selectedId;
  callbacksRef.current = { onMarkerClick, onBackgroundClick };

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setDark(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // cobe scales a marker's screen radius by the same `scale` factor as its
  // position (see the "be" vertex shader in cobe/dist/index.esm.js), so
  // without compensation markers balloon into overlapping blobs when zoomed
  // in. Dividing by scale keeps their on-screen size constant, like map pins.
  const cobeMarkers = (selected: string | null | undefined, scale: number) =>
    markers.map((m) => ({
      location: m.location,
      // Selected marker grows too, on top of its color swap, so the
      // "pointed" country is unambiguous even before the popup renders.
      size: ((m.id === selected ? m.size * 1.7 : m.size) * MARKER_SCALE) / scale,
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
      theta: thetaRef.current,
      dark: dark ? 1 : 0,
      diffuse: dark ? 1.2 : 0.4,
      mapSamples: 22000,
      mapBrightness: dark ? 6.5 : 1.5,
      baseColor: dark ? [0.22, 0.22, 0.25] : [1, 1, 1],
      markerColor: ORANGE,
      glowColor: dark ? [0.08, 0.08, 0.1] : [1, 1, 1],
      markers: cobeMarkers(selectedId, scaleRef.current),
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
        theta: clamp(thetaRef.current + dragDeltaYRef.current / DRAG_SENSITIVITY, THETA_MIN, THETA_MAX),
        scale: scaleRef.current,
        // Recomputed every frame (cheap: ~56 markers) so the zoom-size
        // compensation and selection highlight always match current state.
        markers: cobeMarkers(selectedIdRef.current, scaleRef.current),
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
    // markers identity is stable (module constant); selectedId/scale changes
    // are picked up every frame from refs above, not by re-creating the globe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dark]);

  // Wheel-to-zoom: only while the cursor is over the globe, so it never
  // steals scroll from the rest of the page. React's onWheel is passive by
  // default (preventDefault would be ignored), so this listens natively.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      scaleRef.current = clamp(scaleRef.current - e.deltaY * ZOOM_SENSITIVITY, SCALE_MIN, SCALE_MAX);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const currentPhi = () => phiRef.current + dragDeltaRef.current / DRAG_SENSITIVITY;
  const currentTheta = () =>
    clamp(thetaRef.current + dragDeltaYRef.current / DRAG_SENSITIVITY, THETA_MIN, THETA_MAX);

  const markerAtPoint = (clientX: number, clientY: number) => {
    const box = containerRef.current!.getBoundingClientRect();
    const fx = (clientX - box.left) / box.width;
    const fy = (clientY - box.top) / box.height;
    const phi = currentPhi();
    const theta = currentTheta();
    const scale = scaleRef.current;
    let best: { m: CountryMarker; d: number } | null = null;
    for (const m of markers) {
      const p = project(m.location, phi, theta, scale);
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
    const p = project(m.location, currentPhi(), currentTheta(), scaleRef.current);
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
          // Vertical drag tilts (theta) on mouse/pen only — touch keeps
          // touch-action:pan-y so a vertical finger-drag still scrolls the
          // page, matching today's mobile behavior.
          draggingRef.current = { startX: e.clientX, startY: e.clientY, mouse: e.pointerType !== "touch", moved: false };
          try {
            e.currentTarget.setPointerCapture(e.pointerId);
          } catch {
            // synthetic events carry no active pointer; drag still works
          }
          e.currentTarget.style.cursor = "grabbing";
        }}
        onPointerMove={(e) => {
          const drag = draggingRef.current;
          if (!drag) {
            // Not dragging: hit-test under the cursor so the marker can name
            // itself. Mouse/pen only — a touch "hover" would fire on tap and
            // fight the popup.
            if (e.pointerType !== "touch") {
              const hit = markerAtPoint(e.clientX, e.clientY);
              setHoveredId(hit?.id ?? null);
              e.currentTarget.style.cursor = hit ? "pointer" : "grab";
            }
            return;
          }
          const delta = e.clientX - drag.startX;
          const deltaY = drag.mouse ? e.clientY - drag.startY : 0;
          if (!drag.moved && (Math.abs(delta) > 5 || Math.abs(deltaY) > 5)) {
            drag.moved = true;
            callbacksRef.current.onBackgroundClick?.(); // dismiss popup on drag
          }
          if (drag.moved) {
            dragDeltaRef.current = delta;
            dragDeltaYRef.current = deltaY;
          }
        }}
        onPointerUp={(e) => {
          const drag = draggingRef.current;
          draggingRef.current = null;
          e.currentTarget.style.cursor = "grab";
          phiRef.current += dragDeltaRef.current / DRAG_SENSITIVITY;
          thetaRef.current = clamp(
            thetaRef.current + dragDeltaYRef.current / DRAG_SENSITIVITY,
            THETA_MIN,
            THETA_MAX,
          );
          dragDeltaRef.current = 0;
          dragDeltaYRef.current = 0;
          if (drag && !drag.moved) {
            const hit = markerAtPoint(e.clientX, e.clientY);
            if (hit) selectMarker(hit);
            else callbacksRef.current.onBackgroundClick?.();
          }
        }}
        onPointerLeave={() => setHoveredId(null)}
        onPointerCancel={() => {
          setHoveredId(null);
          draggingRef.current = null;
          phiRef.current += dragDeltaRef.current / DRAG_SENSITIVITY;
          thetaRef.current = clamp(
            thetaRef.current + dragDeltaYRef.current / DRAG_SENSITIVITY,
            THETA_MIN,
            THETA_MAX,
          );
          dragDeltaRef.current = 0;
          dragDeltaYRef.current = 0;
        }}
      />
      {markers
        .filter((m) => m.labeled || m.id === hoveredId || m.id === selectedId)
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
