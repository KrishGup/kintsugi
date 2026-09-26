/* Resizable workspace columns: the guide and details panes have a drag handle on their inner edge. Drag to size,
   double-click to reset, drag past the minimum to fold the pane away (a slim strip brings it back). Keyboard: focus
   the handle, arrows resize, Home/End go to the limits. Widths persist per browser. Phones never see any of this. */

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "../icons";

export type Side = "left" | "right";

export interface Columns {
  left: number;
  right: number;
  leftOpen: boolean;
  rightOpen: boolean;
}

export const DEFAULT_COLUMNS: Columns = { left: 350, right: 360, leftOpen: true, rightOpen: true };
const KEY = "kin.ws.cols";
const MIN = { left: 260, right: 300 };
const MAX = { left: 640, right: 760 };
const CENTER_MIN = 380;    // the 3D view never gets squeezed below this
const HANDLE = 10;         // px, the visual gap between panes doubles as the grab area
const FOLD_BELOW = 70;     // dragging this far under the minimum folds the pane away

function load(): Columns {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_COLUMNS;
    const v = JSON.parse(raw) as Partial<Columns>;
    return {
      left: clamp(Number(v.left) || DEFAULT_COLUMNS.left, MIN.left, MAX.left),
      right: clamp(Number(v.right) || DEFAULT_COLUMNS.right, MIN.right, MAX.right),
      leftOpen: v.leftOpen !== false,
      rightOpen: v.rightOpen !== false,
    };
  } catch {
    return DEFAULT_COLUMNS;
  }
}

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v));
}

export function useColumns(container: React.RefObject<HTMLElement>) {
  const [cols, setColsState] = useState<Columns>(load);
  const setCols = useCallback((next: Columns | ((c: Columns) => Columns)) => {
    setColsState((prev) => {
      const v = typeof next === "function" ? next(prev) : next;
      try {
        localStorage.setItem(KEY, JSON.stringify(v));
      } catch {
        /* per-viewer convenience only */
      }
      return v;
    });
  }, []);

  /** the widest a side may be right now, so the centre keeps CENTER_MIN */
  const maxFor = useCallback(
    (side: Side, c: Columns) => {
      const total = container.current?.clientWidth ?? 1600;
      const other = side === "left" ? (c.rightOpen ? c.right : 0) : c.leftOpen ? c.left : 0;
      return Math.max(MIN[side], Math.min(MAX[side], total - other - CENTER_MIN - 2 * HANDLE - 20));
    },
    [container],
  );

  const resize = useCallback(
    (side: Side, px: number) =>
      setCols((c) => {
        const open = side === "left" ? "leftOpen" : "rightOpen";
        if (px < MIN[side] - FOLD_BELOW) return { ...c, [open]: false };
        return { ...c, [side]: clamp(px, MIN[side], maxFor(side, c)), [open]: true };
      }),
    [setCols, maxFor],
  );
  const toggle = useCallback(
    (side: Side) =>
      setCols((c) => {
        const open = side === "left" ? "leftOpen" : "rightOpen";
        return { ...c, [open]: !c[open] };
      }),
    [setCols],
  );
  const reset = useCallback(
    (side: Side) =>
      setCols((c) => ({ ...c, [side]: DEFAULT_COLUMNS[side], [side === "left" ? "leftOpen" : "rightOpen"]: true })),
    [setCols],
  );

  return { cols, resize, toggle, reset, min: MIN, max: MAX };
}

interface HandleProps {
  side: Side;
  width: number;
  open: boolean;
  min: number;
  max: number;
  label: string;                       // the pane it sizes: "Guide", "Details"
  onResize: (px: number) => void;
  onReset: () => void;
  onToggle: () => void;
}

export function ColumnHandle({ side, width, open, min, max, label, onResize, onReset, onToggle }: HandleProps) {
  const start = useRef<{ x: number; w: number; onFold: boolean; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);

  // one gesture model for the whole strip, fold button included: press and move = resize, press and release = the
  // button's click (when it was pressed), double-click off the button = reset
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const onFold = !!(e.target as HTMLElement).closest(".ws-handle-fold");
    if (!open && !onFold) return;
    start.current = { x: e.clientX, w: width, onFold, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
    e.preventDefault();
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = start.current;
    if (!st || !open) return;
    const dx = e.clientX - st.x;
    if (!st.moved && Math.abs(dx) < 4) return;
    if (!st.moved) {
      st.moved = true;
      setDragging(true);
    }
    onResize(st.w + (side === "left" ? dx : -dx));
  };
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = start.current;
    if (!st) return;
    start.current = null;
    setDragging(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* already released */
    }
    if (st.onFold && !st.moved && e.type !== "pointercancel") onToggle();
  };
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const grow = side === "left" ? "ArrowRight" : "ArrowLeft";
    const shrink = side === "left" ? "ArrowLeft" : "ArrowRight";
    const step = e.shiftKey ? 64 : 16;
    if (e.key === grow) onResize((open ? width : min) + step);
    else if (e.key === shrink) onResize(width - step);
    else if (e.key === "Home") onResize(min);
    else if (e.key === "End") onResize(max);
    else if (e.key === "Enter" || e.key === " ") onToggle();
    else return;
    e.preventDefault();
  };

  useEffect(() => {
    document.body.classList.toggle("is-resizing", dragging);
    return () => document.body.classList.remove("is-resizing");
  }, [dragging]);

  const Chevron = (side === "left") === open ? ChevronLeft : ChevronRight;
  return (
    <div
      className={`ws-handle ws-handle--${side}${dragging ? " dragging" : ""}${open ? "" : " folded"}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={`${label} pane width`}
      aria-valuenow={open ? Math.round(width) : 0}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={(e) => {
        if (!(e.target as HTMLElement).closest(".ws-handle-fold")) onReset();
      }}
      onKeyDown={onKeyDown}
    >
      <span className="ws-handle-line" aria-hidden="true" />
      <button
        type="button"
        className="ws-handle-fold"
        aria-label={open ? `Hide the ${label.toLowerCase()} pane` : `Show the ${label.toLowerCase()} pane`}
        aria-expanded={open}
        tabIndex={-1}
        onClick={(e) => {
          // pointer presses are handled by the strip (capture); this only fires for keyboard/assistive activation
          if (e.detail === 0) onToggle();
        }}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <Chevron size={12} stroke={2.4} />
      </button>
      {!open && <span className="ws-handle-label">{label}</span>}
    </div>
  );
}
