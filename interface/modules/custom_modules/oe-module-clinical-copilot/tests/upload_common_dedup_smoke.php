<?php

/**
 * CLI smoke test for upload_common.php's SHA dedup helpers
 * (Plan_wk2_Claude_Next05 §2.6 smoke #3, AgDR-0071 + AgDR-0063).
 *
 * Verifies:
 *   1. copilot_upload_lookup_existing_document returns null when no
 *      sha_index row exists for (patient_id, sha256).
 *   2. After copilot_upload_record_sha inserts an index row pointing
 *      at a NON-EXISTENT document_id, lookup returns null (the
 *      orphan-row branch in the helper). This is the defense-in-depth
 *      behavior the inline comment describes.
 *   3. Re-calling copilot_upload_record_sha with identical params is
 *      a silent no-op (INSERT IGNORE on the unique (patient_id, sha256)
 *      key); the sha_index ends up with exactly 1 row for the pair.
 *
 * The full lookup-returns-uuid happy path requires inserting a real
 * documents row, which has FK constraints and isn't worth setting up
 * in a smoke. Phase 5.1's 21-step Docker verification exercises that
 * path end-to-end via the actual upload endpoint. This smoke covers
 * the helpers' edge cases that the integration path can't easily hit.
 *
 * Skip-gracefully: if `copilot_document_sha_index` is missing the
 * smoke prints SKIP and exits 0.
 *
 * Usage from the openemr container:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/upload_common_dedup_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/upload_common_dedup_smoke.php --json
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

$ignoreAuth = true;
$sessionAllowWrite = true;
$_GET['site'] = $_GET['site'] ?? 'default';
$_SERVER['HTTP_HOST'] = $_SERVER['HTTP_HOST'] ?? 'default';

$openemrRoot = realpath(__DIR__ . '/../../../../..');
if ($openemrRoot === false) {
    fwrite(STDERR, "Could not resolve OpenEMR root.\n");
    exit(2);
}

require_once $openemrRoot . '/interface/globals.php';
require_once __DIR__ . '/../public/api/upload_common.php';

use OpenEMR\Common\Database\QueryUtils;
use function OpenEMR\Modules\ClinicalCopilot\Api\Internal\copilot_upload_lookup_existing_document;
use function OpenEMR\Modules\ClinicalCopilot\Api\Internal\copilot_upload_record_sha;

$json = false;
$cliArgs = $argv ?? [];
foreach (array_slice($cliArgs, 1) as $arg) {
    if ($arg === '--json') {
        $json = true;
    }
}

/** @var array<string, array<string, mixed>> $report */
$report = [];
$failures = 0;

/**
 * Narrow a phpstan-`mixed` QueryUtils::fetchSingleValue result to int per
 * AgDR-0082's "narrow before cast" discipline.
 */
function _dedup_smoke_int(mixed $raw): int
{
    return is_numeric($raw) ? (int) $raw : 0;
}

// ----------------------------------------------------------------------
// Prereq: does the sha_index table exist?
// ----------------------------------------------------------------------
$tableExists = false;
try {
    $row = QueryUtils::fetchSingleValue(
        "SELECT 1 AS present FROM information_schema.tables "
        . "WHERE table_schema = DATABASE() AND table_name = 'copilot_document_sha_index' LIMIT 1",
        'present',
        [],
    );
    $tableExists = $row !== null && $row !== false;
} catch (\RuntimeException | \PDOException) {
    $tableExists = false;
}

if (!$tableExists) {
    $report['test_1_lookup_miss'] = ['skip' => 'copilot_document_sha_index table missing'];
    $report['test_2_orphan_row_returns_null'] = ['skip' => 'copilot_document_sha_index table missing'];
    $report['test_3_record_sha_idempotent'] = ['skip' => 'copilot_document_sha_index table missing'];
    if ($json) {
        echo json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    } else {
        echo "upload_common dedup smoke: SKIPPED (3/3 tests) — copilot_document_sha_index table missing.\n";
    }
    exit(0);
}

// ----------------------------------------------------------------------
// Test fixtures — synthetic patient_id (very high value so it cannot
// collide with a real OpenEMR pid; the column is BIGINT UNSIGNED so
// negatives are not allowed) and a bogus document_id that does not
// exist in the documents table. SHA is a known string we can pre-clean.
// ----------------------------------------------------------------------
$testPid = 9999990001;
$testSha = str_repeat('b', 64);
$bogusDocumentId = '999999999';

// Cleanup any stale rows from a prior smoke run.
try {
    QueryUtils::sqlStatementThrowException(
        'DELETE FROM `copilot_document_sha_index` WHERE `patient_id` = ?',
        [$testPid],
    );
} catch (\RuntimeException) {
    // Best-effort; continue.
}

// ----------------------------------------------------------------------
// Test 1 — lookup returns null when no row exists for (pid, sha).
// ----------------------------------------------------------------------
try {
    $missResult = copilot_upload_lookup_existing_document($testPid, $testSha);
    $test1Pass = $missResult === null;
    $report['test_1_lookup_miss'] = [
        'pass' => $test1Pass,
        'result' => $missResult === null ? 'null' : 'non-null',
    ];
    if (!$test1Pass) {
        $failures++;
    }
} catch (\RuntimeException | \PDOException $exc) {
    $report['test_1_lookup_miss'] = ['fail' => 'exception', 'message' => $exc->getMessage()];
    $failures++;
}

