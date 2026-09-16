#!/usr/bin/env python3
"""Subject illustrations for the banners and headers.

Every motif is line art drawn in the same 240x160 box, so any of them can be
dropped into any slot without re-fitting. They sit at low alpha behind the
content and are never the thing being read — if a motif is legible before the
headline is, it is too loud.

One motif per subject the rotation actually covers, so the artwork tracks the
work rather than being decoration chosen by mood.
"""

from __future__ import annotations

W, H = 240, 160

# Three weights. LINE is the structure you are meant to notice, DIM is texture,
# NODE is the one or two points that carry the accent.
LINE = "rgba(139,155,255,0.30)"
DIM = "rgba(139,155,255,0.14)"
NODE = "rgba(91,116,255,0.55)"

MOTIFS: dict[str, str] = {}


def _m(name: str, body: str) -> None:
    MOTIFS[name] = body.strip()


# A chain of blocks, each linked to the last. The broadest web3 signal, and the
# default when a banner is not about one chain in particular.
_m("blocks", f"""
<g fill="none" stroke="{LINE}" stroke-width="2">
  <rect x="6" y="50" width="62" height="60" rx="7"/>
  <rect x="89" y="50" width="62" height="60" rx="7"/>
  <rect x="172" y="50" width="62" height="60" rx="7"/>
</g>
<g fill="none" stroke="{DIM}" stroke-width="2" stroke-linecap="round">
  <path d="M18 66 H48 M18 78 H56 M18 90 H38"/>
  <path d="M101 66 H131 M101 78 H139 M101 90 H121"/>
  <path d="M184 66 H214 M184 78 H222 M184 90 H204"/>
</g>
<g fill="none" stroke="{LINE}" stroke-width="2">
  <path d="M68 80 H89 M151 80 H172"/>
</g>
<circle cx="78.5" cy="80" r="4" fill="{NODE}"/>
<circle cx="161.5" cy="80" r="4" fill="{NODE}"/>
""")

# EVM: 32-byte storage words on the left, the stack on the right, one slot warm
# because the article is always about the one slot.
_m("evm", f"""
<g fill="none" stroke="{DIM}" stroke-width="2">
  <rect x="6" y="20" width="104" height="18" rx="3"/>
  <rect x="6" y="44" width="104" height="18" rx="3"/>
  <rect x="6" y="92" width="104" height="18" rx="3"/>
  <rect x="6" y="116" width="104" height="18" rx="3"/>
</g>
<rect x="6" y="68" width="104" height="18" rx="3" fill="rgba(61,90,254,0.16)"
      stroke="{NODE}" stroke-width="2"/>
<g fill="none" stroke="{DIM}" stroke-width="2" stroke-linecap="round">
  <path d="M14 29 H34 M14 53 H44 M14 101 H30 M14 125 H40"/>
</g>
<path d="M14 77 H52" fill="none" stroke="{LINE}" stroke-width="2" stroke-linecap="round"/>
<g fill="none" stroke="{LINE}" stroke-width="2">
  <rect x="150" y="34" width="84" height="20" rx="3"/>
  <rect x="150" y="60" width="84" height="20" rx="3"/>
  <rect x="150" y="86" width="84" height="20" rx="3"/>
</g>
<path d="M130 44 H150" fill="none" stroke="{DIM}" stroke-width="2"/>
<path d="M192 112 V128 M186 122 L192 128 L198 122" fill="none" stroke="{NODE}"
      stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
""")

# Solana: many accounts entering one program at once. The point of the picture
# is the parallelism, so the lanes are the subject and the program is a dot.
_m("solana", f"""
<g fill="none" stroke="{LINE}" stroke-width="2">
  <path d="M8 24 C80 24 110 60 168 78"/>
  <path d="M8 60 C80 60 116 72 168 78"/>
  <path d="M8 100 C80 100 116 86 168 78"/>
  <path d="M8 136 C80 136 110 96 168 78"/>
</g>
<g fill="{DIM}">
  <rect x="0" y="18" width="14" height="12" rx="2"/>
  <rect x="0" y="54" width="14" height="12" rx="2"/>
  <rect x="0" y="94" width="14" height="12" rx="2"/>
  <rect x="0" y="130" width="14" height="12" rx="2"/>
</g>
<circle cx="178" cy="78" r="26" fill="none" stroke="{LINE}" stroke-width="2"/>
<circle cx="178" cy="78" r="7" fill="{NODE}"/>
""")

# Move: a resource leaves its owner and arrives at the next one. The dashed
# outline is the whole idea — the origin is empty afterwards, it was not copied.
_m("move", f"""
<g fill="none" stroke="{LINE}" stroke-width="2">
  <rect x="6" y="46" width="74" height="68" rx="8"/>
  <rect x="160" y="46" width="74" height="68" rx="8"/>
</g>
<rect x="28" y="68" width="30" height="24" rx="4" fill="none" stroke="{DIM}"
      stroke-width="2" stroke-dasharray="4 5"/>
<rect x="182" y="68" width="30" height="24" rx="4" fill="rgba(61,90,254,0.18)"
      stroke="{NODE}" stroke-width="2"/>
<path d="M88 80 H150 M140 72 L150 80 L140 88" fill="none" stroke="{LINE}"
      stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
""")

