/* The brand mark: a ring — the part — cracked on a diagonal and mended with a gold seam. Drawn on the 64-unit grid of
   docs/brand (scripts/brand_assets.py is the source of truth for the kit); this is the same drawing, inline, in the
   icon build (heavier strokes) because the header shows it at 22 px. The blue square around it is `.brand-mark`. */

const SEAM = "M17 15 L31 29 L26 37 L47 49";

export function Mark({ size = 22, heavy = true }: { size?: number; heavy?: boolean }) {
  const [rw, gap, sw, r] = heavy ? [8.0, 9.8, 4.4, 15.2] : [6.6, 8.6, 3.4, 16];
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <circle cx="32" cy="32" r={r} fill="none" stroke="var(--brand-ring)" strokeWidth={rw} />
      <path d={SEAM} fill="none" stroke="var(--brand-square)" strokeWidth={gap} strokeLinejoin="round" strokeLinecap="round" />
      <path d={SEAM} fill="none" stroke="var(--brand-seam)" strokeWidth={sw} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** The horizontal lockup used by the home header, the session top bar and the sign-in gate. */
export function Brand({ tagline }: { tagline?: string }) {
  return (
    <>
      <span className="brand-mark">
        <Mark />
      </span>
      <span className="brand-name">Kintsugi</span>
      {tagline && <span className="brand-tag">{tagline}</span>}
    </>
  );
}