// ----------------------------------------------------------------------
// Test 2 — insert an sha_index row pointing at a NON-EXISTENT
//          document_id and verify lookup returns null (the orphan
//          branch in copilot_upload_lookup_existing_document).
// ----------------------------------------------------------------------
try {
    copilot_upload_record_sha($testPid, $testSha, $bogusDocumentId);

    // Confirm the sha_index row landed.
    $indexCount = QueryUtils::fetchSingleValue(
        'SELECT COUNT(*) AS c FROM `copilot_document_sha_index` WHERE `patient_id` = ? AND `sha256` = ?',
        'c',
        [$testPid, $testSha],
    );

    // Lookup should still return null because documents.id=999999999 doesn't exist.
    $orphanLookup = copilot_upload_lookup_existing_document($testPid, $testSha);

    $test2Pass = (_dedup_smoke_int($indexCount) === 1) && ($orphanLookup === null);
    $report['test_2_orphan_row_returns_null'] = [
        'pass' => $test2Pass,
        'index_count' => _dedup_smoke_int($indexCount),
        'lookup_result' => $orphanLookup === null ? 'null (orphan branch)' : 'non-null (BUG)',
    ];
    if (!$test2Pass) {
        $failures++;
    }
} catch (\RuntimeException | \PDOException $exc) {
    $report['test_2_orphan_row_returns_null'] = ['fail' => 'exception', 'message' => $exc->getMessage()];
    $failures++;
}

// ----------------------------------------------------------------------
// Test 3 — re-call record_sha with the SAME (pid, sha, document_id)
//          and verify INSERT IGNORE absorbs the duplicate; the sha_index
//          still has exactly 1 row for the pair.
// ----------------------------------------------------------------------
try {
    copilot_upload_record_sha($testPid, $testSha, $bogusDocumentId);
    $indexCountAfterDup = QueryUtils::fetchSingleValue(
        'SELECT COUNT(*) AS c FROM `copilot_document_sha_index` WHERE `patient_id` = ? AND `sha256` = ?',
        'c',
        [$testPid, $testSha],
    );
    $test3Pass = _dedup_smoke_int($indexCountAfterDup) === 1;
    $report['test_3_record_sha_idempotent'] = [
        'pass' => $test3Pass,
        'index_count' => _dedup_smoke_int($indexCountAfterDup),
    ];
    if (!$test3Pass) {
        $failures++;
    }
} catch (\RuntimeException | \PDOException $exc) {
    $report['test_3_record_sha_idempotent'] = ['fail' => 'exception', 'message' => $exc->getMessage()];
    $failures++;
}

// ----------------------------------------------------------------------
// Cleanup
// ----------------------------------------------------------------------
try {
    QueryUtils::sqlStatementThrowException(
        'DELETE FROM `copilot_document_sha_index` WHERE `patient_id` = ?',
        [$testPid],
    );
} catch (\RuntimeException $exc) {
    if (!$json) {
        fwrite(
            STDERR,
            "WARNING: smoke cleanup DELETE failed: " . $exc->getMessage() . "\n"
            . "Manual cleanup: DELETE FROM copilot_document_sha_index WHERE patient_id = {$testPid};\n"
        );
    }
}

// ----------------------------------------------------------------------
// Report
// ----------------------------------------------------------------------
if ($json) {
    echo json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
} else {
    foreach ($report as $name => $row) {
        /** @var array<string, mixed> $row */
        if (array_key_exists('skip', $row)) {
            $skip = $row['skip'];
            echo "[SKIP] {$name}: " . (is_string($skip) ? $skip : '') . "\n";
            continue;
        }
        $passVal = $row['pass'] ?? false;
        $status = ($passVal === true) ? 'PASS' : 'FAIL';
        echo "[{$status}] {$name}";
        if (array_key_exists('index_count', $row)) {
            $ic = $row['index_count'];
            echo " (index_count=" . (is_scalar($ic) ? (string) $ic : '?');
            if (array_key_exists('lookup_result', $row)) {
                $lr = $row['lookup_result'];
                echo ", lookup=" . (is_string($lr) ? $lr : '?');
            }
            echo ")";
        } elseif (array_key_exists('result', $row)) {
            $r = $row['result'];
            echo " (result=" . (is_string($r) ? $r : '?') . ")";
        } elseif (array_key_exists('fail', $row)) {
            $fail = $row['fail'];
            $msg = $row['message'] ?? '';
            echo " — " . (is_string($fail) ? $fail : '?') . ": "
                . (is_string($msg) ? $msg : '');
        }
        echo "\n";
    }
    echo $failures === 0 ? "upload_common dedup smoke: ALL PASSED\n" : "upload_common dedup smoke: {$failures} FAILED\n";
}

exit($failures === 0 ? 0 : 1);
