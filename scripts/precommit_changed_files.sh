#!/usr/bin/env bash
#
# precommit_changed_files.sh — run pre-commit hooks on the files an agent is
# about to commit, BEFORE pushing. Catches the cheap CI failures (codespell,
# whitespace/EOL, phpcs styling, rector, shellcheck) that account for ~80%
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
# Extra checks NOT in .pre-commit-config.yaml but run by GitHub Actions —
# this script runs them too to avoid post-push CI rejections:
#   - shellcheck (via Docker `koalaman/shellcheck:stable`) on changed .sh
#                files. Mirrors `.github/workflows/shellcheck.yml`. The
#                repo's `.shellcheckrc` has `enable=all` which raises
#                style-tier checks (SC2250 brace-wrap, SC2248 quote-vars,
#                SC2312 mask-return-in-echo) to errors — those bit the
#                Wk2 Next05 wk2_next05_final_verification.sh commit at
#                80914efcc and required a follow-up `# shellcheck disable=`
#                directive commit (9550d9101). The local mirror lives in
#                run_shellcheck_on_changed_files() below.
#   - rector dry-run (via the dev-easy openemr container) on changed
#                .php files. The pre-commit `rector` hook requires
#                composer on PATH, which Git-Bash-on-Windows hosts
#                don't have — so the SKIP set normally lists `rector`
#                and the hook is silently skipped pre-push. The
#                container-based mirror in run_rector_on_changed_files()
#                runs file-scoped (full-repo dry-run times out at 300s)
#                and catches the common modernizations Rector wants on
#                new PHP: ClosureToArrowFunctionRector + StrContainsRector.
#                Those bit the Wk2 Next05 lab_trends Phase 7.1 commit at
#                8a5298e3c and required a follow-up `99a4f0ea6` fix.
#   - phpstan level-10 (via the dev-easy openemr container) on changed
#                .php files. Same root cause as the rector skip: pre-commit
#                phpstan hook needs composer on PATH which Git-Bash-on-Windows
#                lacks, so phpstan was silently skipped pre-push and CI
#                caught regressions only AFTER push. This was the Wk2 Next05
#                Phase 7.1 trap: PHPStan was red on master across THREE
#                adjacent commits (8a5298e3c → 99a4f0ea6 → 616dcaedc) and
#                required two follow-up fix commits (f3f6c1779 + f481f8ce7)
#                to land. The container-based mirror in
#                run_phpstan_on_changed_files() catches the level-10
#                violations BEFORE push (only when --include-phpstan is set
#                or when .php files are in the change set — same auto-
#                detection as the pre-commit hook side). Recurring traps it
#                catches:
#                 * Closure-by-reference call-site type erasure (use an
#                   anonymous class for helpers that mutate a typed list).
#                 * `is_array()` / `is_string()` on already-narrowed values
#                   from typed PHPDoc returns (e.g. QueryUtils::fetchRecords).
#                 * Custom rule `openemr.noGlobalNsFunctions` (module files
#                   cannot declare global-namespace functions; use closures
#                   or class methods).
#
# Skips (auto-detected):
#   - The "phpstan" hook is the slowest by ~10x; the script invokes it only
#     when --include-phpstan is also passed, OR when the changed files
#     include any *.php under interface/, src/, library/, or modules/.
#   - The shellcheck step is skipped silently when no .sh files are
#     changed OR when Docker is not on PATH. Pass --skip-shellcheck to
#     force-skip even when .sh files are changed (useful for non-docker
#     hosts).
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
include_shellcheck="auto"
include_rector="auto"
for arg in "$@"; do
    case "${arg}" in
        --staged-only)    mode="staged"  ;;
        --all-files)      mode="all"     ;;
        --include-phpstan) include_phpstan="yes" ;;
        --skip-phpstan)   include_phpstan="no"  ;;
        --skip-shellcheck) include_shellcheck="no" ;;
        --skip-rector)    include_rector="no" ;;
        -h|--help)
            sed -n '2,70p' "${BASH_SOURCE[0]}" | sed 's/^# //'
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
    *)
        # Defensive: argument parsing should have rejected unknown modes.
        echo "ERROR: unknown mode: ${mode}" >&2
        exit 2
        ;;
esac

if [[ -z "${FILES}" ]]; then
    echo ">>> no changed/staged files. nothing to check."
    exit 0
fi

