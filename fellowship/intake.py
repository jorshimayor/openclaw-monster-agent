"""Filing what you are given.

Two destinations. A thought goes to a dated markdown file, because prose does
not belong in JSON. An assignment goes into the config the scheduler reads, so
that work handed to you mid-programme is chased exactly like planned work
instead of living in a document nobody opens.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def add_note(notes_dir: Path, week: int, text: str, today: date) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / (f"w{week:02d}.md" if week else "unscheduled.md")
    if not path.exists():
        heading = f"# Week {week:02d}\n" if week else "# Unscheduled\n"
        path.write_text(heading)
    with path.open("a") as fh:
        fh.write(f"\n## {today.isoformat()}\n\n{text.strip()}\n")
    return path


def add_assignment(
    config_path: Path, *, week: int, kind: str, title: str, url: str = "", due: str = ""
) -> None:
    config = json.loads(config_path.read_text())
    entry = {"week": int(week), "kind": kind, "title": title}
    if url:
        entry["url"] = url
    if due:
        entry["due"] = due
    config.setdefault("assignments", []).append(entry)
    config["assignments"].sort(key=lambda a: (a.get("week", 0), a.get("kind", "")))
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=True) + "\n")
