#!/usr/bin/env bash
#
# precommit_changed_files.sh — run pre-commit hooks on the files an agent is
# about to commit, BEFORE pushing. Catches the four cheap CI failures
# (codespell, whitespace/EOL, phpcs styling, rector) that account for ~80%
# of the post-push CI rejections we hit during Wk2 Next05.
#
# Usage (from openemr/ root):
#   ./scripts/precommit_changed_files.sh                  # check staged + modified files
#   ./scripts/precommit_changed_files.sh --staged-only    # check only `git add`-ed files
#   ./scripts/precommit_changed_files.sh --all-files      # check every file in repo
#
# Exit codes:
#   0 = clean (or no files matched).
#   1 = at least one hook reported a violation. Re-run after fixing, or
#       re-stage auto-fixed files (`git add` then commit).
#   2 = pre-commit not installed / mis-configured.
#
# Why this exists: every commit during the Wk2 Next05 sprint window failed at
# least one CI lint job because the repo's .pre-commit-config.yaml hooks were
# never wired into .git/hooks/pre-commit. This script is the manual fallback —
# the long-term fix is `pre-commit install` once per clone.
#
# Hooks invoked (from .pre-commit-config.yaml):
#   - trailing-whitespace, end-of-file-fixer, mixed-line-ending
#   - codespell  (medical terms go in .codespell-ignore-words.txt under
#                  the "Medical abbreviations and terminology" group)
#   - phpcbf     (auto-fixes most phpcs violations including alphabetical
#                  use-statement sorting; re-stage and re-commit)
#   - phpcs      (residual style violations phpcbf can't auto-fix)
#   - rector     (auto-converts old PHP idioms; ClosureToArrowFunctionRector
#                  is the most common single-rule trigger)
#   - phpstan    (full project type-graph analysis — slow but cheaper than
#                  pushing and waiting for CI)
#
# Skips (auto-detected):
#   - The "phpstan" hook is the slowest by ~10x; the script invokes it only
#     when --include-phpstan is also passed, OR when the changed files
#     include any *.php under interface/, src/, library/, or modules/.
#

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# ---------------------------------------------------------------------------
# Pre-flight: confirm pre-commit is installed.
# ---------------------------------------------------------------------------
if ! command -v pre-commit >/dev/null 2>&1; then
    cat >&2 <<EOF
ERROR: pre-commit is not on PATH.

Install (one-time per machine, NOT per clone):
  pip install --user pre-commit

Then optionally install the git hook so commits get checked automatically:
  pre-commit install

If you are on a machine where pip is not available (rare), the alternative
is the project-recommended 'prek' tool. See openemr/CLAUDE.md "Common Gotchas".
EOF
    exit 2
fi

# ---------------------------------------------------------------------------
# Argument parsing.
# ---------------------------------------------------------------------------
mode="changed"
include_phpstan="auto"
for arg in "$@"; do
    case "${arg}" in
        --staged-only)    mode="staged"  ;;
        --all-files)      mode="all"     ;;
        --include-phpstan) include_phpstan="yes" ;;
        --skip-phpstan)   include_phpstan="no"  ;;
        -h|--help)
            sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# //'
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: ${arg}" >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Build the file list.
# ---------------------------------------------------------------------------
case "${mode}" in
    all)
        echo ">>> mode=all-files (running pre-commit run --all-files)"
        if [[ "${include_phpstan}" == "no" ]]; then
            SKIP=phpstan pre-commit run --all-files
        else
            pre-commit run --all-files
        fi
        exit $?
        ;;
    staged)
        FILES=$(git diff --cached --name-only --diff-filter=ACMR)
        ;;
    changed)
        # staged + unstaged-but-modified, deduped
        FILES=$( (git diff --cached --name-only --diff-filter=ACMR; \
                  git diff --name-only --diff-filter=ACMR) | sort -u)
        ;;
esac

if [[ -z "${FILES}" ]]; then
    echo ">>> no changed/staged files. nothing to check."
    exit 0
fi

echo ">>> checking the following files (mode=${mode}):"
echo "${FILES}" | sed 's/^/    /'

# ---------------------------------------------------------------------------
# Decide whether to run phpstan.
# ---------------------------------------------------------------------------
if [[ "${include_phpstan}" == "auto" ]]; then
    if echo "${FILES}" | grep -qE '\.(php)$'; then
        include_phpstan="yes"
    else
        include_phpstan="no"
    fi
fi
if [[ "${include_phpstan}" == "no" ]]; then
    export SKIP="${SKIP:-}${SKIP:+,}phpstan"
    echo ">>> skipping phpstan hook (no .php files changed; pass --include-phpstan to override)"
fi

# ---------------------------------------------------------------------------
# Run pre-commit on the file set. xargs -d \\n preserves spaces in filenames.
# ---------------------------------------------------------------------------
echo ">>> invoking pre-commit run --files ..."
echo "${FILES}" | xargs -d '\n' pre-commit run --files
rc=$?

if [[ ${rc} -eq 0 ]]; then
    echo ">>> all hooks PASSED. safe to commit."
else
    echo ">>> at least one hook reported a violation."
    echo ">>> auto-fix files were modified by phpcbf / rector / end-of-file-fixer:"
    echo "    inspect with 'git diff', then 'git add' the corrected files and re-commit."
fi
exit ${rc}
