"""The two dependency manifests must agree.

CI installs with pip and never sees poetry's dev group, so `respx` — declared in
pyproject and present on every developer machine — was simply absent on the
runner. Collection died before a single test ran, and the failure surfaced as a
red deploy rather than a missing line in a file.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]


def _poetry_dev_packages() -> set[str]:
    data = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    group = data["tool"]["poetry"]["group"]["dev"]["dependencies"]
    return {name.lower().replace("_", "-") for name in group}


def _pip_dev_packages() -> set[str]:
    out: set[str] = set()
    for line in (BACKEND / "requirements-dev.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        name = re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip()
        if name:
            out.add(name.lower().replace("_", "-"))
    return out


def test_dev_requirements_match_pyproject() -> None:
    poetry, pip = _poetry_dev_packages(), _pip_dev_packages()
    missing_from_pip = poetry - pip
    extra_in_pip = pip - poetry
    assert not missing_from_pip, (
        f"declared in pyproject's dev group but missing from requirements-dev.txt: "
        f"{sorted(missing_from_pip)} — CI installs with pip and would fail to collect"
    )
    assert not extra_in_pip, (
        f"in requirements-dev.txt but not declared in pyproject: {sorted(extra_in_pip)}"
    )


def test_every_test_only_import_is_declared() -> None:
    """A third-party module imported by the suite but declared nowhere is the
    exact shape of this failure."""
    # Ask Python what its own standard library is rather than maintaining a
    # list by hand — the hand-written version was already missing `math`.
    stdlib_and_local = {m.lower() for m in sys.stdlib_module_names} | {
        "src",  # the package under test
        "the",  # a docstring line that the import regex catches
    }
    declared = _pip_dev_packages() | {
        re.split(r"[<>=!~\[]", l, maxsplit=1)[0].strip().lower()
        for l in (BACKEND / "requirements.txt").read_text().splitlines()
        if l.strip() and not l.strip().startswith("#")
    }
    imported: set[str] = set()
    for path in (BACKEND / "tests").rglob("*.py"):
        for line in path.read_text().splitlines():
            m = re.match(r"^\s*(?:from|import)\s+([a-zA-Z_][\w]*)", line)
            if m:
                imported.add(m.group(1).lower())
    undeclared = imported - stdlib_and_local - declared
    assert not undeclared, f"imported by tests but declared in no manifest: {sorted(undeclared)}"
