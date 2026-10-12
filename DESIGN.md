---
name: Kintsugi
description: A drafting sheet for verified replacement parts — navy ink, one action blue, measured values in mono.
colors:
  navy: "#05142e"
  blue: "#155dd3"
  blue-hover: "#124fb4"
  blue-soft: "#e2ecfc"
  mid: "#6c9ef0"
  pale: "#bed4f9"
  on-accent: "#ffffff"
  paper: "#f3f7fe"
  sheet: "#ffffff"
  sheet-2: "#f7fafe"
  overlay: "#ffffff"
  ink: "#05142e"
  ink-2: "#3c485c"
  ink-3: "#5b6982"
  ink-inverse: "#f3f7fe"
  rule: "#c9d6ec"
  rule-2: "#e1e9f5"
  focus-halo: "rgba(21, 93, 211, 0.22)"
  grid: "rgba(21, 93, 211, 0.05)"
  grid-major: "rgba(21, 93, 211, 0.075)"
  pass: "#1f7a46"
  pass-soft: "#e3f3ea"
  fail: "#b8322a"
  fail-soft: "#fbe7e5"
  warn: "#8f6008"
  warn-soft: "#fbf0d9"
  viewer-bg: "#eef3fb"
  viewer-part: "#d6dfeb"
  viewer-edge: "#4d5f80"
  viewer-context: "#c9a227"
typography:
  display:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, Helvetica Neue, Arial, sans-serif"
    fontSize: "36.5px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "0.005em"
  headline:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, Helvetica Neue, Arial, sans-serif"
    fontSize: "28.5px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "0.005em"
  title:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, Helvetica Neue, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "0.005em"
  body:
    fontFamily: "IBM Plex Sans, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, Helvetica Neue, Arial, sans-serif"
    fontSize: "15.5px"
    fontWeight: 700
    letterSpacing: "0.08em"
  label-small:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, Helvetica Neue, Arial, sans-serif"
    fontSize: "14.5px"
    fontWeight: 600
    letterSpacing: "0.06em"
  button:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, Helvetica Neue, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.02em"
  mono:
    fontFamily: "IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "15.5px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  sm: "4px"
  base: "5px"
  lg: "8px"
  pill: "999px"
  round: "50%"