echo ">>> checking the following files (mode=${mode}):"
# SC2001: parameter expansion can replace each ^ with "    " inline. The
# `${var//pat/repl}` form does the same job sed used to.
echo "${FILES//^/    }" | awk '{ print "    " $0 }'

# ---------------------------------------------------------------------------
# ShellCheck on changed .sh files — mirrors .github/workflows/shellcheck.yml.
# Catches SC2250 (brace-wrap), SC2248 (quote-vars), SC2312 (mask-return), and
# the dozens of other style-tier rules raised to errors by the repo's
# `.shellcheckrc` (`enable=all`). This bit commit 80914efcc and required a
# follow-up disable-directive commit 9550d9101 — running shellcheck pre-push
# avoids the round-trip.
# ---------------------------------------------------------------------------
run_shellcheck_on_changed_files() {
    local sh_files
    # FILES may have newlines; pipe through grep to filter .sh and .source
    # (the workflow paths list), then drop deleted files.
    sh_files=$(echo "${FILES}" | grep -E '\.(sh|source)$' || true)
    if [[ -z "${sh_files}" ]]; then
        return 0
    fi

    # Filter out files that no longer exist (covers `git mv` / deletion).
    local existing_sh_files=""
    while IFS= read -r f; do
        [[ -z "${f}" ]] && continue
        [[ -f "${f}" ]] || continue
        existing_sh_files+="${f}"$'\n'
    done <<< "${sh_files}"

    if [[ -z "${existing_sh_files}" ]]; then
        echo ">>> changed .sh files were deleted; nothing for shellcheck."
        return 0
    fi

    if ! command -v docker >/dev/null 2>&1; then
        echo ">>> Docker not on PATH; skipping shellcheck (pass --skip-shellcheck to silence)" >&2
        echo ">>> WARNING: CI may still reject the push on ShellCheck. To run locally:" >&2
        echo ">>>   docker run --rm -v \"\$(pwd):/mnt\" -w /mnt koalaman/shellcheck:stable \\" >&2
        echo ">>>     --check-sourced --external-sources <files...>" >&2
        return 0
    fi

    echo ">>> running shellcheck (via Docker) on changed .sh files:"
    local files_args
    files_args=$(echo "${existing_sh_files}" | tr '\n' ' ')
    echo "    ${files_args}"

    # Match the CI invocation: --check-sourced --external-sources
    # The .shellcheckrc in repo root enables all checks; the container picks it up.
    local pwd_for_docker
    if command -v cygpath >/dev/null 2>&1; then
        pwd_for_docker=$(cygpath -w "${REPO_ROOT}")
    else
        pwd_for_docker="${REPO_ROOT}"
    fi
    # files_args is intentionally space-separated for the docker invocation.
    # The linter would otherwise warn SC2086 on the unquoted expansion below.
    # shellcheck disable=SC2086
    MSYS_NO_PATHCONV=1 docker run --rm \
        -v "${pwd_for_docker}:/mnt" \
        -w /mnt \
        koalaman/shellcheck:stable \
        --check-sourced --external-sources ${files_args}
}

if [[ "${include_shellcheck}" != "no" ]]; then
    # `set -e` would terminate the script if shellcheck returns non-zero,
    # bypassing our messaging. Run inside an `if !` block so we capture the
    # exit code, print the recovery hint, and exit with shellcheck's code.
    # SC2310 fires here because set-e is disabled inside the if-condition;
    # that's exactly what we want.
    # shellcheck disable=SC2310
    if ! run_shellcheck_on_changed_files; then
        sc_rc=$?
        echo ">>> shellcheck reported issues. Fix the warnings or add a '# shellcheck disable=SCNNNN' directive."
        echo ">>> See scripts/run_eval_gate.sh + scripts/wk2_next05_final_verification.sh for the disable-directive pattern."
        exit "${sc_rc}"
    fi
fi

