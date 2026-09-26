/* The one brand mark: a single stroke on the accent square (`.brand-mark`). Used by the home header, the session top bar and the sign-in gate. */

export function Mark({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="var(--on-accent)" strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true" focusable="false">
      <path d="M4 19 10 5l4 8 6-9" />
    </svg>
  );
}
