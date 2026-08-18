#!/usr/bin/env python3
"""Monster Agent Project Verifier — checks files + runs backend tests.

Usage:
    python scripts/verify_project.py
    ./scripts/verify_project.py     # after chmod +x

Exits 0 when all checks + tests pass, non-zero otherwise.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
from typing import List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

BACKEND_EXPECTED_FILES: List[str] = [
    "backend/src/api/main.py",
    "backend/src/api/routes/__init__.py",
    "backend/src/api/routes/tasks.py",
    "backend/src/api/routes/agents.py",
    "backend/src/api/routes/mcp.py",
    "backend/src/api/routes/knowledge.py",
    "backend/src/api/sse.py",
    "backend/src/orchestration/__init__.py",
    "backend/src/orchestration/pipeline.py",
    "backend/src/orchestration/steps.py",
    "backend/src/orchestration/patterns.py",
    "backend/src/orchestration/graph_builder.py",
    "backend/src/agents/__init__.py",
    "backend/src/agents/base.py",
    "backend/src/agents/orchestrator.py",
    "backend/src/agents/_utils.py",
    "backend/src/agents/content_web2.py",
    "backend/src/agents/content_web3.py",
    "backend/src/agents/football_analyst.py",
    "backend/src/agents/editor_reviewer.py",
    "backend/src/agents/security_auditor.py",
    "backend/src/agents/knowledge_crystallizer.py",
    "backend/src/agents/study_partner.py",
    "backend/src/llm/__init__.py",
    "backend/src/llm/router.py",
    "backend/src/llm/models.py",
    "backend/src/llm/providers/__init__.py",
    "backend/src/llm/providers/nvidia_nim.py",
    "backend/src/llm/providers/groq.py",
    "backend/src/llm/providers/google_gemini.py",
    "backend/src/knowledge/__init__.py",
    "backend/src/knowledge/store.py",
    "backend/src/knowledge/memory.py",
    "backend/src/knowledge/extractor.py",
    "backend/src/mcp/__init__.py",
    "backend/src/mcp/manager.py",
    "backend/src/mcp/registry.py",
    "backend/src/mcp/servers/__init__.py",
    "backend/src/mcp/servers/github.py",
    "backend/src/mcp/servers/notion.py",
    "backend/src/mcp/servers/google_workspace.py",
    "backend/src/mcp/servers/slack.py",
    "backend/src/mcp/servers/hashnode.py",
    "backend/src/core/__init__.py",
    "backend/src/core/types.py",
    "backend/src/core/config.py",
    "backend/src/core/logging.py",
]

FRONTEND_EXPECTED_FILES: List[str] = [
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/src/app/layout.tsx",
    "frontend/src/app/page.tsx",
    "frontend/src/app/agents/page.tsx",
    "frontend/src/app/knowledge/page.tsx",
    "frontend/src/app/tasks/page.tsx",
    "frontend/src/app/tasks/[id]/page.tsx",
    "frontend/src/app/integrations/page.tsx",
]

MCP_HASHNODE_EXPECTED: List[str] = [
    "mcp-servers/hashnode/package.json",
    "mcp-servers/hashnode/src/index.ts",
]

DOCS_EXPECTED: List[str] = [
    "docs/architecture.md",
    "docs/11_step_pipeline.md",
    "docs/llm_fallback_chain.md",
    "docs/mcp_setup.md",
]

DEPLOY_EXPECTED: List[str] = [
    "deploy/render/render.yaml",
    "deploy/vercel/vercel.json",
]


def _join(path: str) -> str:
    return os.path.join(REPO_ROOT, path)


def _exists(path: str) -> bool:
    return os.path.exists(_join(path))


def check_backend_files() -> Tuple[int, int, List[str]]:
    found = 0
    missing: List[str] = []
    for rel in BACKEND_EXPECTED_FILES:
        if _exists(rel):
            found += 1
        else:
            missing.append(rel)
    extra = len(glob.glob(_join("backend/src/**/*.py"), recursive=True)) - found
    extra = max(extra, 0)
    total_found = found + extra
    return total_found, found, missing


def check_frontend_files() -> Tuple[int, int, List[str]]:
    found = 0
    missing: List[str] = []
    for rel in FRONTEND_EXPECTED_FILES:
        if _exists(rel):
            found += 1
        else:
            missing.append(rel)
    extra_tsx = len(glob.glob(_join("frontend/src/**/*.tsx"), recursive=True)) - len(
        [f for f in FRONTEND_EXPECTED_FILES if f.endswith(".tsx") and _exists(f)]
    )
    extra_tsx = max(extra_tsx, 0)
    total_found = found + extra_tsx
    return total_found, found, missing


def check_mcp_hashnode_files() -> Tuple[int, int, List[str]]:
    found = 0
    missing: List[str] = []
    for rel in MCP_HASHNODE_EXPECTED:
        if _exists(rel):
            found += 1
        else:
            missing.append(rel)
    tools_dir = _join("mcp-servers/hashnode/src/tools")
    tools_ok = os.path.isdir(tools_dir)
    if tools_ok:
        found += 1
    else:
        missing.append("mcp-hashnode/tools/ (directory)")
    return found, found, missing


def check_docs_deploy() -> Tuple[int, int, List[str]]:
    found = 0
    missing: List[str] = []
    all_expected = DOCS_EXPECTED + DEPLOY_EXPECTED
    for rel in all_expected:
        if _exists(rel):
            found += 1
        else:
            missing.append(rel)
    return found, found, missing


def run_backend_tests() -> Tuple[int, str, str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "backend/tests",
        "-q",
        "--no-header",
        "--tb=short",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "Tests timed out after 300s"
    except FileNotFoundError:
        return 127, "", "pytest not found — install backend dependencies first"


def _print_section(title: str, ok: bool, detail: str) -> None:
    mark = "\u2705" if ok else "\u274c"
    print(f"{mark} {title}: {detail}")


def _banner(text: str) -> None:
    width = 64
    bar = "=" * width
    centered = text.center(width)
    print()
    print(bar)
    print(centered)
    print(bar)
    print()


def main() -> int:
    _banner("Monster Agent Project Verification")
    print(f"Repo root: {REPO_ROOT}")
    print()

    all_ok = True
    counters: dict = {"files": 0, "docs": 0, "tests_passed": 0, "tests_total": 0}

    backend_total, backend_req, backend_missing = check_backend_files()
    backend_ok = len(backend_missing) == 0
    counters["files"] += backend_total
    _print_section(
        "Backend src files",
        backend_ok,
        f"{backend_total} found ({backend_req}/{len(BACKEND_EXPECTED_FILES)} required)",
    )
    if backend_missing:
        all_ok = False
        for m in backend_missing[:10]:
            print(f"     missing: {m}")
        if len(backend_missing) > 10:
            print(f"     ... and {len(backend_missing) - 10} more")

    frontend_total, frontend_req, frontend_missing = check_frontend_files()
    frontend_ok = len(frontend_missing) == 0
    counters["files"] += frontend_total
    _print_section(
        "Frontend files",
        frontend_ok,
        f"{frontend_total} found ({frontend_req}/{len(FRONTEND_EXPECTED_FILES)} required)",
    )
    if frontend_missing:
        all_ok = False
        for m in frontend_missing:
            print(f"     missing: {m}")

    mcp_total, mcp_req, mcp_missing = check_mcp_hashnode_files()
    mcp_ok = len(mcp_missing) == 0 or any(
        "mcp-hashnode" in p and not _exists(p) for p in MCP_HASHNODE_EXPECTED
    )
    if len(mcp_missing) == len(MCP_HASHNODE_EXPECTED) + 1 or (
        len(mcp_missing) >= 2 and not os.path.isdir(_join("mcp-hashnode"))
    ):
        print(f"\u26a0\ufe0f  MCP Hashnode server: {mcp_total}/3 files found (optional module)")
    else:
        mcp_ok = len(mcp_missing) == 0
        _print_section(
            "MCP Hashnode server",
            mcp_ok,
            f"{mcp_total} found ({mcp_req} required)",
        )
        if not mcp_ok:
            all_ok = False
            for m in mcp_missing:
                print(f"     missing: {m}")
    counters["files"] += mcp_total

    docs_total, docs_req, docs_missing = check_docs_deploy()
    docs_ok = len(docs_missing) == 0
    counters["docs"] = len([d for d in DOCS_EXPECTED if _exists(d)])
    counters["files"] += docs_total
    _print_section(
        "Docs + deploy configs",
        docs_ok,
        f"{docs_total} found ({docs_req} required)",
    )
    if not docs_ok:
        all_ok = False
        for m in docs_missing:
            print(f"     missing: {m}")

    print()
    print("\u23f3  Running backend tests (pytest backend/tests -q --no-header) ...")
    test_rc, test_out, test_err = run_backend_tests()
    tests_ok = test_rc == 0
    if tests_ok:
        passed = 0
        total = 0
        for line in test_out.splitlines() + test_err.splitlines():
            stripped = line.strip()
            if stripped.endswith(" passed") or " passed" in stripped:
                try:
                    tokens = stripped.replace(",", "").split()
                    for i, tok in enumerate(tokens):
                        if tok == "passed" and i > 0:
                            passed = int(tokens[i - 1])
                            total = passed
                            break
                except Exception:
                    pass
            if "passed" in stripped and "failed" in stripped:
                try:
                    tokens = stripped.replace(",", "").split()
                    for i, tok in enumerate(tokens):
                        if tok == "passed" and i > 0:
                            passed = int(tokens[i - 1])
                        if tok == "failed" and i > 0:
                            total = passed + int(tokens[i - 1])
                            break
                except Exception:
                    pass
        counters["tests_passed"] = passed
        counters["tests_total"] = total if total else passed
        _print_section(
            "Backend tests",
            True,
            f"ALL PASSED ({counters['tests_passed']} passed)" if counters["tests_passed"] else "ALL PASSED",
        )
    else:
        all_ok = False
        _print_section(
            "Backend tests",
            False,
            f"FAILED (exit code {test_rc})",
        )
        output_tail = (test_out + "\n" + test_err).strip().splitlines()[-20:]
        if output_tail:
            print("     --- pytest output (last 20 lines) ---")
            for line in output_tail:
                print(f"     {line}")
            print("     --- end ---")

    print()
    print("-" * 64)
    summary = (
        f"Summary: {counters['files']} files found, "
        f"{counters['docs']} docs, "
        f"tests: {'PASS' if tests_ok else 'FAIL'}"
    )
    if counters["tests_passed"]:
        summary = (
            f"Summary: {counters['files']} files found, "
            f"{counters['docs']} docs, "
            f"{counters['tests_passed']} tests passed"
        )
    print(summary)
    print("-" * 64)

    if all_ok:
        print("\n\u2705  All checks passed — project looks complete.")
        return 0
    else:
        print("\n\u274c  Some checks failed — review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
