"""CLI for the Flow Research fellowship.

    python3 -m fellowship status         where you are on the 48 weeks
    python3 -m fellowship lab            generate this week's Jupyter notebook
    python3 -m fellowship note "..."     log a thought against this week
    python3 -m fellowship assign ...     file an assignment you were given

Run it from the repo root. The 48-week plan and the week resolver live in the
backend, because that is what files your commitments and sends the reminders;
duplicating either here would mean two calendars that disagree by week 30.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from src.agents import fellowship as plan  # noqa: E402
from .notebook import write_notebook  # noqa: E402
from .intake import add_assignment, add_note  # noqa: E402


def cmd_status(_args) -> int:
    s = plan.summary()
    if not s.get("enabled"):
        print("fellowship is switched off in backend/config/fellowship.json")
        return 1
    if not s["started"]:
        from datetime import date as _d
        days = (_d.fromisoformat(s["programme_start"]) - _d.today()).days
        print(f"not started — week 1 begins {s['programme_start']}, in {days} day(s)")
        print(f"first up: {s['cohort']}, 48 weeks at 20 hours a week")
        return 0
    if s["finished"]:
        print(f"finished — 48 weeks ended {s['week_end']}")
        return 0

    print(f"{s['cohort']}  ·  week {s['week']} of {s['total_weeks']}  ·  {s['weeks_left']} left")
    print(f"{s['block']} — day {s['day_of_week']} of 7 ({s['week_start']} to {s['week_end']})")
    print(f"path: {s['path'] or 'not chosen yet (due week 17)'}")
    print()
    if s["awaiting_path_choice"]:
        print("THIS WEEK IS THE CHOICE. Set \"path\" to \"A\" or \"B\" in")
        print("backend/config/fellowship.json before doing anything else:")
        for alt in s["alternatives"]:
            print(f"  Path {alt['path']}: {alt['topic']}")
            print(f"    {alt['lab']}")
        return 0
    print(f"topic   {s['topic']}")
    if s["reading"]:
        print(f"paper   {s['reading']['title']} ({s['reading']['cite']})")
        print(f"        {s['reading']['url']}")
    if s["lab"]:
        print(f"lab     {s['lab']}")
    if s["deliverable"]:
        print(f"DUE     {s['deliverable']}")
    return 0


def cmd_lab(args) -> int:
    pos = plan.position()
    if pos is None or not pos.started or pos.finished:
        print("no active week — check `python3 -m fellowship status`")
        return 1
    if pos.plan is None:
        print("choose your path first (week 17 decision) — see `status`")
        return 1
    path = write_notebook(pos.plan, ROOT / "fellowship" / "labs", force=args.force)
    print(f"wrote {path.relative_to(ROOT)}")
    print("  jupyter lab " + str(path.relative_to(ROOT)))
    return 0


def cmd_note(args) -> int:
    pos = plan.position()
    week = pos.week if pos and pos.started and not pos.finished else 0
    path = add_note(ROOT / "fellowship" / "notes", week, " ".join(args.text), date.today())
    print(f"logged to {path.relative_to(ROOT)}")
    return 0


def cmd_assign(args) -> int:
    pos = plan.position()
    week = args.week or (pos.week if pos and pos.started else 1)
    add_assignment(
        ROOT / "backend" / "config" / "fellowship.json",
        week=week, kind=args.kind, title=args.title, url=args.url, due=args.due,
    )
    print(f"filed {args.kind} against week {week}: {args.title}")
    print("It will be filed as a commitment and chased like the rest of the week's work.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fellowship")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="where you are on the 48 weeks").set_defaults(fn=cmd_status)

    lab = sub.add_parser("lab", help="generate this week's Jupyter notebook")
    lab.add_argument("--force", action="store_true", help="overwrite an existing notebook")
    lab.set_defaults(fn=cmd_lab)

    note = sub.add_parser("note", help="log a thought against this week")
    note.add_argument("text", nargs="+")
    note.set_defaults(fn=cmd_note)

    assign = sub.add_parser("assign", help="file an assignment you were given")
    assign.add_argument("title")
    assign.add_argument("--kind", default="assignment",
                        choices=["assignment", "book", "project", "reading", "deadline"])
    assign.add_argument("--week", type=int, help="defaults to the current week")
    assign.add_argument("--url", default="")
    assign.add_argument("--due", default="", help="YYYY-MM-DD")
    assign.set_defaults(fn=cmd_assign)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
