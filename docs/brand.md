# Brand

Derived from the two profile banners, not invented alongside them. The colours,
the dot grid, the circuit traces and the `({ Key_Name: true })` motif were
already there; what follows is those decisions written down so they can be
repeated without redrawing anything by hand.

## The idea

A profile expressed as code that evaluates to `true`. The claims are structured
data, not adjectives — the design makes the same argument the writing standard
does, which is that a statement should be checkable. Everything else (grid,
traces, glow) is the surface those claims sit on and should never compete
with them.

This is why there is no tagline anywhere in the asset set. A tagline would be
the one unfalsifiable thing on the canvas.

## The mark

`brand/logo-mark.svg`, `brand/logo-lockup.svg`, `brand/favicon.svg`.

Braces around a node: the object from the banner, collapsed to a glyph. Drawn
as stroked paths, never as text, so it renders identically without JetBrains
Mono installed.

- Minimum size for the mark is 24px. Below that, use `favicon.svg`, which drops
  the node's ring and thickens the strokes — the detailed version turns to mud
  at 16px.
- The lockup is the mark plus `jorshimayor` plus the three-word rule. Never
  re-typeset it; if the words change, change the file.
- Clear space on all sides is the width of one brace stem. There is no approved
  version on a light ground — the ink background is doing structural work, not
  decorating.

## Colour

Roles, not a palette. `brand/tokens.json` is the source; `brand/tokens.css`
is the same values as custom properties for the frontend.

| Role | Token | Use |
| --- | --- | --- |
| Ground | `ink-900` → `ink-600` | canvas, top to bottom |
| Lift | `depth-900/700/500` | the glow in the lower third, nothing else |
| Primary | `accent-500` `#3D5AFE` | the node, one accent bar, one rule per asset |
| Key second half | `accent-400` | the half of the key after the underscore |
| Highlight | `peri-400/300` | the last line of a title, kickers |
| Text | `paper-100/200` | key names, titles |
| Receding | `muted-500/400` | `true`, the colon, subtitles, read time |
| Structure | `line-soft/strong` | traces, dashed frames |
| Grid | `grid-dot` | the dot matrix, and never above 0.05 alpha |

One accent per canvas. If a second thing is `accent-500`, one of them is wrong.

## Type

Mono for scaffolding — `const profile = () =>`, URLs, dates, read time, tags.
Sans, weight 700, for anything that is a claim. The distinction is functional:
mono is the machinery, sans is the content.

Tracking is `0.18em` on labels, `-0.01em` on headings. Titles are never set
below 46px on a 1200px canvas or 52px on a thumbnail — below that the asset
stops working at feed size, which is the only size that matters.

## Canvases

| Asset | Size | File |
| --- | --- | --- |
| X header | 1500×500 | `brand/out/banner-x.svg` |
| LinkedIn header | 1584×396 | `brand/out/banner-linkedin.svg` |
| YouTube thumbnail | 1280×720 | `brand/out/thumbnail.svg` |
| Article header / OG | 1200×630 | `brand/out/article-header.svg` |
| Newsletter header | 1200×400 | `brand/out/newsletter.svg` |

Two crops constrain the layouts and are easy to forget:

- **X overlays the avatar on the bottom-left corner.** Nothing below `y=340`
  sits left of `x=440`.
- **A thumbnail is judged at 320×180.** Three words a line, three lines, one
  number. The contact sheet renders it at both sizes for this reason.

## Regenerating

```bash
python3 brand/render.py --site jorshimayor.dev && python3 brand/preview.py
```

`render.py` fills the templates in `brand/templates/`; `preview.py` builds
`brand/out/_preview.html`, a contact sheet to eyeball before publishing.

Per-asset content is passed in, so a thumbnail is a command rather than a file
to edit:

```bash
python3 brand/render.py --site jorshimayor.dev \
  --tag "SOLANA SECURITY" \
  --thumb "Reentrancy in Practice|Not the Textbook Version|17 Contracts Audited"
```

Two things in the renderer are worth knowing before changing it:

- **`render()` raises on an unfilled placeholder.** A template that quietly
  shipped `{{LINE3}}` as literal text was the failure worth preventing.
- **`fit_size()` shrinks a title until it fits.** SVG cannot measure text, so
  an over-long title does not wrap — it runs off the canvas silently. The
  character width it uses (`CHAR_W = 0.56`) is an estimate, deliberately on the
  wide side. Widen it further before trusting it with a new typeface.

## What this does not cover

- **Motion.** No animation, transition or video-intro spec exists.
- **The website itself.** `tokens.css` is importable, but the frontend has not
  been migrated onto these variables.
- **Light mode.** There isn't one, by choice.
- **Print.** Everything here is RGB on a dark ground and will not survive CMYK.
- **Photography or illustration style.** The illustration guidance in
  [`writing-standard.md`](writing-standard.md) covers diagrams in articles,
  which is a separate problem from brand imagery.
