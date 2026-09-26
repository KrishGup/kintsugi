/* One hovered dimension for the whole workspace. A check row, a guide row or a bound slider says "I'm about
   neck_ring.ring_outer_diameter" while the pointer is on it; the 3D view draws the section it was measured on, and
   every other pane's row for the same dimension lights up. */

import { useEffect, useState } from "react";

const EVENT = "kin:hover-dim";
let current: string | null = null;

export function hoverDim(dim: string | null) {
  if (dim === current) return;
  current = dim;
  window.dispatchEvent(new CustomEvent(EVENT, { detail: dim }));
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
export function hoverProps(dim: string | null | undefined) {
  if (!dim) return {};
  return {
    onMouseEnter: () => hoverDim(dim),
    onMouseLeave: () => hoverDim(null),
    onFocus: () => hoverDim(dim),
    onBlur: () => hoverDim(null),
  };
}
