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

This is why nothing in the set makes a claim it cannot back. The lockup carries
`BLOCKCHAIN · SECURITY · WRITING` — three disciplines, checkable — and not a
slogan, which would be the one unfalsifiable thing on the canvas. Change it with
`--tagline` if the disciplines change; do not turn it into a promise.

## The mark

`brand/out/logo-mark.svg`, `brand/out/logo-lockup.svg`, `brand/out/favicon.svg`,
all rendered from `brand/templates/_mark.svg`.

Three claims in one glyph: the **braces** are the code, the **hexagon** is the
block, the **three linked nodes** are the model. Web3, AI and engineering in a
single shape rather than three icons taking turns.

It is one drawing at every size. Nothing is added or removed between the logo
and the 16px favicon — only the stroke weights change, and the hexagon fill
gets denser, because a 5px stroke that reads correctly at 96px greys out into a
smudge at 16px. Those two weight sets are `MARK_WEIGHTS` in `render.py`; there
is no third.

- Drawn as stroked paths, never as text, so it renders identically on a machine
  without JetBrains Mono.
- Clear space on all sides is the width of one brace stem.
- There is no approved version on a light ground — the ink background is doing
  structural work, not decorating.
- `frontend/public/favicon.svg` and `logo-mark.svg` are **written by the
  renderer**, not copied by hand. Edit the template and re-render; do not edit
  the files under `public/`.

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

## Subject illustrations

`brand/motifs.py`. Line art, one per subject the rotation actually covers, so
the artwork tracks the work instead of being chosen by mood:

`blocks` (the default, and the broadest web3 signal) · `evm` · `solana` ·
`move` · `cosmos` · `security` · `ai` · `football` · `systems` · `none`

Every motif is drawn in the same 240×160 box, so any of them drops into any
slot without re-fitting. They sit behind the content at low alpha and are never
the thing read first — **if the motif is legible before the headline is, it is
too loud.** That is the whole rule; the alphas in `motifs.py` (`LINE`, `DIM`,
`NODE`) are what enforce it, and raising them is how this gets ruined.

```bash
python3 brand/preview.py   # also writes brand/out/motif-gallery.html
```

Pick per asset:

```bash
python3 brand/render.py --site jorshimayor.is-a.dev \
  --motif blocks --article-motif security --thumb-motif evm
```

`--thumb-motif`, `--article-motif` and `--news-motif` each fall back to
`--motif`. An unknown name fails with the list rather than drawing nothing.

## Canvases

| Asset | Size | File |
| --- | --- | --- |
| X header | 1500×500 | `brand/out/banner-x.svg` |
| LinkedIn header | 1584×396 | `brand/out/banner-linkedin.svg` |
| YouTube thumbnail | 1280×720 | `brand/out/thumbnail.svg` |
| Article header / OG | 1200×630 | `brand/out/article-header.svg` |
| Newsletter header | 1200×400 | `brand/out/newsletter.svg` |

Three constraints on the layouts, all learned by rendering them:

- **X overlays the avatar on the bottom-left corner.** Nothing below `y=340`
  sits left of `x=440`.
- **A thumbnail is judged at 320×180.** Three words a line, three lines, one
  number. The contact sheet renders it at both sizes for this reason.
- **Each motif sits in the one box its canvas has free**, which is why the
  positions in `render.py` differ per asset rather than being one constant.

## Regenerating

```bash
python3 brand/render.py --site jorshimayor.is-a.dev && python3 brand/preview.py
```

`render.py` fills the templates in `brand/templates/` and also writes the
site's favicon; `preview.py` builds `brand/out/_preview.html`, a contact sheet
to eyeball before publishing, plus `motif-gallery.html`.

Per-asset content is passed in, so a thumbnail is a command rather than a file
to edit:

```bash
python3 brand/render.py --site jorshimayor.is-a.dev \
  --tag "SOLANA SECURITY" --thumb-motif security \
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
- **The website itself.** `tokens.css` is importable and the favicon is wired
  up, but the frontend has not been migrated onto these variables.
- **Light mode.** There isn't one, by choice.
- **Print.** Everything here is RGB on a dark ground and will not survive CMYK.
- **Photography.** The motifs are diagrams, not imagery.
- **Illustration inside articles.** The guidance in
  [`writing-standard.md`](writing-standard.md) covers diagrams in articles,
  which is a separate problem from brand imagery.
