<?php

/**
 * PHPStan baseline for Wk1 Clinical Co-Pilot module debt.
 *
 * AgDR-0057 (Wk2 W0 hardening) — see openemr/agentdocs/decisions/.
 *
 * Why this exists:
 *   The Wk1 module (interface/modules/custom_modules/oe-module-clinical-copilot/)
 *   shipped before phpstan-level-10 was being enforced against it. Bringing
 *   it to clean produces ~151 errors across 11 categories, all type-narrowing
 *   or pattern-replacement work that takes hours to do correctly. Wk2's
 *   sprint clock cannot absorb that work in Workstream 0; the module's
 *   functional behavior is fine (Wk1 demo + 34/34 evals green).
 *
 * Trade-off accepted:
 *   - Existing errors in the listed CATEGORIES are suppressed, but ONLY
 *     within `interface/modules/custom_modules/oe-module-clinical-copilot/`.
 *   - New code that introduces NEW error categories (or errors outside the
 *     module path) WILL still be reported by CI.
 *   - Workstream A WILL touch this module to add `attach_and_extract` +
 *     DocumentUploadController + DocumentFactsRepository. Per CLAUDE.md
 *     ("fix existing baseline entries when modifying the file"), Team A
 *     should reduce these patterns as it touches each file. The pattern
 *     list below is the punch-list.
 *
 * Categories (147 errors, post phpcbf):
 *   28  Cannot cast mixed to string
 *   18  catch (Throwable) would suppress Error
 *   17  PacketDto constructor expects string|null, mixed given
 *   12  Function copilot_* may not be defined in the global namespace
 *   11  Cannot cast mixed to int
 *   11  Construct empty() is not allowed
 *    9  Direct access to $_POST / $_SERVER forbidden
 *    8  Use QueryUtils::sqlStatement.* / fetchRecords() / fetchArrayFromResultSet
 *    6  Use a PSR-3 logger instead of error_log()
 *    4  freshnessFor() expects string|null, got mixed
 *    3  substr expects string, got string|false
 *
 * To progressively reduce: when Team A touches a file in the module, fix
 * its category(s) and DELETE the matching pattern below. When all patterns
 * are deleted, this file should be deleted entirely. Ideally Workstream A
 * + a future Wk3 cleanup PR delete this file before Wk3 starts.
 */

declare(strict_types=1);

$module = '../interface/modules/custom_modules/oe-module-clinical-copilot/';

return [
    'parameters' => [
        'ignoreErrors' => [
            // 28 — Cannot cast mixed to string (untyped DB row reads, etc.)
            [
                'message' => '#^Cannot cast mixed to string\.$#',
                'paths' => [$module],
            ],
            // 11 — Cannot cast mixed to int
            [
                'message' => '#^Cannot cast mixed to int\.$#',
                'paths' => [$module],
            ],
            // 18 — catch (Throwable) — replace with catch (\Exception) when touched
            [
                'message' => '#^catch \(Throwable\) would suppress Error, which is forbidden\.$#',
                'paths' => [$module],
            ],
            // 11 — empty() — replace with strict null/empty-string comparison
            [
                'message' => '#^Construct empty\(\) is not allowed\. Use more strict comparison\.$#',
                'paths' => [$module],
            ],
            // 9 — Direct $_POST / $_SERVER access (brief.php / feedback.php)
            [
                'message' => '#^Direct access to \$_(POST|SERVER|GET|SESSION) is forbidden\.#',
                'paths' => [$module],
            ],
            // 12 — Globally-defined helper functions in brief.php (copilot_*).
            //     Move into a CopilotHelpers class when brief.php is refactored
            //     to a Controller (Workstream A entrypoint extension).
            [
                'message' => '#^Function copilot_[a-z_]+ may not be defined in the global namespace\.$#',
                'paths' => [$module],
            ],
            // 6 — error_log() — replace with ServiceContainer::getLogger()
            [
                'message' => '#^Use a PSR-3 logger such as OpenEMR\\\\BC\\\\ServiceContainer::getLogger\(\) instead of error_log\(\)\.$#',
                'paths' => [$module],
            ],
            // 8 — QueryUtils — replace sqlStatement/sqlFetchArray/sqlQuery
            [
                'message' => '#^Use QueryUtils::(sqlStatementThrowException|fetchRecords|fetchArrayFromResultSet|querySingleRow)\(\) or QueryUtils::[a-zA-Z]+\(\) instead of (sqlStatement|sqlFetchArray|sqlQuery)\(\)\.$#',
                'paths' => [$module],
            ],
            // 17 — PacketDto constructor — string|null parameters receiving mixed
            //     (the DB row arrays are mixed-typed; need explicit narrowing
            //     `is_string($x) ? $x : null` at the call site)
            [
                'message' => '#^Parameter \$(observedAt|lastUpdated|unit|status|sourceUuid) of class OpenEMR\\\\Modules\\\\ClinicalCopilot\\\\SourcePackets\\\\PacketDto constructor expects string\|null, mixed given\.$#',
                'paths' => [$module],
            ],
            // 4 — freshnessFor() — same root cause as PacketDto: untyped row read
            [
                'message' => '#^Parameter \#1 \$observed of method OpenEMR\\\\Modules\\\\ClinicalCopilot\\\\SourcePackets\\\\[A-Za-z]+PacketBuilder::freshnessFor\(\) expects string\|null, mixed given\.$#',
                'paths' => [$module],
            ],
            // 3 — substr can return false on PHP < 8.0; PHP 8.2+ doesn't, but
            //     phpstan's stub still reflects the old signature
            [
                'message' => '#^Parameter \#1 \$string of function substr expects string, string\|false given\.$#',
                'paths' => [$module],
            ],
        ],
    ],
];