# ---------------------------------------------------------------------------
# Rector dry-run on changed .php files — mirrors .github/workflows for
# Rector PHP Analysis. The local pre-commit `rector` hook requires
# composer on PATH (Git-Bash-on-Windows hosts don't have it); the
# container-based mirror runs file-scoped via the dev-easy openemr
# container, which has composer pre-installed.
# ---------------------------------------------------------------------------
run_rector_on_changed_files() {
    local php_files
    php_files=$(echo "${FILES}" | grep -E '\.php$' || true)
    if [[ -z "${php_files}" ]]; then
        return 0
    fi

    # Drop deleted files.
    local existing_php_files=""
    while IFS= read -r f; do
        [[ -z "${f}" ]] && continue
        [[ -f "${f}" ]] || continue
        existing_php_files+="${f} "
    done <<< "${php_files}"
    existing_php_files="${existing_php_files% }"

    if [[ -z "${existing_php_files}" ]]; then
        return 0
    fi

    if ! command -v docker >/dev/null 2>&1; then
        echo ">>> Docker not on PATH; skipping rector dry-run (pass --skip-rector to silence)" >&2
        return 0
    fi

    # NB: keep the path RELATIVE to REPO_ROOT (we're cd'd there at the top of
    # the script). MSYS_NO_PATHCONV=1 blocks the /c/Users → C:\Users translation
    # that Git-Bash usually applies, so an absolute `/c/Users/...` path handed
    # to Docker-on-Windows would be interpreted as a literal `C:\c\Users\...`
    # (the rector step was silently bug-skipping for exactly this reason on
    # 99a4f0ea — the regression got through pre-push because the container
    # check kept returning "not running" even when it was up).
    local compose_file="docker/development-easy/docker-compose.yml"
    if [[ ! -f "${compose_file}" ]]; then
        echo ">>> dev-easy compose file not found at ${compose_file}; skipping rector dry-run" >&2
        return 0
    fi

    # Check the openemr container is up before exec-ing into it.
    if ! MSYS_NO_PATHCONV=1 docker compose -f "${compose_file}" ps openemr 2>/dev/null | grep -q 'Up\|running'; then
        echo ">>> dev-easy openemr container not running; skipping rector dry-run" >&2
        echo ">>>   (start with: cd docker/development-easy && docker compose up --detach --wait)" >&2
        return 0
    fi

    echo ">>> running rector --dry-run (via dev-easy container) on changed .php files:"
    echo "    ${existing_php_files}"

    # The container's user UID typically does not match the host bind-mount
    # owner — git refuses to operate on the repo without the safe.directory
    # opt-in. Re-add the safe.directory each time (idempotent).
    # shellcheck disable=SC2086
    MSYS_NO_PATHCONV=1 docker compose -f "${compose_file}" exec -T openemr bash -c "
        cd /var/www/localhost/htdocs/openemr &&
        git config --global --add safe.directory /var/www/localhost/htdocs/openemr &&
        php -d memory_limit=4g ./vendor/bin/rector process --dry-run ${existing_php_files}
    "
}

if [[ "${include_rector}" != "no" ]]; then
    # Same `if !` pattern as the shellcheck step.
    # shellcheck disable=SC2310
    if ! run_rector_on_changed_files; then
        rector_rc=$?
        echo ">>> rector reported changes it would make. Either apply them"
        echo ">>>   ('composer rector-fix' in the container, or run the same command without --dry-run)"
        echo ">>>   or rewrite the affected lines manually to match modern PHP 8.x idioms."
        echo ">>> Common auto-modernizations on new code: ClosureToArrowFunctionRector + StrContainsRector."
        exit "${rector_rc}"
    fi
fi

