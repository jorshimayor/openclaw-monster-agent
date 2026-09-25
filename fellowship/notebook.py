"""This week's lab, as a Jupyter notebook.

Generated rather than hand-started because the structure is the same every
week and the friction of an empty notebook is what stops the habit. Reading,
reproduction, lab, thoughts, article seed: the same five sections for 48 weeks,
so the record is comparable at week 40 to what it was at week 4.

The three-pass reading prompts come from Keshav's How to Read a Paper, which
the programme places at week 17 and which is worth having from week 1.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


def md(text: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str = "") -> dict[str, Any]:
    return {
        "cell_type": "code", "execution_count": None, "metadata": {},
        "outputs": [], "source": text.splitlines(keepends=True),
    }


def build_cells(plan, today: date) -> list[dict[str, Any]]:
    reading = plan.reading
    path_line = f" · Path {plan.path}" if plan.path else ""
    cells = [
        md(
            f"# Week {plan.week:02d} — {plan.topic}\n"
            f"\n**{plan.block}**{path_line}  ·  generated {today.isoformat()}\n"
            f"\n{plan.concepts}\n"
        )
    ]

    if reading:
        cells += [
            md(
                f"## 1. The paper\n"
                f"\n**{reading['title']}** — {reading['cite']}  \n{reading['url']}\n"
                "\nThree passes (Keshav). Do not start at the top and read to the bottom.\n"
                "\n**Pass 1 — five minutes.** Title, abstract, intro, section headings, "
                "conclusions. Answer: what category, what is it related to, are the "
                "assumptions valid, what are the contributions?\n"
                "\n**Pass 2 — an hour.** Figures and tables carefully. Mark references you "
                "have not read. You should be able to summarise the main thrust with "
                "supporting evidence to someone else.\n"
                "\n**Pass 3 — the reproduction below.** Re-create the core claim at small "
                "scale. This is the pass the programme actually grades.\n"
            ),
            md("### Pass 1 and 2 notes\n\n_What is the claim, and what evidence is offered for it?_\n"),
            md(
                "## 2. Reproduction\n"
                "\nSmall scale is fine. The point is that the claim survives contact with "
                "your own code, not that you match the paper's numbers.\n"
                "\n**The claim I am reproducing:** _one sentence_\n"
                "\n**What would falsify it:** _one sentence — write this BEFORE running anything_\n"
            ),
            code("# Reproduction\n"),
            code(),
            md("### What actually happened\n\n_Including the ways it did not match._\n"),
        ]

    if plan.lab:
        cells += [
            md(f"## 3. Lab\n\n{plan.lab}\n"),
            code("# Lab\n"),
            code(),
            md("### Result\n\n_What works, what does not, what you measured._\n"),
        ]

    cells += [
        md(
            "## 4. Thoughts\n"
            "\nThe part that is easy to skip and hardest to reconstruct later.\n"
            "\n**What surprised me:**\n"
            "\n**What I did not believe:**\n"
            "\n**What I would test next:**\n"
            "\n**Where this connects to the team's research directions** "
            "(verifiable agent-work eval harnesses; retrieval-grounded review assistance):\n"
        ),
        md(
            "## 5. Article seed\n"
            "\nOne write-up a week compounds into the week 47 record. Do not start a draft "
            "here — capture the angle while it is fresh.\n"
            "\n**The one thing a reader would not already know:**\n"
            "\n**The measurement that makes it checkable:**\n"
            "\n**Working title:**\n"
            "\n> Run the draft through `/write` before publishing. The standard is in "
            "`docs/writing-standard.md`.\n"
        ),
    ]

    if plan.deliverable:
        cells.append(
            md(f"## 6. Deliverable — due end of this week\n\n{plan.deliverable}\n\n- [ ] done\n")
        )
    return cells


def write_notebook(plan, out_dir: Path, *, force: bool = False, today: date | None = None) -> Path:
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{plan.slug}.ipynb"
    if path.exists() and not force:
        # Never clobber work. The notebook is where the week's thinking lives.
        return path
    notebook = {
        "cells": build_cells(plan, today),
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "fellowship": {"week": plan.week, "block": plan.block, "path": plan.path},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    return path
