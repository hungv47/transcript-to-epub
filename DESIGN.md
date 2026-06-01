# TalkToBook Design System

Visual system for TalkToBook’s landing page and converter. The product turns spoken creator content into reading assets, so the interface should feel like a quiet publishing desk rather than a generic SaaS page.

## Hallmark Direction

- **Genre:** editorial
- **Macrostructure:** Workbench
- **Nav:** N9 Edge-aligned minimal
- **Footer:** Ft6 Letter close
- **Tone:** editorial, premium, clean
- **Enrichment:** product proof only — converter panel plus book/page preview

## Palette

All implementation colors should be declared as CSS custom properties and referenced by token.

| Token | Value | Role |
|---|---:|---|
| `--color-paper` | `#F7F0E5` | Main page surface |
| `--color-paper-2` | `#EFE5D8` | Muted section surface |
| `--color-panel` | `#FFFAF2` | Form and result panels |
| `--color-ink` | `#1E1A17` | Primary text and buttons |
| `--color-ink-2` | `#514842` | Secondary copy |
| `--color-muted` | `#6F655E` | Supporting copy |
| `--color-rule` | `#D9CDBD` | Hairline rules and borders |
| `--color-accent` | `#7F1D1D` | Oxblood accent, links, checks |
| `--color-accent-2` | `#4B1515` | Strong accent hover/state |
| `--color-accent-soft` | `#EAD7CF` | Subtle accent wash |
| `--color-error` | `#9B1C1C` | Form errors |

Accent discipline: oxblood is a mark, rule, or text accent. Never use it as a large filled hero background.

## Typography

- **Display:** Newsreader. Headlines, proof titles, editorial use-case labels.
- **UI/body:** Instrument Sans. Forms, buttons, nav, short body copy.
- **Mono:** JetBrains Mono or system mono for raw transcript samples only.

Hero and major headings should use Newsreader with tight line-height. UI chrome should remain Instrument Sans.

## Layout

The page uses a Workbench structure:

1. Edge-aligned minimal nav.
2. Above-fold split: concise promise + working converter.
3. Use-case table/grid showing lead magnet and repurposing contexts.
4. Before/after proof.
5. Simple launch offer.
6. FAQ.
7. Letter-close footer.

Avoid a long marketing detour before the converter. The tool should be usable in the first viewport on desktop and immediately after the hero copy on mobile.

## Motion

Quiet reveal only. Transform + opacity. No bounce, glow, parallax, or decorative ambient motion. Respect `prefers-reduced-motion`.

## Component Rules

- Inputs and buttons share the same height family.
- Focus rings are visible and instant.
- Cards are shallow panels, not nested cards.
- Buttons never use gradient fills.
- Do not use neon lime, purple gradients, glassmorphism, fake browser chrome, or generic icon grids.