# Cosmos: two chains and the relay between them. Sovereign columns, one link.
_m("cosmos", f"""
<g fill="none" stroke="{DIM}" stroke-width="2">
  <rect x="10" y="26" width="52" height="22" rx="4"/>
  <rect x="10" y="56" width="52" height="22" rx="4"/>
  <rect x="10" y="86" width="52" height="22" rx="4"/>
  <rect x="178" y="26" width="52" height="22" rx="4"/>
  <rect x="178" y="56" width="52" height="22" rx="4"/>
  <rect x="178" y="86" width="52" height="22" rx="4"/>
</g>
<path d="M62 67 C104 24 136 24 178 67" fill="none" stroke="{LINE}" stroke-width="2"/>
<circle cx="120" cy="38" r="6" fill="{NODE}"/>
<path d="M62 78 C104 120 136 120 178 78" fill="none" stroke="{DIM}"
      stroke-width="2" stroke-dasharray="5 6"/>
""")

# Security: the call that comes back before the first one finished. Drawn as a
# loop returning into the same box, with the state it re-reads still warm.
_m("security", f"""
<g fill="none" stroke="{LINE}" stroke-width="2">
  <rect x="26" y="40" width="96" height="76" rx="8"/>
</g>
<g fill="none" stroke="{DIM}" stroke-width="2" stroke-linecap="round">
  <path d="M42 60 H86 M42 74 H100"/>
</g>
<path d="M42 92 H74" fill="none" stroke="{NODE}" stroke-width="2" stroke-linecap="round"/>
<path d="M122 62 H186 C206 62 206 100 186 100 L130 100 M140 92 L130 100 L140 108"
      fill="none" stroke="{LINE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="196" cy="81" r="4" fill="{NODE}"/>
""")

# AI: a small layered network. Deliberately small — three layers is enough to
# read as one, and more edges just turns into grey fog at this alpha.
_m("ai", f"""
<g fill="none" stroke="{DIM}" stroke-width="1.6">
  <path d="M40 40 L120 34 M40 40 L120 66 M40 40 L120 98 M40 40 L120 126"/>
  <path d="M40 80 L120 34 M40 80 L120 66 M40 80 L120 98 M40 80 L120 126"/>
  <path d="M40 120 L120 34 M40 120 L120 66 M40 120 L120 98 M40 120 L120 126"/>
  <path d="M120 34 L204 60 M120 66 L204 60 M120 98 L204 60 M120 126 L204 60"/>
  <path d="M120 34 L204 100 M120 66 L204 100 M120 98 L204 100 M120 126 L204 100"/>
</g>
<g fill="{LINE}">
  <circle cx="40" cy="40" r="5"/><circle cx="40" cy="80" r="5"/><circle cx="40" cy="120" r="5"/>
  <circle cx="120" cy="34" r="5"/><circle cx="120" cy="66" r="5"/>
  <circle cx="120" cy="98" r="5"/><circle cx="120" cy="126" r="5"/>
</g>
<circle cx="204" cy="60" r="6" fill="{NODE}"/>
<circle cx="204" cy="100" r="6" fill="{NODE}"/>
""")

# Football: a third of a pitch, a passing move, and the shot it ends in. Every
# line is straight, like the passes; the shot is the only dashed one.
_m("football", f"""
<g fill="none" stroke="{DIM}" stroke-width="2">
  <rect x="6" y="18" width="228" height="124" rx="4"/>
  <path d="M234 52 H188 V108 H234"/>
  <path d="M234 70 H212 V90 H234"/>
</g>
<g fill="none" stroke="{LINE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M34 118 L88 94 L124 120 L164 76"/>
</g>
<g fill="{LINE}">
  <circle cx="34" cy="118" r="4"/><circle cx="88" cy="94" r="4"/><circle cx="124" cy="120" r="4"/>
</g>
<path d="M164 76 L210 68" fill="none" stroke="{NODE}" stroke-width="2.4"
      stroke-linecap="round" stroke-dasharray="1 7"/>
<circle cx="164" cy="76" r="4.5" fill="{NODE}"/>
<circle cx="214" cy="67" r="3" fill="{NODE}"/>
""")


# Web2 / systems: one request through the tiers. The dashed return path is the
# half people forget to draw.
_m("systems", f"""
<g fill="none" stroke="{LINE}" stroke-width="2">
  <rect x="4" y="62" width="44" height="36" rx="6"/>
  <rect x="88" y="20" width="58" height="30" rx="5"/>
  <rect x="88" y="66" width="58" height="30" rx="5"/>
  <rect x="88" y="112" width="58" height="30" rx="5"/>
</g>
<g fill="none" stroke="{DIM}" stroke-width="2">
  <path d="M48 80 H70 M70 35 V125 M70 35 H88 M70 80 H88 M70 127 H88"/>
</g>
<g fill="none" stroke="{LINE}" stroke-width="2">
  <path d="M146 35 H176 M146 80 H176 M146 127 H176"/>
  <path d="M176 30 V130"/>
  <ellipse cx="210" cy="52" rx="24" ry="9"/>
  <path d="M186 52 V108 C186 113 197 117 210 117 C223 117 234 113 234 108 V52"/>
  <path d="M186 74 C186 79 197 83 210 83 C223 83 234 79 234 74"/>
</g>
<path d="M176 80 H186" fill="none" stroke="{LINE}" stroke-width="2"/>
<circle cx="26" cy="80" r="5" fill="{NODE}"/>
""")


def motif(name: str, x: float, y: float, scale: float, opacity: float = 1.0) -> str:
    """One motif, positioned. Unknown names fail loudly rather than drawing air."""
    if name == "none":
        return ""
    if name not in MOTIFS:
        raise SystemExit(f"unknown motif {name!r} — pick one of: {', '.join(names())}")
    return (
        f'<g transform="translate({x},{y}) scale({scale})" opacity="{opacity}"'
        f' aria-hidden="true">{MOTIFS[name]}</g>'
    )


def names() -> list[str]:
    return sorted(MOTIFS) + ["none"]
