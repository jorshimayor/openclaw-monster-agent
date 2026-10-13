#!/usr/bin/env python3
"""One week's work, turned into everything it should become.

    python3 content/pipeline.py "Storage packing costs you 3,355 gas" \
        --evidence "Measured on a 3-slot struct, before and after reordering" \
        --level all --tag "EVM DEEP DIVE"

The premise, which is the only opinion encoded here: a piece worth publishing
comes out of something you actually did, not a topic you picked. So the input
is evidence — a measurement, a finding, a bug — and the three levels are three
depths on that one thing rather than three different articles.

  beginner      the idea that made it make sense
  intermediate  the walkthrough, with the code that runs
  advanced      what surprised you, which only you can write

What this generates is scaffolding: briefs, the outline for each level, the
channel adaptations, and the artwork. It does not write the article. The whole
point of docs/writing-standard.md is that the research and the prose are yours;
a generated draft would be the AI slop that standard exists to refuse.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "out"

LEVELS = ("beginner", "intermediate", "advanced")

# What each level owes the reader. These are prompts for the writer, not
# templates to fill — a filled template reads like a filled template.
BRIEF = {
    "beginner": {
        "owes": "The idea that made this make sense to you, for someone who has not met it.",
        "test": "Could a developer who has never touched this follow it without looking "
                "anything up?",
        "shape": [
            "The concrete situation where this bites. No definitions yet.",
            "The one mental model that unlocks it. A diagram earns its place here.",
            "The smallest example that demonstrates it, running.",
            "What to go and try, in one sentence.",
        ],
        "avoid": "Do not open by defining the term. Open with the problem it solves.",
    },
    "intermediate": {
        "owes": "The walkthrough, with code that runs and numbers that are measured.",
        "test": "Could a working engineer reproduce your result from this alone?",
        "shape": [
            "What you were trying to do and what went wrong.",
            "The working implementation, in full, not in fragments.",
            "The measurement: before, after, and how you measured.",
            "The edge cases you hit and how you handled them.",
            "What you would do differently.",
        ],
        "avoid": "No unmeasured performance claims. If you say faster, say by how much, "
                 "measured how.",
    },
    "advanced": {
        "owes": "What surprised you. Nobody else can write this piece.",
        "test": "Does this contain something a careful reader could not have predicted?",
        "shape": [
            "The assumption you held, stated plainly, so the reversal lands.",
            "The evidence that broke it.",
            "Why the obvious explanation is wrong.",
            "What this implies that is not yet obvious.",
            "The open question you have not answered.",
        ],
        "avoid": "No summary of prior art. Lead with the surprise; the reader can look "
                 "the background up.",
    },
}

CHANNELS = {
    "article": "Long form on the site. The canonical version; everything else points here.",
    "newsletter": "Issue intro: the one sentence that makes someone open the article, "
                  "plus what you learned that week.",
    "x_thread": "Open with the finding, not with 'a thread'. One claim per post. "
                "Last post links the article.",
    "youtube": "Script beats. Show the terminal before explaining it — the proof earns "
               "the explanation.",
}


def slugify(text: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return out[:60]


def lint(text: str, title: str) -> dict:
    """Run the draft through the editorial standard before it goes anywhere."""
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from src.writing.lint import check  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - the linter is optional here
        return {"error": f"linter unavailable: {exc}"}
    return check(text, title=title, profile="technical")


def brief_for(level: str, topic: str, evidence: str) -> str:
    b = BRIEF[level]
    lines = [
        f"# {topic}",
        f"\n**Level:** {level}  ·  **Owes the reader:** {b['owes']}",
        f"\n**The evidence this rests on:** {evidence}",
        f"\n**Passes when:** {b['test']}",
        f"\n**Watch out:** {b['avoid']}",
        "\n## Shape\n",
    ]
    lines += [f"{i}. {step}" for i, step in enumerate(b["shape"], 1)]
    lines += [
        "\n## Draft\n",
        "_Write here. Run `python3 content/pipeline.py --lint <file>` before publishing._\n",
        "\n## Checks before publishing\n",
        "- [ ] Every number is measured, and says how",
        "- [ ] No claim here that the evidence above does not support",
        "- [ ] Code runs as written, from a clean checkout",
        "- [ ] Passes the linter (`docs/writing-standard.md`)",
    ]
    return "\n".join(lines)


def channel_sheet(topic: str, evidence: str) -> str:
    lines = [f"# Channels — {topic}", f"\nEvidence: {evidence}\n"]
    for name, note in CHANNELS.items():
        lines += [f"\n## {name}\n", note, "\n_..._\n"]
    return "\n".join(lines)


def render_art(topic: str, tag: str, site: str, out_dir: Path) -> list[str]:
    """Thumbnail, article header and newsletter art, into this piece's folder.

    --out-dir keeps it out of brand/out: rendering art for one article must not
    overwrite the brand defaults, and must never touch frontend/public, which
    is where the live site favicon lives.
    """
    words = topic.split()
    third = max(1, len(words) // 3)
    thumb = "|".join(
        [" ".join(words[:third]), " ".join(words[third:third * 2]), " ".join(words[third * 2:])]
    )
    cmd = [
        sys.executable, str(ROOT / "brand" / "render.py"),
        "--site", site, "--tag", tag, "--thumb", thumb,
        "--article", thumb, "--news-title", "|".join([" ".join(words[:third]),
                                                      " ".join(words[third:])]),
        "--out-dir", str(out_dir),
        "--only", "thumbnail,article-header,newsletter",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return [f"artwork failed: {proc.stderr.strip()[:200]}"]
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("topic", nargs="?", help="what you actually found or did")
    ap.add_argument("--evidence", default="",
                    help="the measurement, finding or bug this rests on")
    ap.add_argument("--level", default="all", choices=[*LEVELS, "all"])
    ap.add_argument("--tag", default="DEEP DIVE", help="thumbnail tag")
    ap.add_argument("--site", default="jorshimayor.is-a.dev")
    ap.add_argument("--no-art", action="store_true")
    ap.add_argument("--lint", metavar="FILE", help="lint a draft and exit")
    args = ap.parse_args()

    if args.lint:
        path = Path(args.lint)
        result = lint(path.read_text(), title=path.stem)
        if "error" in result:
            print(result["error"]); return 1
        findings = result.get("findings", [])
        print(f"{result.get('words')} words · {len(findings)} findings")
        for f in findings:
            print(f"  [{f['severity']}] {f['rule']}: {f['excerpt'][:70]}")
        return 0 if result.get("passes") else 1

    if not args.topic:
        ap.error("a topic is required unless --lint is given")
    if not args.evidence:
        # The whole premise is that a piece comes out of something you did.
        ap.error("--evidence is required: name the measurement, finding or bug. "
                 "A piece with no evidence behind it is the thing the writing "
                 "standard exists to refuse.")

    slug = f"{date.today():%Y-%m-%d}-{slugify(args.topic)}"
    folder = OUT / slug
    folder.mkdir(parents=True, exist_ok=True)

    levels = LEVELS if args.level == "all" else (args.level,)
    written = []
    for level in levels:
        path = folder / f"{level}.md"
        if not path.exists():
            path.write_text(brief_for(level, args.topic, args.evidence))
        written.append(path)

    channels = folder / "channels.md"
    if not channels.exists():
        channels.write_text(channel_sheet(args.topic, args.evidence))
    written.append(channels)

    (folder / "meta.json").write_text(json.dumps({
        "topic": args.topic, "evidence": args.evidence,
        "created": date.today().isoformat(), "tag": args.tag,
    }, indent=2))

    for path in written:
        print(f"  {path.relative_to(ROOT)}")
    if not args.no_art:
        print("\nartwork:")
        for line in render_art(args.topic, args.tag, args.site, folder):
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