# ---------------------------------------------------------------------------
# PHPStan on changed .php files — mirrors `.github/workflows/phpstan.yml`.
# Catches the level-10 violations the pre-commit `phpstan` hook would
# normally cover, except the pre-commit hook needs composer on PATH which
# Git-Bash-on-Windows hosts don't have. The container-based mirror is the
# load-bearing prevention against the same kind of post-push CI rejection
# the Wk2 Next05 Phase 7.1 commits hit at 8a5298e3c / 99a4f0ea6 / 616dcaedc
# (PHPStan went red on master across three adjacent commits before being
# fixed by f3f6c1779 + f481f8ce7).
# ---------------------------------------------------------------------------
run_phpstan_on_changed_files() {
    local php_files
    php_files=$(echo "${FILES}" | grep -E '\.php$' || true)
    if [[ -z "${php_files}" ]]; then
        return 0
    fi

    # Drop deleted files.
    local existing_php_files=""
    while IFS= read -r f; do
        [[ -z "${f}" ]] && continue
        [[ -f "${f}" ]] || continue
        existing_php_files+="${f} "
    done <<< "${php_files}"
    existing_php_files="${existing_php_files% }"

    if [[ -z "${existing_php_files}" ]]; then
        return 0
    fi

    if ! command -v docker >/dev/null 2>&1; then
        echo ">>> Docker not on PATH; skipping container PHPStan (pass --skip-phpstan to silence)" >&2
        echo ">>> WARNING: CI may reject the push on PHPStan. Local invocation is:" >&2
        echo ">>>   docker compose -f docker/development-easy/docker-compose.yml \\" >&2
        echo ">>>     exec -T openemr bash -c 'cd /var/www/localhost/htdocs/openemr && \\" >&2
        echo ">>>     git config --global --add safe.directory \\" >&2
        echo ">>>     /var/www/localhost/htdocs/openemr && \\" >&2
        echo ">>>     php -d memory_limit=4g ./vendor/bin/phpstan analyze \\" >&2
        echo ">>>     <files> --level=10 --no-progress'" >&2
        return 0
    fi

    # NB: keep the path RELATIVE to REPO_ROOT (we're cd'd there at the top of
    # the script). MSYS_NO_PATHCONV=1 blocks the /c/Users → C:\Users translation
    # that Git-Bash usually applies, so an absolute `/c/Users/...` path handed
    # to Docker-on-Windows would be interpreted as a literal `C:\c\Users\...`
    # (the rector step was silently bug-skipping for exactly this reason on
    # 99a4f0ea — the regression got through pre-push because the container
    # check kept returning "not running" even when it was up).
    local compose_file="docker/development-easy/docker-compose.yml"
    if [[ ! -f "${compose_file}" ]]; then
        echo ">>> dev-easy compose file not found at ${compose_file}; skipping PHPStan" >&2
        return 0
    fi

    if ! MSYS_NO_PATHCONV=1 docker compose -f "${compose_file}" ps openemr 2>/dev/null | grep -q 'Up\|running'; then
        echo ">>> dev-easy openemr container not running; skipping PHPStan" >&2
        echo ">>>   (start with: cd docker/development-easy && docker compose up --detach --wait)" >&2
        return 0
    fi

    echo ">>> running PHPStan --level=10 (via dev-easy container) on changed .php files:"
    echo "    ${existing_php_files}"

    # Container's bind-mounted repo needs safe.directory each time
    # (UID mismatch). PHPStan's neon.dist defaults to level=max — we pass
    # --level=10 explicitly so the invocation is symmetric with what CI
    # would emit and so the level can't silently drift if the neon is
    # later edited.
    # shellcheck disable=SC2086
    MSYS_NO_PATHCONV=1 docker compose -f "${compose_file}" exec -T openemr bash -c "
        cd /var/www/localhost/htdocs/openemr &&
        git config --global --add safe.directory /var/www/localhost/htdocs/openemr &&
        php -d memory_limit=4g ./vendor/bin/phpstan analyze ${existing_php_files} --level=10 --no-progress
    "
}

if [[ "${include_phpstan}" == "auto" ]]; then
    if echo "${FILES}" | grep -qE '\.(php)$'; then
        include_phpstan="yes"
    else
        include_phpstan="no"
    fi
fi
if [[ "${include_phpstan}" != "no" ]]; then
    # shellcheck disable=SC2310
    if ! run_phpstan_on_changed_files; then
        phpstan_rc=$?
        echo ">>> PHPStan reported errors. Fix them BEFORE pushing — phpstan-level-10"
        echo ">>>   has been red on master multiple times during Wk2 Next05 because"
        echo ">>>   the pre-commit phpstan hook silently skipped on hosts without"
        echo ">>>   composer. Common patterns and fixes:"
        echo ">>>     * Closure-by-reference \$failures erases the type at call sites:"
        echo ">>>       use an anonymous class with typed property instead."
        echo ">>>     * is_array(\$x) / is_string(\$x) where the PHPDoc already narrows:"
        echo ">>>       drop the dead guard."
        echo ">>>     * Global-namespace functions in module files:"
        echo ">>>       openemr.noGlobalNsFunctions — use closures or class methods."
        exit "${phpstan_rc}"
    fi
fi

# The pre-commit phpstan, rector, phpcbf, phpcs, and
# composer-require-checker hooks all shell out to `composer` (which the
# host often lacks). The container-based mirrors above are the
# load-bearing checks; tell pre-commit to skip its own composer-dependent
# hooks so we don't get noisy "Executable `composer` not found" failures
# that drown out the real results.
export SKIP="${SKIP:-}${SKIP:+,}phpstan,rector,phpcbf,phpcs,composer-require-checker,composer-validate,composer-normalize,php-syntax-check"

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
exit "${rc}"
