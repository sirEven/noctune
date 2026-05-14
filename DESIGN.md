---
version: alpha
name: Noctune
description: A midnight music library manager — calm, precise, and deeply dark.
colors:
  surface: "#0C0C14"
  surface-raised: "#14141E"
  surface-overlay: "#1C1C28"
  primary: "#6C5CE7"
  accent: "#6C5CE7"
  accent-hover: "#8B7CF7"
  accent-muted: "#6C5CE7"
  success: "#34D399"
  warning: "#F59E0B"
  error: "#F87171"
  text-primary: "#E8E6F0"
  text-secondary: "#8B88A0"
  text-muted: "#55536B"
  border: "#2A2840"
  border-active: "#3D3A5C"
typography:
  h1:
    fontFamily: Inter
    fontSize: 2rem
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  h2:
    fontFamily: Inter
    fontSize: 1.5rem
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  h3:
    fontFamily: Inter
    fontSize: 1.125rem
    fontWeight: 600
    lineHeight: 1.4
  body-md:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.5
  label-caps:
    fontFamily: Inter
    fontSize: 0.6875rem
    fontWeight: 600
    letterSpacing: "0.08em"
  mono:
    fontFamily: JetBrains Mono
    fontSize: 0.8125rem
    fontWeight: 400
    lineHeight: 1.6
rounded:
  sm: 4px
  md: 8px
  lg: 12px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#FFFFFF"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface-overlay}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
  button-secondary-hover:
    backgroundColor: "{colors.border-active}"
    textColor: "{colors.text-primary}"
  card:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  card-border:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
  badge-confidence:
    backgroundColor: "{colors.accent-muted}"
    textColor: "#FFFFFF"
    rounded: "{rounded.full}"
    padding: "{spacing.xs} {spacing.sm}"
  badge-success:
    backgroundColor: "#065F46"
    textColor: "#34D399"
    rounded: "{rounded.full}"
    padding: "{spacing.xs} {spacing.sm}"
  badge-warning:
    backgroundColor: "#78350F"
    textColor: "#FCD34D"
    rounded: "{rounded.full}"
    padding: "{spacing.xs} {spacing.sm}"
  badge-error:
    backgroundColor: "#7F1D1D"
    textColor: "#FCA5A5"
    rounded: "{rounded.full}"
    padding: "{spacing.xs} {spacing.sm}"
  divider:
    backgroundColor: "{colors.border}"
    height: 1px
  input-border:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
  metadata-label:
    textColor: "{colors.text-secondary}"
    typography: "{typography.label-caps}"
  placeholder-text:
    textColor: "{colors.text-muted}"
    typography: "{typography.body-sm}"
---

## Overview

Noctune runs at night. The UI should feel like a dim studio — dark surfaces,
violet accents pulling focus to what matters, and enough contrast that you never
squint. No visual noise. Information is dense but breathable. Every element earns
its place.

The accent color (amethyst violet) belongs to user actions and agent activity.
It is not decorative. It signals: "this is where you act" or "this is what the
system processed." Everything else is surfaces and text.

## Colors

- **Surface (#0C0C14):** The void. Deepest background — the page itself.
- **Surface Raised (#14141E):** Cards, panels, any elevated container. One step
  up from the void.
- **Surface Overlay (#1C1C28):** Hover states, active rows, dropdowns. Two
  steps up.
- **Accent (#6C5CE7):** Amethyst. The only color that acts. Buttons, active
  states, processed indicators, selection highlights.
- **Accent Hover (#7C6CF7):** Lighter amethyst for hover feedback.
- **Accent Muted (#6C5CE7):** Same hue at low opacity for subtle tints —
  progress bars, pill badges, active toggles. Applied as rgba(108, 92, 231, 0.12)
  in CSS, stored as the base hex here.
- **Success (#10B981):** Confident transfers, completed scans, "all good."
- **Warning (#F59E0B):** Review queue, low confidence, needs attention.
- **Error (#EF4444):** Failed transfers, conflicts, problems.
- **Text Primary (#E8E6F0):** Headlines, body copy. Warm white, not cold.
- **Text Secondary (#8B88A0):** Metadata, descriptions, secondary labels.
- **Text Muted (#55536B):** Disabled states, timestamps, placeholders.
- **Border (#2A2840):** Default borders. Subtle but present.
- **Border Active (#3D3A5C):** Focused borders, active card outlines.

## Typography

Inter for everything. Weight and size carry all hierarchy — no font family
switching. Tight letter-spacing on headlines (-0.02em), default tracking on
body. JetBrains Mono for file paths, technical data, and the review queue's
diff view.

Body size is 0.875rem (14px). This is a data-dense tool — smaller type fits
more on screen without feeling cramped because the line height is generous
(1.5) and spacing is deliberate.

## Layout

Sidebar (fixed, 260px) with pipeline stages on the left. Main content area fills
the rest. No hamburger menus, no collapsible sections — the sidebar is always
visible on desktop.

Spacing is a 4px baseline. `md` (16px) for intra-component gaps, `lg` (24px)
for inter-component gaps, `xl` (32px) for section breaks.

## Elevation & Depth

No drop shadows. Elevation is expressed through background color alone:
surface → surface-raised → surface-overlay. Three tiers. A card sits on
surface-raised, its hover state is surface-overlay. Flat and honest.

## Shapes

Rounded corners are understated. `sm` (4px) on inputs and small elements, `md`
(8px) on buttons, `lg` (12px) on cards. `full` is reserved for pill badges
(confidence scores, status indicators) and album art thumbnails.

## Components

- **button-primary** is amethyst on white text. One per view. The main action:
  "Start Scan," "Confirm & Transfer," "Apply Tags."
- **button-secondary** is a surface with text. Cancel, skip, secondary actions.
- **card** is the default surface for grouped content — album groups in the
  review queue, batch progress blocks, tag editor sections. Left border accent
  (2px amethyst) on the active/selected card.
- **input-border** is the focused variant of input — border color shifts to
  border-active.
- **divider** is a 1px border line for separating sections within cards.
- **metadata-label** is label-caps in text-secondary — for field labels above
  tag values. Quiet but readable.
- **placeholder-text** is text-muted at body-sm size — for empty states and
  placeholder content.
- **badge-confidence** uses accent-muted as a pill. Shows "87%" or "High" —
  immediate signal without shouting.
- **badge-success**, **badge-warning**, **badge-error** are status pills
  with tinted dark backgrounds and bright foreground text. Used in the pipeline
  progress view and per-file status. Dark bg + light text = WCAG-safe on dark
  themes.

## Do's and Don'ts

- **Do** use the accent color only for actions and active states. It loses power
  if it's everywhere.
- **Do** use monospace for file paths, technical data, and diffs.
- **Do** use left-border cards (2px accent) to mark the active/selected item.
- **Don't** use drop shadows. Color elevation only.
- **Don't** introduce colors outside the palette. Extend it first.
- **Don't** center-align body text. Left-aligned, always.
- **Don't** use rounded-full for anything that isn't a badge or avatar.
- **Don't** nest card backgrounds (surface-raised inside surface-raised).
  Go surface → surface-raised, never surface-raised → surface-raised.