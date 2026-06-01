# Design

Visual system for the TalkToBook landing + converter. Calm, editorial, exact —
the interface is itself a sample of the books the engine makes.

## Theme

Light, warm-paper reading surface with a dark-ink hero and footer bookending it.
Daylight, not dark mode: a creator reviewing their work at a desk. The page
should feel like the inside of a well-set book.

## Color (brand-committed, do not drift)

| Token | Hex | Role |
|---|---|---|
| `--ink` | `#0C1211` | Dark panels (hero/footer), headings, primary buttons |
| `--ink-soft` | `#16201E` | Raised ink surfaces (book cover, cards on ink) |
| `--lime` | `#B7FF6E` | The one accent: rules, keylines, one emphasized word. ≤10% of pixels |
| `--lime-deep` | `#004700` | Lime's readable form on paper (tags, checkmarks, small text) |
| `--paper` | `#FAF8F3` | Body background, reading surface |
| `--paper-2` | `#F1EEE5` | Muted section bands, insets |
| `--text` | `#1A1A1A` | Body text on paper (≈13:1) |
| `--muted` | `#5B615E` | Secondary text on paper (≥5:1 — darker than the AI-default gray) |
| `--line` | `#E1DDD2` | Hairlines, borders |

Strategy: **Restrained** — tinted neutrals + a single accent under 10%. The lime
is never a fill behind text; on paper it appears only as a thin rule or in its
deep form.

## Typography

Two families on a contrast axis (contemporary grotesque vs. literary serif),
both chosen against the reflex-reject defaults.

- **Display + UI — Bricolage Grotesque** (variable, opsz). Headings, nav,
  buttons, labels, form UI. Letter-spacing -0.02 to -0.03em on large sizes;
  `text-wrap: balance` on h1–h3.
- **Reading — Literata** (variable). The book mockup, before/after "after"
  page, and any in-product reading sample. A face literally designed for ebook
  reading — the product's voice made visible.
- **Mono — system** (`ui-monospace`). Only for raw-transcript "before" samples.

Fluid modular scale via `clamp()`, ≥1.25 between steps. Hero display max ~5rem.

## Components

- **Buttons.** `.btn` with `-primary` (ink, or lime-on-ink in the hero),
  `-ghost` (outline). Ease-out-expo lift on hover, visible focus ring.
- **Book mockup.** CSS-built cover + open page, overlapping with slight depth.
  Mirrors the real generated output (dark cover, lime rule, serif reading page
  with a lime-keylined interviewer quote). Decorative → `aria-hidden`.
- **Converter card.** Single white panel: title + source inputs, paste/upload
  tabs, ownership checkbox, primary action; result + upsell render inline.
- **Steps / pricing / FAQ.** Restrained panels, hairline separators, no
  repeated uppercase eyebrows, no side-stripe accent borders.

## Motion

Quiet and intentional. Ease-out-expo (`cubic-bezier(.16,1,.3,1)`). On-load:
staggered hero reveal of the book mockup. On-scroll: subtle rise+fade that
**enhances an already-visible default** (content is visible without JS).
Optional pointer-tilt on the book. Every effect has a
`prefers-reduced-motion: reduce` path (instant/crossfade).

## Layout

Reading-width content (≈1080px max, 65–75ch prose), fluid `clamp()` spacing that
breathes on large viewports with varied rhythm. Hero is two columns on desktop
(copy + book), single column stacked on mobile.