spacing:
  xs: "5px"
  sm: "8px"
  md: "10px"
  lg: "13px"
  xl: "16px"
  2xl: "21px"
  3xl: "26px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.on-accent}"
    typography: "{typography.button}"
    rounded: "{rounded.base}"
    padding: "8px 14px"
    height: "39px"
  button-primary-hover:
    backgroundColor: "{colors.blue-hover}"
    textColor: "{colors.on-accent}"
  button-secondary:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.base}"
    padding: "8px 14px"
    height: "39px"
  button-secondary-hover:
    backgroundColor: "{colors.blue-soft}"
    textColor: "{colors.ink}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.button}"
    rounded: "{rounded.base}"
    padding: "8px 14px"
    height: "39px"
  button-ghost-hover:
    backgroundColor: "{colors.blue-soft}"
    textColor: "{colors.blue}"
  button-danger-hover:
    backgroundColor: "{colors.fail-soft}"
    textColor: "{colors.fail}"
  button-sm:
    size: "15.5px"
    padding: "5px 10px"
    height: "34px"
  button-xs:
    size: "14.5px"
    padding: "4px 8px"
    height: "29px"
  input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "8px 10px"
    size: "17px"
  input-disabled:
    backgroundColor: "{colors.sheet-2}"
    textColor: "{colors.ink}"
  input-number:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.mono}"
    rounded: "{rounded.base}"
    padding: "8px 10px"
    width: "109px"
  pill-neutral:
    backgroundColor: "{colors.sheet-2}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.pill}"
    padding: "4px 9px"
    size: "14.5px"
  pill-pass:
    backgroundColor: "{colors.pass-soft}"
    textColor: "{colors.pass}"
    rounded: "{rounded.pill}"
    padding: "4px 9px"
    size: "14.5px"
  pill-fail:
    backgroundColor: "{colors.fail-soft}"
    textColor: "{colors.fail}"
    rounded: "{rounded.pill}"
    padding: "4px 9px"
    size: "14.5px"
  pill-warn:
    backgroundColor: "{colors.warn-soft}"
    textColor: "{colors.warn}"
    rounded: "{rounded.pill}"
    padding: "4px 9px"
    size: "14.5px"
  pill-blue:
    backgroundColor: "{colors.blue-soft}"
    textColor: "{colors.blue}"
    rounded: "{rounded.pill}"
    padding: "4px 9px"
    size: "14.5px"
  chip:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-2}"
    typography: "{typography.mono}"
    rounded: "{rounded.sm}"
    padding: "4px 9px"
    size: "14.5px"
  tab:
    textColor: "{colors.ink-3}"
    padding: "0 9px"
    size: "15.5px"
  tab-active:
    textColor: "{colors.blue}"
    padding: "0 9px"
    size: "15.5px"
  panel:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.base}"
    padding: "16px"
  panel-head:
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    padding: "10px 16px"
    height: "49px"
  card:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "10px 13px"
    size: "16px"
  stage-current:
    backgroundColor: "{colors.blue-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "4px 13px 4px 8px"
    size: "15.5px"
  toast:
    backgroundColor: "{colors.overlay}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "12px 13px 12px 16px"
    size: "16px"
  popover:
    backgroundColor: "{colors.overlay}"
    rounded: "{rounded.lg}"
    padding: "16px"
    width: "416px"
  modal:
    backgroundColor: "{colors.overlay}"
    rounded: "{rounded.lg}"
    padding: "18px"
    width: "min(728px, 100%)"
  dim-label:
    textColor: "{colors.blue}"
    typography: "{typography.mono}"
    rounded: "{rounded.sm}"
    padding: "1px 6px"
    size: "14.5px"
  slider-thumb:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.round}"
    size: "21px"
  switch:
    backgroundColor: "{colors.rule-2}"
    rounded: "13px"
    width: "44px"
    height: "26px"
  switch-on:
    backgroundColor: "{colors.blue}"
    rounded: "13px"
    width: "44px"
    height: "26px"
---

# Design System: Kintsugi

## Overview

**Creative North Star: "The Drafting Sheet"**

Kintsugi's interface is an engineering drawing's sheet: fine grid paper under everything, white panels ruled with 1 px navy-tinted lines, title-block labels in tracked condensed capitals, dimension lines with ticks, and measured values set in tabular mono. One blue does every job that asks for a decision — the primary button, the link, the active tab, the caret, the focus ring — and two lighter blues serve it as tints: Dimension Blue for lines and ghosts, Tolerance Tint for selection and the band a measurement is allowed to live in. Nothing else in the palette speaks except the three status colours, and those never speak alone.

The voice is precise, calm and evidential. Density is earned by the task: the home page is spacious (one hero line, one dimension-line strip, two panels); the session workspace is dense (three panes, 17 px body, 16 px tables, 14 px column labels) because a maker reviewing checks wants every dimension on screen at once. Decoration is refused; expression lives in details a drafter would recognise — the ticks on the path, the pale bracket above a slider, the arrow before a target value. The system refuses the SaaS-dashboard arrangement of hero-metric cards: a status is a 9 px dot before a heading, a number is a measured value with its evidence, never a big tile.

Light is the default (a bench in daylight); dark is composed from the navy rather than inverted and follows the system setting. Type is self-hosted so the sheet renders with no CDN reachable.

