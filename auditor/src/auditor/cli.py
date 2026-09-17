"""Command line.

    python -m auditor doctor
    python -m auditor scope ./targets/practice/damn-vulnerable-defi
    python -m auditor audit ./targets/practice/damn-vulnerable-defi --vertical lending
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .budget import Budget
from .pipeline import audit
from .schemas import Vertical
from .scope import ScopeError, check_scope
from .tools.doctor import check_toolchain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auditor")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="which verification tools are installed")

    scope_cmd = sub.add_parser("scope", help="check whether a target is authorized")
    scope_cmd.add_argument("target")

    audit_cmd = sub.add_parser("audit", help="run the pipeline against a target")
    audit_cmd.add_argument("target")
    audit_cmd.add_argument("--vertical", required=True, choices=[v.value for v in Vertical])
    audit_cmd.add_argument("--max-hypotheses", type=int, default=12)
    audit_cmd.add_argument("--max-steps", type=int, default=120)
    audit_cmd.add_argument("--max-usd", type=float, default=10.0)
    audit_cmd.add_argument("--out", type=Path, default=Path("reports"))

    args = parser.parse_args(argv)

    if args.command == "doctor":
        results = check_toolchain()
        for result in results:
            print(result.line)
        missing_required = [r.tool for r in results if r.required and not r.installed]
        if missing_required:
            print(f"\n{', '.join(missing_required)} is required — nothing can be proven without it.")
            return 1
        return 0

    if args.command == "scope":
        try:
            allowed = check_scope(args.target)
        except ScopeError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        print(f"authorized by {allowed.program.name} ({allowed.matched_on})")
        print(f"  {allowed.program.authorization}")
        return 0

    try:
        report = audit(
            args.target,
            args.vertical,
            budget=Budget(max_steps=args.max_steps, max_usd=args.max_usd),
            max_hypotheses=args.max_hypotheses,
            out_dir=args.out,
        )
    except ScopeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    print(f"target        {report.target} ({report.vertical.value})")
    print(f"authorized by {report.authorization}")
    print(f"invariants    {len(report.invariants)}")
    print(f"hypotheses    {len(report.hypotheses)}")
    print(f"PROVEN        {len(report.findings)}")
    print(f"discarded     {len(report.discarded)}")
    print(f"budget        {report.budget}")
    if report.static_skipped:
        print(f"note          static sweep was partial, missing: {', '.join(report.static_skipped)}")
    if report.stopped_early:
        print(f"stopped early {report.stopped_early}")
    print(f"\nreport written to {args.out / 'report.json'}")
    print("Nothing here is submittable until a human has reviewed it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
