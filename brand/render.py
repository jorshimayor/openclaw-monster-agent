#!/usr/bin/env python3
"""Render the brand templates.

    python brand/render.py --site yourdomain.dev

Everything that changes between assets is a placeholder, so the same surface —
ground, dot matrix, glow, traces — is identical across every format and only the
content moves. Change a colour in tokens.json and it changes once, here.

    python brand/render.py --site x.dev \\
        --thumb "Storage Packing|Costs You|3,355 Gas" --tag "EVM DEEP DIVE"
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
OUT = ROOT / "out"

MONO = "'JetBrains Mono','SF Mono',Menlo,Consolas,monospace"
SANS = "Inter,-apple-system,'Segoe UI',system-ui,sans-serif"

# Width of one character at font-size 1 in the heavy sans. SVG cannot measure
# text, so a title that is too long for its box silently runs off the canvas —
# this is what the type sizes are fitted against. Deliberately a little wide.
CHAR_W = 0.56


def fit_size(lines: list[str], width: int, largest: int, smallest: int) -> int:
    """The largest size at which the longest line still fits inside `width`."""
    plain = [re.sub(r"&\w+;", "x", line) for line in lines]
    longest = max((len(line) for line in plain), default=0) or 1
    return max(smallest, min(largest, int(width / (longest * CHAR_W))))


def esc(text: str) -> str:
    """SVG text is XML — an ampersand in a title is a parse error, not a glyph."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def surface(w: int, h: int) -> str:
    raw = (TEMPLATES / "_surface.svg").read_text()
    raw = re.sub(r"^<!--.*?-->\s*", "", raw, flags=re.S)
    return raw.replace("{{W}}", str(w)).replace("{{H}}", str(h))


def render(name: str, size: tuple[int, int], values: dict) -> Path:
    svg = (TEMPLATES / f"{name}.svg").read_text()
    svg = svg.replace("{{SURFACE}}", surface(*size))
    filled = {"MONO": MONO, "SANS": SANS, **values}
    for key, value in filled.items():
        svg = svg.replace(f"{{{{{key}}}}}", str(value))

    missing = set(re.findall(r"\{\{(\w+)\}\}", svg))
    if missing:
        raise SystemExit(f"{name}: unfilled placeholders {sorted(missing)}")

    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.svg"
    path.write_text(svg)
    return path


def split_lines(text: str, count: int) -> list[str]:
    """"A|B|C" or a sentence chopped into `count` roughly equal lines."""
    if "|" in text:
        parts = [p.strip() for p in text.split("|")]
    else:
        words = text.split()
        per = max(1, -(-len(words) // count))
        parts = [" ".join(words[i:i + per]) for i in range(0, len(words), per)]
    return [esc(p) for p in (parts + [""] * count)[:count]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="your primary URL, no scheme")
    ap.add_argument("--secondary", default="jorshimayor.hashnode.dev")
    ap.add_argument("--keys", default="Blockchain_Dev|Security_Researcher|Technical_Writer")
    ap.add_argument("--thumb", default="Storage Packing|Costs You|3,355 Gas")
    ap.add_argument("--tag", default="EVM DEEP DIVE")
    ap.add_argument("--thumb-sub", default="measured, not asserted")
    ap.add_argument("--article", default="How Does a Hypervisor|Allocate Resources?|")
    ap.add_argument("--kicker", default="GIVE ME CLARITY")
    ap.add_argument("--readtime", default="12 min read")
    ap.add_argument("--newsletter", default="the build log")
    ap.add_argument("--issue", default="ISSUE 01")
    ap.add_argument("--date", default="")
    ap.add_argument("--news-title", default="What broke when Opta|pulled out of FBref")
    ap.add_argument("--news-sub", default="and what I am building about it")
    args = ap.parse_args()

    keys = [k.strip() for k in args.keys.split("|")]
    while len(keys) < 3:
        keys.append("Technical_Writer")
    halves = [(k.split("_", 1) + [""])[:2] for k in keys]

    common = {"SITE": esc(args.site), "SECONDARY": esc(args.secondary)}
    key_vals = {
        "KEY1A": esc(halves[0][0]), "KEY1B": esc(halves[0][1]),
        "KEY2A": esc(halves[1][0]), "KEY2B": esc(halves[1][1]),
        "KEY3A": esc(halves[2][0]), "KEY3B": esc(halves[2][1]),
    }

    written = [
        render("banner-x", (1500, 500), {**common, **key_vals}),
        render("banner-linkedin", (1584, 396), {**common, **key_vals}),
    ]

    thumb = split_lines(args.thumb, 3)
    size = fit_size(thumb, 1140, largest=82, smallest=52)
    written.append(render("thumbnail", (1280, 720), {
        **common, "TAG": esc(args.tag), "TAGW": max(160, len(args.tag) * 13 + 48),
        "TITLESIZE": size, "Y1": 290, "Y2": 290 + size + 10, "Y3": 290 + (size + 10) * 2,
        "LINE1": thumb[0], "LINE2": thumb[1], "LINE3": thumb[2],
        "SUBTITLE": esc(args.thumb_sub),
    }))

    article = split_lines(args.article, 3)
    size = fit_size(article, 1024, largest=74, smallest=46)
    written.append(render("article-header", (1200, 630), {
        **common, "KICKER": esc(args.kicker), "TITLESIZE": size,
        "LINE1": article[0], "LINE2": article[1], "LINE3": article[2],
        "Y2": 288 + size + 16, "Y3": 288 + (size + 16) * 2,
        "READTIME": esc(args.readtime),
    }))

    news = split_lines(args.news_title, 2)
    size = fit_size(news, 1056, largest=54, smallest=36)
    from datetime import date
    written.append(render("newsletter", (1200, 400), {
        **common, "NEWSLETTER": esc(args.newsletter), "ISSUE": esc(args.issue),
        "DATE": esc(args.date or date.today().strftime("%d %b %Y").upper()),
        "TITLESIZE": size, "Y2": 214 + size + 10,
        "LINE1": news[0], "LINE2": news[1], "SUBTITLE": esc(args.news_sub),
    }))

    for p in written:
        print(f"  {p.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
