#!/usr/bin/env python3
"""check_pr_has_tests.py — fail CI if a code-touching PR adds zero tests.

Plan §15.5.4 + antipattern §13.19: every code-touching PR must add at least
one test file (`test_*.py`) OR at least one eval case JSON file. Refactor and
doc-only PRs are exempt.

Heuristic (intentionally simple — the goal is awareness, not exhaustive
classification):

    code-touching change = a *.py file outside tests/ and evals/cases/
                           OR a *.php / *.js / *.ts file outside tests/
    test-adding change   = a new test_*.py file OR new evals/cases/*.json file
                           OR a new tests/**/*.php file (PHPUnit)

If a PR has any code-touching change but zero test additions, exit 1.

Usage (in GitHub Actions):
    python scripts/check_pr_has_tests.py --base $BASE_SHA --head $HEAD_SHA

Usage (locally against a feature branch):
    python scripts/check_pr_has_tests.py --base origin/master --head HEAD
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys


CODE_PATTERNS = [
    re.compile(r"^agent/copilot-api/app/.*\.py$"),
    re.compile(r"^interface/modules/custom_modules/oe-module-clinical-copilot/.*\.(php|js|css)$"),
    re.compile(r"^scripts/.*\.(py|sh)$"),
]

# Paths that count as "test additions" (presence ≥1 of these means PR is fine)
TEST_PATTERNS = [
    re.compile(r"^agent/copilot-api/tests/.*test_.*\.py$"),
    re.compile(r"^agent/copilot-api/evals/cases/.*\.json$"),
    re.compile(r"^agent/copilot-api/evals/live_smoke/.*\.json$"),
    re.compile(r"^interface/modules/custom_modules/oe-module-clinical-copilot/tests/.*\.(php|js)$"),
]

# Paths that are ALWAYS exempt (doc-only, config-only, workflow-only)
EXEMPT_PATTERNS = [
    re.compile(r".*\.md$"),
    re.compile(r"^agentdocs/"),
    re.compile(r"^openemr/agentdocs/"),
    re.compile(r"^\.github/workflows/"),
    re.compile(r"^\.pre-commit-config\.yaml$"),
    re.compile(r".*\.gitignore$"),
]


def _git_diff_files(base: str, head: str) -> list[tuple[str, str]]:
    """Return (status, path) for files changed between base..head."""
    raw = subprocess.check_output(
        ["git", "diff", "--name-status", f"{base}..{head}"],
        text=True,
    )
    out: list[tuple[str, str]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        out.append((status, path))
    return out


def _matches_any(path: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.match(path) for p in patterns)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/master")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument(
        "--allow-no-tests",
        action="store_true",
        help="Bypass the check (for refactor PRs — cite a reason in PR description).",
    )
    args = parser.parse_args()

    if args.allow_no_tests:
        print("check_pr_has_tests: bypassed via --allow-no-tests")
        return 0

    files = _git_diff_files(args.base, args.head)
    if not files:
        print("check_pr_has_tests: no changes in diff; skipping.")
        return 0

    code_changes: list[str] = []
    test_additions: list[str] = []

    for status, path in files:
        if _matches_any(path, EXEMPT_PATTERNS):
            continue
        if _matches_any(path, TEST_PATTERNS):
            # Either added or modified counts — if a test changed, the PR
            # touches the test surface.
            test_additions.append(path)
            continue
        if _matches_any(path, CODE_PATTERNS):
            code_changes.append(path)

    if code_changes and not test_additions:
        print("check_pr_has_tests: FAIL", file=sys.stderr)
        print("", file=sys.stderr)
        print("Code-touching changes (no accompanying test additions):", file=sys.stderr)
        for p in code_changes[:20]:
            print(f"  - {p}", file=sys.stderr)
        if len(code_changes) > 20:
            print(f"  ... and {len(code_changes) - 20} more", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Plan §15.5.4 + antipattern §13.19: every code-touching PR must",
            file=sys.stderr,
        )
        print(
            "add at least one test (test_*.py) OR eval case (evals/cases/*.json).",
            file=sys.stderr,
        )
        print(
            "If this is a pure refactor, pass --allow-no-tests and cite the",
            file=sys.stderr,
        )
        print("reason in your PR description.", file=sys.stderr)
        return 1

    print(
        f"check_pr_has_tests: OK "
        f"({len(code_changes)} code change(s), {len(test_additions)} test addition(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
