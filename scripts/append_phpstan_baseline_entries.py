#!/usr/bin/env python3
"""Append PHPStan baseline entries from a raw phpstan output file.

**LAST-RESORT TOOL.** The OpenEMR project standard is to FIX phpstan errors at
the source, not baseline them (`.phpstan/fatal-baseline-caps.php` actively
enforces this for fatal categories). Only use this script when:

  1. You have agent-leader / owner authorization to defer a fix.
  2. You have opened an AgDR documenting the deferral and the planned
     follow-up that drives the new entries back down.
  3. The errors are in NON-CAPPED baseline files (see CAPPED_FILES below).

Usage:
    # In the openemr/ root:
    docker exec development-easy-openemr-1 bash -c "cd /var/www/localhost/htdocs/openemr && \\
        vendor/bin/phpstan analyze --memory-limit=8G --configuration=phpstan.neon.dist \\
        --no-progress --error-format=raw <FILE_PATHS_OR_DIRS>" > phpstan_errors.txt

    python scripts/append_phpstan_baseline_entries.py phpstan_errors.txt

Exits with code 2 (and edits nothing) if any error message:
  - Doesn't match a known baseline file pattern (extend MAPPING below).
  - Maps to a capped fatal-baseline category (those MUST be fixed at source).

Preferred workflow: refactor at the source. Patterns by error type:

  Function X may not be defined in the global namespace
    → wrap helpers in `namespace OpenEMR\\Modules\\X\\Internal;` or convert
      to `final class XHelpers { public static function ...() }`

  Direct access to $_POST / $_SERVER / $_FILES is forbidden
    → use Symfony\\Component\\HttpFoundation\\Request:
        $request = Request::createFromGlobals();
        $csrf = $request->request->get('csrf_token_form');
        $upload = $request->files->get('file');  // UploadedFile

  Direct instantiation of OpenEMR\\Common\\Logging\\SystemLogger discouraged
    → use \\OpenEMR\\BC\\ServiceContainer::getLogger()

  catch (Exception) would suppress ErrorException, which is forbidden
  catch (Throwable) would suppress Error, which is forbidden
    → catch the specific subtype (RuntimeException, JsonException, etc.)
      or split: catch (\\Error) { throw $e; } catch (\\Exception) { ... }

  Cannot cast mixed to int|string|float|bool
    → narrow first: `if (is_int($v)) { $i = $v; }` — do not cast `(int) $mixed`.

  Call to function is_array() / is_string() / method_exists() will always
    evaluate to true → delete the redundant check.

  Offset 'X' on non-empty-array on left side of ?? always exists
    → drop the `?? null`; the offset is provably present.

  Variable $X in isset() always exists and is not nullable
    → drop the isset() and reference $X directly.

  Result of && is always true/false → remove the redundant operand.

  Function X() has parameter $Y with no value type specified in iterable type
    → add `@param array<string, mixed> $Y` (or the precise shape) in the
      PHPDoc, or migrate the function to use a typed DTO.

  Parameter #N $X of function Y expects T, U given
    → narrow U at the call site before passing.

  Method X() should return T but returns U
    → narrow U or change the return type to match reality.

  PHPDoc tag @param has invalid value (...)
    → fix the malformed PHPDoc comment.

  Binary operation '.' between X and mixed results in an error
    → cast or narrow the mixed operand to string first.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE_DIR = REPO / ".phpstan" / "baseline"
PCRE_SPECIAL = set(r"\.()[]{}*+?|^$#<>:")

# Baseline files whose entry counts are capped by FatalBaselineCapsIsolatedTest.
# Adding entries to these is forbidden — fix the code instead.
# Source of truth: .phpstan/fatal-baseline-caps.php
CAPPED_FILES = {
    "class.notFound.php",
    "classConstant.notFound.php",
    "constant.notFound.php",
    "function.notFound.php",
    "include.fileNotFound.php",
    "includeOnce.fileNotFound.php",
    "interface.notFound.php",
    "method.notFound.php",
    "require.fileNotFound.php",
    "requireOnce.fileNotFound.php",
    "return.missing.php",
    "staticMethod.notFound.php",
    "trait.notFound.php",
    "variable.undefined.php",
    "classConstant.nonObject.php",
    "clone.nonObject.php",
    "method.nonObject.php",
    "property.nonObject.php",
    "staticMethod.nonObject.php",
}


def php_pcre_escape(msg: str) -> str:
    out = []
    for c in msg:
        if c in PCRE_SPECIAL:
            out.append("\\" + c)
        else:
            out.append(c)
    pcre = "".join(out)
    pcre = pcre.replace("\\", "\\\\")
    pcre = pcre.replace("'", "\\'")
    return pcre


def baseline_for(msg: str) -> str | None:
    # OpenEMR custom rules (project-specific)
    if "may not be defined in the global namespace" in msg:
        return "openemr.noGlobalNsFunctions.php"
    if "Direct access to $_" in msg:
        return "openemr.forbiddenRequestGlobals.php"
    if "Direct instantiation of" in msg and "is discouraged" in msg:
        return "openemr.forbiddenInstantiation.php"
    if "catch (" in msg and "would suppress" in msg:
        return "openemr.forbiddenCatchType.php"
    # Casts
    if "Cannot cast mixed to int" in msg:
        return "cast.int.php"
    if "Cannot cast mixed to string" in msg:
        return "cast.string.php"
    if "Cannot cast mixed to float" in msg or "Cannot cast mixed to double" in msg:
        return "cast.double.php"
    if "Cannot cast mixed to bool" in msg:
        return "cast.bool.php"
    # Narrowing
    if "will always evaluate to true" in msg or "will always evaluate to false" in msg:
        return "function.alreadyNarrowedType.php"
    # Types
    if "has parameter" in msg and "no value type specified" in msg:
        return "missingType.iterableValue.php"
    if msg.startswith("Parameter #") and "expects" in msg and "given" in msg:
        return "argument.type.php"
    if "should return" in msg and "but returns" in msg:
        return "return.type.php"
    # Always-exists / unreachable
    if "on left side of ??" in msg and "always exists" in msg:
        return "nullCoalesce.offset.php"
    if msg.startswith("Variable ") and "in isset()" in msg and "always exists" in msg:
        return "isset.variable.php"
    if "Result of &&" in msg and "always true" in msg:
        return "booleanAnd.alwaysTrue.php"
    if "Result of &&" in msg and "always false" in msg:
        return "booleanAnd.alwaysFalse.php"
    if "Result of ||" in msg and "always true" in msg:
        return "booleanOr.alwaysTrue.php"
    if "Result of ||" in msg and "always false" in msg:
        return "booleanOr.alwaysFalse.php"
    # PHPDoc
    if "PHPDoc tag @param has invalid value" in msg:
        return "phpDoc.parseError.php"
    if "PHPDoc tag @return has invalid value" in msg:
        return "phpDoc.parseError.php"
    if "PHPDoc tag @var has invalid value" in msg:
        return "phpDoc.parseError.php"
    # Binary
    if "Binary operation" in msg and "results in an error" in msg:
        return "binaryOp.invalid.php"
    return None


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: append_phpstan_baseline_entries.py <phpstan_raw_output_file>", file=sys.stderr)
        sys.exit(1)

    errors: list[tuple[str, str]] = []
    with open(sys.argv[1]) as f:
        for line in f:
            m = re.match(r"^(\S+):\d+:(.*)$", line.rstrip())
            if not m:
                continue
            path, msg = m.groups()
            relpath = path.replace("/var/www/localhost/htdocs/openemr/", "")
            errors.append((relpath, msg.strip()))

    grouped: dict[tuple[str, str, str], int] = defaultdict(int)
    unmatched: list[str] = []
    capped: list[str] = []
    for path, msg in errors:
        bf = baseline_for(msg)
        if bf is None:
            unmatched.append(f"  {path}: {msg}")
        elif bf in CAPPED_FILES:
            capped.append(f"  {path}: {msg}  -> {bf}")
        else:
            grouped[(bf, msg, path)] += 1

    failed = False
    if unmatched:
        print(
            "UNMATCHED ERRORS — extend baseline_for() in this script "
            "to cover these patterns:",
            file=sys.stderr,
        )
        for u in unmatched:
            print(u, file=sys.stderr)
        failed = True

    if capped:
        print(
            "\nCAPPED FATAL ERRORS — these must be FIXED IN CODE, not baselined "
            "(see .phpstan/fatal-baseline-caps.php and CLAUDE.md):",
            file=sys.stderr,
        )
        for c in capped:
            print(c, file=sys.stderr)
        failed = True

    if failed:
        sys.exit(2)

    by_file: dict[str, list[str]] = defaultdict(list)
    for (bf, msg, path), count in grouped.items():
        entry = (
            "$ignoreErrors[] = [\n"
            f"    'message' => '#^{php_pcre_escape(msg)}$#',\n"
            f"    'count' => {count},\n"
            f"    'path' => __DIR__ . '/../../{path}',\n"
            "];\n"
        )
        by_file[bf].append(entry)

    for bf, entries in by_file.items():
        path = BASELINE_DIR / bf
        if not path.exists():
            print(f"WARN: baseline file does not exist: {bf}", file=sys.stderr)
            continue
        content = path.read_text()
        new_block = "\n".join(entries) + "\n"
        marker = "\nreturn ['parameters'"
        if marker not in content:
            print(f"WARN: marker not found in {bf}", file=sys.stderr)
            continue
        new_content = content.replace(marker, "\n" + new_block + marker, 1)
        path.write_text(new_content)
        print(f"  appended {len(entries)} entries to {bf}")


if __name__ == "__main__":
    main()
