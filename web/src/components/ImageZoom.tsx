import { useCallback, useEffect, useRef, useState, type PointerEvent as RPointerEvent, type WheelEvent as RWheelEvent } from "react";
import { Empty, Spinner } from "../ui";

interface Props {
  src: string | null;
  alt: string;
  placeholder?: string;
}

interface View {
  scale: number;
  x: number;
  y: number;
}

/** Zoomable / pannable image (CSS transforms). Fit-to-width on load, wheel to zoom, drag to pan, double-click to fit. */
export default function ImageZoom({ src, alt, placeholder }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const img = useRef<HTMLImageElement>(null);
  const [view, setView] = useState<View>({ scale: 1, x: 0, y: 0 });
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const drag = useRef<{ px: number; py: number; vx: number; vy: number; id: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const fit = useCallback(
    (mode: "fit" | "width" | "one" = "fit") => {
      const el = host.current;
      if (!el || !natural) return;
      const W = el.clientWidth;
      const H = el.clientHeight;
      let scale = 1;
      if (mode === "width") scale = (W - 24) / natural.w;
      else if (mode === "fit") scale = Math.min((W - 24) / natural.w, (H - 24) / natural.h);
      scale = Math.max(0.02, Math.min(scale, mode === "one" ? 1 : 2));
      const x = (W - natural.w * scale) / 2;
      const y = mode === "fit" ? (H - natural.h * scale) / 2 : 12;
      setView({ scale, x, y: Math.max(y, mode === "fit" ? y : 12) });
    },
    [natural],
  );

  useEffect(() => {
    setNatural(null);
    setFailed(false);
    setLoading(!!src);
  }, [src]);

  useEffect(() => {
    if (natural) fit("fit");
  }, [natural, fit]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      if (natural) fit("fit");
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [natural, fit]);

  const onWheel = (e: RWheelEvent<HTMLDivElement>) => {
    if (!natural) return;
    const el = host.current!;
    const rect = el.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = Math.exp(-e.deltaY * 0.0016);
    setView((v) => {
      const scale = Math.max(0.02, Math.min(v.scale * factor, 12));
      const k = scale / v.scale;
      return { scale, x: mx - (mx - v.x) * k, y: my - (my - v.y) * k };
    });
  };

  const onPointerDown = (e: RPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || !natural) return;
    drag.current = { px: e.clientX, py: e.clientY, vx: view.x, vy: view.y, id: e.pointerId };
    (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
    setDragging(true);
  };
  const onPointerMove = (e: RPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    setView((v) => ({ ...v, x: d.vx + (e.clientX - d.px), y: d.vy + (e.clientY - d.py) }));
  };
  const onPointerUp = (e: RPointerEvent<HTMLDivElement>) => {
    if (drag.current) {
      try {
        (e.currentTarget as HTMLDivElement).releasePointerCapture(drag.current.id);
      } catch {
        /* ignore */
      }
    }
    drag.current = null;
    setDragging(false);
  };

  // React attaches wheel listeners passively; use a native non-passive one so preventDefault works.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const handler = (e: WheelEvent) => e.preventDefault();
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, []);

  if (!src) {
    return (
      <div className="viewer-overlay">
        <Empty title="Nothing rendered yet" icon={<SheetIcon />}>
          {placeholder || "Blueprint sheets are rendered after each iteration compiles."}
        </Empty>
      </div>
    );
  }

  return (
    <div
      className={`zoomer${dragging ? " dragging" : ""}`}
      ref={host}
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={() => fit("fit")}
      role="img"
      aria-label={alt}
    >
      <img
        ref={img}
        src={src}
        alt={alt}
        draggable={false}
        onLoad={(e) => {
          const t = e.currentTarget;
          setNatural({ w: t.naturalWidth, h: t.naturalHeight });
          setLoading(false);
        }}
        onError={() => {
          setLoading(false);
          setFailed(true);
        }}
        style={{
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
          visibility: natural ? "visible" : "hidden",
        }}
      />
      <div className="zoomer-tools" onPointerDown={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
        <button className="btn btn-xs" onClick={() => fit("fit")} title="Fit to pane">
          FIT
        </button>
        <button className="btn btn-xs" onClick={() => fit("width")} title="Fit to width">
          WIDTH
        </button>
        <button className="btn btn-xs" onClick={() => fit("one")} title="Actual pixels">
          1:1
        </button>
        <a className="btn btn-xs" href={src} target="_blank" rel="noreferrer" title="Open full size in a new tab">
          OPEN ↗
        </a>
      </div>
      {natural && (
        <div className="viewer-hud">
          <span>
            <b>{Math.round(view.scale * 100)}%</b>
          </span>
          <span>
            {natural.w} × {natural.h} px
          </span>
          <span>scroll to zoom · drag to pan · double-click to fit</span>
        </div>
      )}
      {loading && (
        <div className="viewer-overlay" style={{ pointerEvents: "none" }}>
          <Spinner label="Loading sheet…" />
        </div>
      )}
      {failed && (
        <div className="viewer-overlay">
          <Empty title="Sheet not available">The image could not be loaded.</Empty>
        </div>
      )}
    </div>
  );
}

function SheetIcon() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="1" />
      <path d="M3 9h18M8 9v11M14 4v5" />
    </svg>
  );
}
