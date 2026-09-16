#!/usr/bin/env python3
"""Build a contact sheet of everything in brand/out, for eyeballing.

    python brand/render.py --site yourdomain.dev && python brand/preview.py

The SVGs are inlined as data URIs rather than linked: a browser opening the file
directly will not always resolve a relative src, and a contact sheet with silent
holes in it is worse than none.
"""

from __future__ import annotations

import base64
from pathlib import Path

from motifs import MOTIFS, H, W

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"

# (file, caption, css width) — feed sizes included, because a thumbnail that
# only works at full size does not work.
SHEET = [
    ("logo-mark.svg", "logo · mark", 120),
    ("logo-lockup.svg", "logo · lockup", 380),
    ("logo-mark.svg", "mark @32", 32),
    ("favicon.svg", "favicon @32", 32),
    ("favicon.svg", "favicon @16", 16),
    ("banner-x.svg", "banner · X (1500×500)", 760),
    ("banner-linkedin.svg", "banner · LinkedIn (1584×396)", 760),
    ("thumbnail.svg", "YouTube thumbnail (1280×720)", 480),
    ("thumbnail.svg", "…at feed size (320×180)", 320),
    ("article-header.svg", "article header / OG (1200×630)", 560),
    ("newsletter.svg", "newsletter (1200×400)", 560),
]

CSS = """
body{margin:0;background:#14161c;font:11px/1.4 ui-monospace,monospace;
     color:#8a93ab;padding:16px}
h2{font-size:11px;font-weight:600;letter-spacing:1.6px;text-transform:uppercase;
   color:#5b74ff;margin:22px 0 8px}
img{display:block;border:1px solid rgba(93,120,255,.16)}
.row{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap}
"""


def uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/svg+xml;base64,{data}"


def main() -> None:
    """With no arguments, everything. With them, only assets matching one."""
    import sys
    wanted = sys.argv[1:]
    rows = [r for r in SHEET if not wanted or any(w in r[0] for w in wanted)]
    parts = [f"<!doctype html><meta charset='utf-8'><style>{CSS}</style>"]
    for name, caption, width in rows:
        path = (OUT / name).resolve()
        if not path.exists():
            raise SystemExit(f"missing {path} — run render.py first")
        parts.append(f"<h2>{caption}</h2>")
        parts.append(f"<img src='{uri(path)}' width='{width}'>")
    target = OUT / "_preview.html"
    target.write_text("\n".join(parts))
    print(f"  {target.relative_to(ROOT.parent)}")
    print(f"  {motif_sheet().relative_to(ROOT.parent)}")


def motif_sheet() -> Path:
    """Every subject illustration at full strength, for picking one."""
    cards = []
    for name in sorted(MOTIFS):
        cards.append(
            f"<figure><svg viewBox='0 0 {W} {H}' width='{W}' height='{H}'>"
            f"<rect width='{W}' height='{H}' fill='#080B18'/>{MOTIFS[name]}</svg>"
            f"<figcaption>{name}</figcaption></figure>"
        )
    target = OUT / "motif-gallery.html"
    target.write_text(
        f"<!doctype html><meta charset='utf-8'><style>{CSS}"
        "figure{margin:0}figcaption{margin-top:6px}"
        ".g{display:flex;flex-wrap:wrap;gap:14px}"
        "svg{border:1px solid rgba(93,120,255,.16)}</style>"
        f"<div class='g'>{''.join(cards)}</div>"
    )
    return target


if __name__ == "__main__":
    main()
