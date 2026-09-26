/* One icon family for the whole interface: 24-unit grid, round caps, one stroke weight. Sized by `size` (px). */

interface P {
  size?: number;
  stroke?: number;
  className?: string;
  title?: string;
}

function Svg({ size = 14, stroke = 2, className, title, children }: P & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      focusable="false"
    >
      {title && <title>{title}</title>}
      {children}
    </svg>
  );
}

export const Check = (p: P) => (
  <Svg {...p} stroke={p.stroke ?? 2.6}>
    <path d="m4 12.5 5 5L20 6.5" />
  </Svg>
);
export const Cross = (p: P) => (
  <Svg {...p} stroke={p.stroke ?? 2.4}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);
export const Close = (p: P) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);
export const Undo = (p: P) => (
  <Svg {...p}>
    <path d="M9 14 4 9l5-5" />
    <path d="M4 9h10a6 6 0 0 1 0 12h-3" />
  </Svg>
);
export const Redo = (p: P) => (
  <Svg {...p}>
    <path d="m15 14 5-5-5-5" />
    <path d="M20 9H10a6 6 0 0 0 0 12h3" />
  </Svg>
);
export const Reset = (p: P) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 1 0 3-6.7" />
    <path d="M3 4v5h5" />
  </Svg>
);
export const ChevronDown = (p: P) => (
  <Svg {...p}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
);
export const ChevronRight = (p: P) => (
  <Svg {...p}>
    <path d="m9 6 6 6-6 6" />
  </Svg>
);
export const More = (p: P) => (
  <Svg {...p} stroke={0}>
    <circle cx="5" cy="12" r="2" fill="currentColor" />
    <circle cx="12" cy="12" r="2" fill="currentColor" />
    <circle cx="19" cy="12" r="2" fill="currentColor" />
  </Svg>
);
export const Dot = (p: P) => (
  <Svg {...p} stroke={0}>
    <circle cx="12" cy="12" r="3" fill="currentColor" />
  </Svg>
);
export const Camera = (p: P) => (
  <Svg {...p}>
    <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
    <circle cx="12" cy="13" r="3.2" />
  </Svg>
);
export const Download = (p: P) => (
  <Svg {...p}>
    <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v3h16v-3" />
  </Svg>
);
export const Gear = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </Svg>
);
export const Search = (p: P) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Svg>
);
export const Star = (p: P) => (
  <Svg {...p}>
    <path d="m12 3 2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.4 6.3 20.5l1.2-6.4L2.8 9.7l6.4-.8L12 3z" />
  </Svg>
);
export const Sliders = (p: P) => (
  <Svg {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
    <circle cx="9" cy="7" r="2" fill="currentColor" />
    <circle cx="15" cy="12" r="2" fill="currentColor" />
    <circle cx="7" cy="17" r="2" fill="currentColor" />
  </Svg>
);
export const Plus = (p: P) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);
export const Play = (p: P) => (
  <Svg {...p} stroke={0}>
    <path d="M7 4.5v15l12-7.5z" fill="currentColor" />
  </Svg>
);
export const Stop = (p: P) => (
  <Svg {...p} stroke={0}>
    <rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor" />
  </Svg>
);
export const Cube = (p: P) => (
  <Svg {...p} stroke={p.stroke ?? 1.4}>
    <path d="M12 3 3 7.5v9L12 21l9-4.5v-9L12 3z" />
    <path d="M3 7.5 12 12l9-4.5M12 12v9" />
  </Svg>
);
export const Ruler = (p: P) => (
  <Svg {...p} stroke={p.stroke ?? 1.6}>
    <path d="M3 17 17 3l4 4L7 21z" />
    <path d="m7 13 2 2M10 10l2 2M13 7l2 2" />
  </Svg>
);
