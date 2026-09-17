"""The scope gate.

The first thing every run does and the only thing that can stop it. It reads
config/scope.yaml and fails closed: a target that does not match an authorized,
unexpired entry is refused, and there is deliberately no override flag. The
guide is explicit that this is a real gate rather than an afterthought, because
the difference between bug bounty work and an attack is authorization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCOPE_FILE = ROOT / "config" / "scope.yaml"


class ScopeError(RuntimeError):
    """Refusal. Raised, never returned, so it cannot be ignored by accident."""


@dataclass(frozen=True)
class Program:
    name: str
    platform: str
    authorization: str
    repos: tuple[str, ...] = ()
    addresses: tuple[str, ...] = ()
    paths: tuple[Path, ...] = ()
    expires: date | None = None

    def expired(self, today: date) -> bool:
        return self.expires is not None and today > self.expires


@dataclass(frozen=True)
class Allowed:
    """Proof a target was authorized. Carried through the run and into reports."""

    target: str
    program: Program
    matched_on: str


_GIT_SUFFIX = re.compile(r"\.git$")
_SCHEME = re.compile(r"^(https?://|git\+https?://|ssh://git@|git@)")
_ADDRESS = re.compile(r"^([a-z0-9-]+):(0x[0-9a-fA-F]{40})$")


def normalize_repo(url: str) -> str:
    """github.com/a/b, https://github.com/a/b.git and git@github.com:a/b are one repo."""
    url = url.strip().rstrip("/")
    url = _SCHEME.sub("", url)
    url = url.replace("github.com:", "github.com/", 1)
    url = _GIT_SUFFIX.sub("", url)
    return url.lower()


def normalize_address(value: str) -> str | None:
    match = _ADDRESS.match(value.strip())
    return f"{match.group(1)}:{match.group(2).lower()}" if match else None


def load_programs(path: Path | None = None) -> list[Program]:
    path = path or SCOPE_FILE
    if not path.exists():
        raise ScopeError(f"no scope file at {path} — nothing is authorized")
    raw = yaml.safe_load(path.read_text()) or {}
    programs = []
    for entry in raw.get("programs") or []:
        missing = {"name", "platform", "authorization"} - set(entry)
        if missing:
            raise ScopeError(
                f"scope entry {entry.get('name', '?')!r} is missing {sorted(missing)} — "
                "every entry must record what authorizes it"
            )
        expires = entry.get("expires")
        programs.append(
            Program(
                name=entry["name"],
                platform=entry["platform"],
                authorization=str(entry["authorization"]),
                repos=tuple(normalize_repo(r) for r in entry.get("repos") or []),
                addresses=tuple(
                    a for a in (normalize_address(x) for x in entry.get("addresses") or []) if a
                ),
                paths=tuple((path.parent.parent / p).resolve() for p in entry.get("paths") or []),
                expires=expires if isinstance(expires, date) else None,
            )
        )
    return programs


def _within(candidate: Path, allowed: Path) -> bool:
    """True only if candidate is allowed or sits underneath it.

    Both sides are resolved first, so `allowed/../../etc` does not sneak past
    and a symlink out of the tree does not either.
    """
    try:
        candidate.resolve().relative_to(allowed.resolve())
    except ValueError:
        return False
    return True


def check_scope(
    target: str,
    *,
    programs: list[Program] | None = None,
    today: date | None = None,
) -> Allowed:
    """Authorize a target, or raise. There is no third outcome and no override."""
    today = today or date.today()
    programs = load_programs() if programs is None else programs
    if not programs:
        raise ScopeError("scope file lists no programs — nothing is authorized")

    address = normalize_address(target)
    repo = normalize_repo(target) if "/" in target else None
    path = Path(target).expanduser()
    is_path = path.exists()

    expired: list[str] = []
    for program in programs:
        hit = None
        if address and address in program.addresses:
            hit = f"address {address}"
        elif repo and repo in program.repos:
            hit = f"repo {repo}"
        elif is_path and any(_within(path, allowed) for allowed in program.paths):
            hit = f"path {path.resolve()}"
        if not hit:
            continue
        if program.expired(today):
            expired.append(f"{program.name} (ended {program.expires})")
            continue
        return Allowed(target=target, program=program, matched_on=hit)

    if expired:
        raise ScopeError(
            f"{target!r} matches a program whose scope has ended: {', '.join(expired)}. "
            "Re-confirm authorization and update config/scope.yaml before running."
        )
    raise ScopeError(
        f"{target!r} is not in scope. Add it to config/scope.yaml with the URL of the "
        "program that authorizes testing it. There is no flag to skip this check."
    )
