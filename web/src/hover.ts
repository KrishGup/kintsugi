/* One hovered dimension for the whole workspace. A check row, a guide row or a bound slider says "I'm about
   neck_ring.ring_outer_diameter" while the pointer is on it; the 3D view draws the section it was measured on, and
   every other pane's row for the same dimension lights up. */

import { useEffect, useState } from "react";

const EVENT = "kin:hover-dim";
let hovered: string | null = null;
let pinned: string | null = null;
let current: string | null = null;

function emit() {
  const next = hovered ?? pinned;
  if (next === current) return;
  current = next;
  window.dispatchEvent(new CustomEvent(EVENT, { detail: next }));
}

export function hoverDim(dim: string | null) {
  hovered = dim;
  emit();
}

/** A click (or a tap, where there is no hover) keeps the dimension in focus until the next click; clicking it again lets go. */
export function pinDim(dim: string | null) {
  pinned = pinned === dim ? null : dim;
  emit();
}

export function pinnedDim(): string | null {
  return pinned;
}

export function useHoveredDim(): string | null {
  const [dim, setDim] = useState<string | null>(current);
  useEffect(() => {
    const on = (e: Event) => setDim((e as CustomEvent<string | null>).detail);
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, []);
  return dim;
}

/** Spread onto any element that stands for a dimension. Keyboard focus counts as hovering. */
export function hoverProps(dim: string | null | undefined, opts: { pin?: boolean } = {}) {
  if (!dim) return {};
  return {
    onMouseEnter: () => hoverDim(dim),
    onMouseLeave: () => hoverDim(null),
    onFocus: () => hoverDim(dim),
    onBlur: () => hoverDim(null),
    ...(opts.pin ? { onClick: () => pinDim(dim) } : {}),
  };
}