**Key Characteristics:**
- Grid paper ground: a 31 px minor / 155 px major blueprint grid on the body, under every pane; panels never redraw it.
- Navy-tinted everything: inks, rules, shadows and the scrim all descend from #05142E — no neutral gray anywhere.
- One action blue (#155DD3), two servant tints (#6C9EF0, #BED4F9), three status colours that always carry a word or an icon.
- Two typefaces plus a mono: Barlow Semi Condensed for headings and tracked title-block labels, IBM Plex Sans body at 17 px, IBM Plex Mono with tabular figures for every measured value.
- Flat by default: 1 px rules and a whisper-faint rest shadow on panels; soft offset shadows only lift overlays.
- Crisp and measured forms: 4 / 5 / 8 px radii, pills only for status, one 24-unit stroke icon family.

## Colors

A navy-ink palette with one saturated action blue and two lighter blues as tints; every neutral is cool and navy-tinted, never gray.

### Primary
- **Action Blue** (#155DD3): every primary action, link, active tab underline, focus ring, caret and `accent-color`; the current-stage fill; the dimension lines in the 3D view and the dim-label text. It is the only colour that asks for a click.
- **Action Blue, pressed** (#124FB4): hover and active fill of the primary button only.
- **Action Blue, soft** (#E2ECFC): the hover and active fill of every secondary control, table-row and session-row hover, active segments and chips, inline code, and the tint on question and intake cards. In dark mode it becomes a 16 % blue wash.

### Secondary
- **Dimension Blue** (#6C9EF0): the dimension-line motif (the home path's 1 px rule and ticks), hover borders on buttons and inputs, the dashed file-drop border, empty-state icons, the tolerance band's outline, ghost meshes in the viewer. In dark mode it is promoted to the action colour with navy text on it.
- **Tolerance Tint** (#BED4F9): text selection, the slider's tolerance band fill (70 % over the sheet; 45 % for a spec range), the pressed state of secondary buttons; in dark mode the secondary ink.

### Tertiary
- **Pass Green** (#1F7A46 on #E3F3EA), **Fail Red** (#B8322A on #FBE7E5), **Warn Amber** (#8F6008 on #FBF0D9): pills, banners, chips, the 9 px status marker on timeline and request cards, slider marks, stage numbers once done. Tone borders are the colour at 35–60 % over transparent (`color-mix`). Every use is paired with a word or an icon.
- **Context Amber** (#C9A227): only the mating object drawn as a translucent proxy in the 3D view (17 % opacity) — the one warm colour, reserved for the thing the part fits into.

### Neutral
- **Drafting Ink** (#05142E): primary text, the brand navy, the dark-mode canvas, the slider's value bubble.
- **Ink 2** (#3C485C) / **Ink 3** (#5B6982): secondary and tertiary text — panel titles, hero copy and card labels on Ink 2; column labels, hints, placeholders, HUD readouts and inactive tabs on Ink 3.
- **Sheet Paper** (#F3F7FE): the canvas under the grid, and the inset background of read-only blocks (summary lines, derived values, guide cards, banners, status lines).
- **Sheet** (#FFFFFF): panels, panes, cards, inputs and buttons. **Sheet 2** (#F7FAFE): the inset second neutral for neutral pills, disabled inputs, empty states and the file drop.
- **Overlay** (#FFFFFF light / #14305A dark): toasts, popovers and the settings modal.
- **Rule** (#C9D6EC) and **Rule 2** (#E1E9F5): outer 1 px borders (panels, inputs, table heads) and inner dividers (rows, cards, count badges, the progress track, the switch rail).
- **Viewer bed** (#EEF3FB), **Viewer part** (#D6DFEB), **Viewer edge** (#4D5F80): the 3D pane's background, mesh and edge lines; the viewer reads its colours from the tokens at runtime so it belongs to whichever theme it sits in.
- **Grid** (rgba(21,93,211,.05) minor, .075 major): the blueprint lines of the sheet, drawn in the action blue at very low alpha; in dark mode from the pale blue at 5 % / 8 %.

**Dark mode** (`prefers-color-scheme: dark`) is composed from the navy: canvas #05142E, panels #0A1D3F, inset #0F2549, overlays #14305A; inks #E8F0FC / #BED4F9 / #86A3D2; rules #274572 / #1B3459. The action colour becomes #6C9EF0 with #05142E text on it (hover #86B0F5, soft fill rgba(108,158,240,.16)); selection flips to #155DD3 with white text; statuses lift to #5CC98A / #F08A80 / #E5B85C on #10352A / #47201F / #3D3117; the viewer bed is #071736 with a #B9C6DA part, #0B1C3B edges, #8FB5F4 dimension lines and an #E0B84A context ghost.

### Named Rules
**The One Blue Rule.** Only #155DD3 asks for action. The two lighter blues are tints — they outline, band, ghost and highlight — and never fill a button or underline a link on their own.
**The Never-Gray Rule.** Every ink, rule, scrim and shadow is mixed from the navy. A neutral gray (`#888`, `#ccc`, `gray-500`) has no place on the sheet.
**The Word-With-Colour Rule.** Pass, fail and warn always travel with text or an icon — a pill's label, a check mark, a 9 px marker beside a heading. Colour alone never states a measurement's status.

## Typography

**Display Font:** Barlow Semi Condensed (with Arial Narrow, Helvetica Neue, Arial, sans-serif) — weights 600 and 700, self-hosted through `@fontsource`, latin subset.
**Body Font:** IBM Plex Sans (with system-ui, -apple-system, Segoe UI, Roboto, sans-serif) — 400, 500, 600.
**Label/Mono Font:** IBM Plex Mono (with ui-monospace, SFMono-Regular, Menlo, Consolas, monospace) — 400, 500, always `font-variant-numeric: tabular-nums`.

**Character:** A condensed, tracked heading face doing the title block's work over a plain, even body face; the mono is not a code affectation but the column of measured values on a drawing. Headings are bold and quiet (letter-spacing 0.005em, `text-wrap: balance`), never large: the biggest type on any screen is the 36.5 px hero line.

### Hierarchy
- **Display** (700, 36.5px, 1.1): the home hero line only ("Photograph what broke. Print what fits."); 31 px under 936 px.
- **Headline** (700, 28.5px, 1.15): the base `h1`; the session top bar sets it at 23.5 px (21 px on phones) with ellipsis; the brand name is 23.5 px uppercase at 0.04em (19.5 px in the top bar).
- **Title** (700, 22px / 18px, 1.15): `h2` and `h3` in running content; guide-step and empty-state titles use the 600 weight at 18 px; the settings modal head is 600 at 21 px.
- **Body** (400, 17px, 1.5): the base size everywhere. Tables and timeline cards run 16 px; `.small`, hints and captions 12 / 14.5 px; the hero explanation is 18 px on Ink 2 at a 72ch maximum measure.
- **Label — title block** (700, 15.5px, 0.08em, uppercase, Ink 2): panel and pane heads, section titles, customizer group titles, popover titles — the label that names a block of the sheet.
- **Label — column** (600, 14.5px, 0.06em, uppercase, Ink 3): table heads and timeline card heads; `.label` and `dt` labels use the same size at 0.08em / 0.04em. Field labels are 15.5 px, 600, 0.04em and *not* uppercase.
- **Button** (600, 17px, 0.02em, line-height 1): the whole `.btn` family in Barlow, mixed case; 15.5 px small, 14.5 px extra-small, 18 px large. Tabs and segmented switches are the exception that goes uppercase (15.5 px, 0.03–0.04em).
- **Mono** (400, 15.5px, tabular): measured and target values, parameter names, chips, key-value readouts and export lists; 15 px in summary lines and check ids; 14.5 px in the viewer HUD, dim labels, tool calls and the health line; 13 px in tab counts and slider range labels.

### Named Rules
**The Title-Block Rule.** A block of the sheet is named in tracked condensed capitals (15.5 px, 700, 0.08em) on a 1 px rule — never in sentence-case bold, never larger than 15.5 px.
**The Measured-Value Rule.** Any number that was measured, computed or targeted is set in IBM Plex Mono with tabular figures, right-aligned in tables, with its unit or target beside it (`→ 43.2`). Prose numbers stay in the body face.

## Layout

The sheet is the page: the body carries the blueprint grid (31 px minor, 155 px major, offset −1 px) as `background-image`, and every pane sits on it as a white rectangle with a 1 px rule. Panels never repaint the grid inside themselves.

**Home** is a centred column (max-width 1560 px; padding 36 px 26 px 73 px, or 18 / 12 / 52 px under 1274 px) under a sticky 68 px header: the hero, the four-station dimension line (a 4-column grid, gap 18 px, hidden under 936 px), then a 7fr / 5fr grid (gap 26 px) holding the New-part panel and the Your-parts panel; one column with a 18 px gap under 1274 px.

**Session workspace** is a full-height grid (`100vh`, padding 13 px, gap 13 px): a 65 px top bar across the top row, then guide 455 px · centre `minmax(0, 1fr)` · engineer's tabs 468 px — on a window too narrow for that, the side panes start at a quarter of the width each (never under 338 / 390 px) so the 3D view keeps room. Under 1274 px it becomes one pane at a time on `100dvh` (padding and gap 8 px), switched from a three-button bar at the bottom in thumb reach (buttons min-height 52 px, the active one filled with the action blue).

**Rhythm.** Pane and panel heads are at least 49 px tall (padding 10 px 16 px) and wrap rather than scroll: a narrow pane puts its last tabs, and the 3D view its view picker, on a second row; pane bodies pad 16 px; tables cell-pad 8 px 10 px and flush to the pane edge with −16 px margins; stacks step by 13 px, rows by 10 px, fields by 5 px; buttons pad 8 px 14 px at a 39 px minimum height. Toasts stack from the bottom-right corner at 21 px; popovers open 8 px below their anchor at 416 px wide; the modal opens 8vh from the top at `min(728px, 100%)`.

**Breakpoints.** 1274 px (workspace collapses, home goes single-column, the top bar and centre head wrap) and 936 px (header compacts, brand tag and path hide, icon buttons drop their text, hero drops to 31 px). `@media (hover: none)` keeps the per-row delete button visible where there is no hover.

## Elevation & Depth

Depth is tonal first: the canvas (Sheet Paper) under white panels, an inset second neutral (Sheet 2) for read-only and disabled blocks, and Overlay for anything that floats; in dark mode the same ladder climbs from #05142E through #0A1D3F and #0F2549 to #14305A. Edges are drawn, not cast — 1 px Rule outside, 1 px Rule 2 inside. Panels and panes carry a rest shadow so faint (6 % / 4 % navy) that they read flat; the lifted shadow is reserved for overlays.

### Shadow Vocabulary
- **Rest** (`box-shadow: 0 1px 3px rgba(5,20,46,.06), 0 3px 8px rgba(5,20,46,.04)`): panels, panes, the top bar and the mobile pane switch. Dark: `0 1px 3px rgba(0,0,0,.35), 0 3px 10px rgba(0,0,0,.25)`.
- **Pop** (`box-shadow: 0 13px 36px rgba(5,20,46,.18), 0 3px 8px rgba(5,20,46,.08)`): toasts, popovers and the settings modal, which also enter with a 160–180 ms fade-and-rise. Dark: `0 16px 42px rgba(0,0,0,.5), 0 3px 8px rgba(0,0,0,.3)`.
- **Focus halo** (`box-shadow: 0 0 0 4px rgba(21,93,211,.22)` with the border turned to the action blue): buttons, inputs, the slider thumb and the switch on `:focus-visible`; tabs and segments take the same halo inset at 3 px; everything else gets the global 3 px solid outline offset 3 px.
- **Current-step ring** (`box-shadow: 0 0 0 3px #E2ECFC` on a blue border): the guide's current step and a focused number box.
- **Scrim** (`rgba(5,20,46,.5)` with `backdrop-filter: blur(3px)`): behind the modal.

### Named Rules
**The Overlay-Only Lift Rule.** Only what floats above the sheet (toast, popover, modal) casts a visible shadow. A panel, card or table row gets a rule and, at most, the rest shadow — never the pop shadow, never a hover lift.

## Shapes

Crisp and measured. Three radii do all the work: 4 px (`--radius-sm`) for inline code, chips, thumbnails, count badges and focus-ring corners; 5 px (`--radius`) for buttons, inputs, panels, panes, cards, banners, toasts and the brand mark; 8 px (`--radius-lg`) for popovers and the modal. Fully round forms are reserved for status and controls: 999 px pills for status labels and stage chips, 50 % circles for step numbers, status dots (6–10 px), the slider thumb (21 px) and the switch knob (18 px).

Borders are always 1 px: Rule on outer edges, Rule 2 on inner dividers, dashed Rule for "put something here" (the file drop, empty states, the advanced-settings block) and for a guide step's body divider. Tone borders are the status colour mixed 35–60 % into transparent. The drafting motifs are drawn from the same vocabulary: the home path is a 1 px Dimension Blue rule with 1 × 14 px ticks; the slider is a 3 px track under a 10 px tolerance bracket (1 px Dimension Blue outline, top corners 3 px, dashed when the measurement is an estimate) with 2 × 21 px marks; dimension lines in the 3D view carry extension lines and ticks like a drawing. The select's arrow is two 5 px gradient triangles; no icon font, no glyphs.

## Components

Crisp and measured: small radii, 1 px rules, a full state vocabulary (hover, active, focus-visible, disabled, invalid), and one 24-unit stroke icon family sized 11–18 px inside controls and 30–47 px in empty states.

### Buttons
- **Shape:** gently squared (5 px), 39 px minimum height, padding 8 px 14 px, Barlow 600 17 px at 0.02em, icon gap 8 px; `-sm` 34 px / 16 px, `-xs` 29 px / 14 px, `-lg` 18 px with 12 px 21 px padding, `-block` full width.
- **Primary:** Action Blue fill and border with white text; hover and active go to the pressed blue (#124FB4). One per view — "Analyze photos", "Create session", "Run designer".
- **Secondary (default `.btn`):** white with a 1 px Rule border and Ink text; hover turns the border Dimension Blue and the fill soft blue; active mixes soft blue with Tolerance Tint 70 / 30.
- **Ghost:** transparent, Ink 2 text; hover fills soft blue and turns the text Action Blue. `.active` on any button is the same soft-blue fill with blue text and no border (the viewer's DIMS / GHOST / OBJECT toggles).
- **Danger / quiet danger:** Fail text (or Ink 3 until hovered) with a fail-soft fill on hover; the row delete button appears only on hover or focus-within.
- **Choice:** a left-aligned, wrapping Plex Sans 500 variant for answering a question; hover outlines in Action Blue.
- **Focus:** no outline; the 4 px focus halo plus a blue border. **Disabled:** 45 % opacity, `not-allowed`.
- Transitions: background, border, colour and shadow at 150 ms on the house curve.

### Inputs / Fields
- **Style:** white, 1 px Rule, 5 px radius, padding 8 px 10 px, 17 px body face; hover border Dimension Blue; placeholders in Ink 3 at full opacity; the select draws its own 5 px arrow and pads 31 px on the right.
- **Focus:** border Action Blue plus the 4 px halo.
- **Error / Disabled:** `aria-invalid` turns the border Fail; disabled sits on Sheet 2 at 55 % opacity.
- **Fields:** a 5 px stack of label (Barlow 600 16 px 0.04em, Ink 2), control, and hint (14 px, Ink 3). Checkboxes and native ranges take the action blue through `accent-color`.
- **Measured inputs:** `.input-num` is Plex Mono, right-aligned, 109 px wide (74–120 px in rows); the customizer's number box is a 34 px bar of `− [ 43.2 ] + mm` with 26 px steppers and a mono unit, ringed in soft blue on focus-within and bordered Fail when out of range.

### Pills, Chips and Markers
- **Pills:** 999 px, 14 px Plex Sans 500, padding 4 px 9 px, 1 px border; neutral on Sheet 2 with a Rule border, or pass / fail / warn / blue on their soft fills with a 35 % tone border. A running state adds a 8 px pulsing dot (1.2 s).
- **Chips** (check ids, filters): 4 px radius, Plex Mono 14 px, white with a Rule border; pass / fail tones; `.active` is a 3 px Action Blue outline.
- **Status markers:** a 9 px dot before a card or request head, coloured by `--tone`; stage and step numbers are 16–29 px circles that go pass-soft when done and Action Blue when current.

### Tabs / Navigation
- **Tabs:** Barlow 600 16 px uppercase at 0.03em in Ink 3, padding 0 9 px, a 3 px transparent bottom border; hover Ink; active Action Blue text and underline; a Plex Mono 13 px count badge on Rule 2 that turns soft blue when active; focus is the inset halo.
- **Stage bar:** 999 px chips with a numbered 21 px circle, joined by 8 px Rule ticks, scroll-snapping under a right-edge fade; done steps get pass-soft numbers, the current step a blue border, soft-blue fill and a blue number.
- **Segmented control / mode switch:** a single 1 px Rule frame, 5 px radius, transparent buttons divided by Rule 2; the active segment is soft blue with Action Blue text (uppercase Barlow in the mode and pane switches, Plex Sans in the customizer).
- **Header / top bar:** a 68 px sticky white header with a bottom Rule on the home page; in a session a 65 px ruled, rest-shadowed top bar carrying brand, title, mono iteration counter, status and actions, wrapping under 1274 px.

### Cards / Containers
- **Panels and panes:** white, 1 px Rule, 5 px radius, rest shadow; a 49 px head with the title-block label and a Rule 2 bottom border; 16 px body; an optional ruled foot.
- **Timeline cards:** 5 px radius on Rule 2 (assistant cards on Rule), padding 10 px 13 px, 16 px text, a column-label head with a mono timestamp; questions tint soft blue with a 45 % blue border, narration pass-soft, errors fail-soft; tool calls and system lines are borderless mono with a hairline on either side.
- **Inset blocks:** summary lines, derived values, guide cards, banners and status lines sit on Sheet Paper with a Rule 2 border; tone banners take the soft fill and a 45–60 % tone border.
- **Empty states:** dashed Rule, Sheet 2, centred, 36 px 21 px padding, a Dimension Blue 30–47 px icon and a 18 px Barlow title.

### Overlays
- **Toasts:** a bottom-right stack on the Overlay surface with a Rule border, pop shadow, a tone dot before the text and a 180 ms rise-in.
- **Popovers:** 416 px, 8 px radius, pop shadow, 160 ms rise-in, a title-block label head.
- **Modal:** `min(728px, 100%)` on Overlay with a 8 px radius over the navy scrim; a ruled head with a 21 px Barlow title.

### Drafting Slider (signature)
A parameter is a dimension, so its control is drawn like one: a 3 px Rule track with a 55 % Action Blue fill to the value; above it a 10 px tolerance bracket in Tolerance Tint outlined in Dimension Blue (solid for a confirmed measurement, dashed for an estimate, 45 % fill for a spec range); 2 × 21 px marks in pass / warn / blue / neutral for measured and verified values; a 21 px white thumb with a 3 px Action Blue ring that scales 1.15× on hover or drag and shows the value in a navy bubble while dragging; mono range labels at the ends. Keyboard: arrows step, Shift ×10, Page ×10, Home / End. A binding line under it says where the number came from, with a tone dot and a bold source.

### Dimension Line (signature)
The home page's "how it works" is one 1 px Dimension Blue rule with 1 × 14 px ticks at each station and the end, four numbered stations in mono blue beneath it — the brand motif in place of a card grid. The 3D view repeats it in space: overall X / Y / Z dimensions as Action Blue line segments with extension lines and ticks, labelled in 14 px mono chips (blue text on an 82 % viewer-bed tint with a 35 % blue border) that settle in with a 280 ms rise — the one authored motion in the product.

### Hover Cards (in place of tooltips)
The interface does not use `title=` tooltips: a control says what it does in its label, and a disabled control says why in a small dim line beside it. When a compact element stands for more than it can show — an iteration chip, a preset, a binding line, a photo's grade, a tool call — a **hover card** carries the detail: a Sheet surface with a 1 px Rule, the pop shadow, 16 px body text, 7 × 12 px padding, above the element by default (`.below` / `.right` variants), shown after 150 ms on hover or keyboard focus (`.hover-anchor:focus-within`), never on touch devices. `role="tooltip"` and `aria-describedby` link it to its anchor.

### Hover Linking (dimension focus)
Every row that stands for a spec dimension — a check, a guide "confirm the fit" row, a bound customizer slider, a capture-request chip — announces the dimension it is about while the pointer is on it (`hover.ts`, one window event). Rows for the same dimension elsewhere light up (`.is-hovered`: soft-blue fill, a 3 px Action Blue inset bar on tables), and the 3D view draws the **section plane** the check was measured on: a translucent Action Blue plane through the part at that axis and offset, with a solid Action Blue chip naming the dimension and its plane (`neck_ring.inner_diameter · z = 3.0 mm`).

### Resizable Panes
On desktop the guide and details columns have drag handles on their inner edges: the 13 px gutter is the grab area, a 3 px Action Blue line appears on hover, focus and drag, and a small 18 × 44 px pill button on the line folds the pane away (a 29 px strip with the pane's name written vertically brings it back). Drag past the minimum folds it too; double-click resets; the handle is a `role="separator"` that arrows resize (Shift × 4), Home / End limit, Enter folds. Widths persist per browser. Phones never see the handles.

### The Mark
A ring — the part — cracked on a diagonal and mended with a gold seam (#F2C14E, the one colour outside the palette, used nowhere else in the interface except the tint of the real object ghosted in the 3D view). It sits on a 6 px-radius Action Blue square in both themes (`--brand-square`, `--brand-ring`, `--brand-seam`); the icon build with heavier strokes is used at 31 px and below. The kit — SVG sources, PNGs, favicon and app icons, the social image, fonts and `kintsugi-brand.css` — is `docs/brand/`, generated by `scripts/brand_assets.py`.

## Do's and Don'ts

### Do:
- **Do** keep the blueprint grid on the body only (31 px minor / 155 px major, Action Blue at 5 % / 7.5 %) and place every pane on it as a white rectangle with a 1 px Rule.
- **Do** name each block of the sheet with a title-block label — Barlow 700, 16 px, 0.08em, uppercase, Ink 2 — on a Rule 2 line.
- **Do** set every measured, computed or target value in IBM Plex Mono with tabular figures, right-aligned in tables, with its unit or `→ target` beside it.
- **Do** use #155DD3 for every action, link, active tab, caret and focus, and soft blue (#E2ECFC) for every hover and active fill; in dark mode let the action colour become #6C9EF0 with navy text.
- **Do** draw controls from the drafting vocabulary: 1 px rules, ticks, tolerance brackets, 9 px status dots, numbered circles.
- **Do** pair pass / fail / warn with a word or an icon, and keep tone borders at 35–60 % of the colour.
- **Do** use the one icon family — 24-unit `viewBox`, `currentColor` stroke, round caps, weight 2 (1.3–1.6 at 39 px and above) — at 11–18 px inside controls.
- **Do** keep the three radii (4 / 5 / 8 px), reserve 999 px for status pills and stage chips, and 50 % for dots, numbers, thumb and knob.
- **Do** self-host type (`@fontsource`, latin subsets) and honour `prefers-reduced-motion` and `prefers-color-scheme`.

### Don't:
- **Don't** introduce a neutral gray for text, rules, scrims or shadows; mix from the navy.
- **Don't** let the tints act: no #6C9EF0 or #BED4F9 button fills, links or underlines in light mode.
- **Don't** lift a panel, card or row with the pop shadow or a hover translate; only toasts, popovers and the modal cast a visible shadow.
- **Don't** mark status with a side stripe, a full-bleed colour fill or a big tinted tile; use the 9 px marker before the head and a pill.
- **Don't** arrange the sheet as hero-metric cards or a dashboard of KPIs; density comes from ruled tables and rows.
- **Don't** use glyph icons, icon fonts, emoji or a second icon set; every icon is a 24-unit stroke SVG from `icons.tsx`.
- **Don't** uppercase body copy or the `.btn` family; capitals belong to title-block labels, column labels, tabs and segmented switches.
- **Don't** load fonts, scripts or images from a CDN; the sheet must render off-grid.
- **Don't** hide meaning in a `title=` tooltip; put it in the label, in a dim line beside the control, or in a hover card.
- **Don't** recolour, rotate or straighten the mark's seam, or draw the mark without its square on a busy ground.
