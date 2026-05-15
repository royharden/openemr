<?php

/**
 * CLI smoke test for DocumentFactsRepository::persistExtractedDocument
 * idempotency (Plan_wk2_Claude_Next05 §2.6 smoke #4, AgDR-0071).
 *
 * Verifies:
 *   1. First call with a fresh idempotency_key inserts 1 row. The DB
 *      ends up with exactly 1 row for the idempotency_key, and
 *      persistExtractedDocument's return value is >0 (the new row's
 *      auto-increment id — note: NOT an affected-row count; the
 *      method returns the LAST_INSERT_ID through QueryUtils::sqlInsert,
 *      which is positive on successful insert and 0 on INSERT IGNORE
 *      duplicate).
 *   2. Second call with the IDENTICAL payload (same patient_uuid +
 *      document_sha256 + field_path) returns 0 (the INSERT IGNORE
 *      silently absorbs the duplicate), and the DB still has exactly
 *      1 row for the key.
 *   3. A third call with the SAME patient_uuid + document_sha256 but
 *      a DIFFERENT field_path inserts 1 new row (the idempotency key
 *      is per-fact, not per-document). Return value is >0 (a different
 *      auto-increment id from the first insert).
 *   4. `field_value_json.collection_date` survives persistence so
 *      LabResultWriter and lab_trends.php can use the clinical collection
 *      date instead of the upload/extraction timestamp.
 *
 * Skip-gracefully: if the `copilot_document_facts` table is missing
 * (migration not applied) or QueryUtils cannot reach the DB at all,
 * the smoke prints SKIP and exits 0. Run inside the openemr container
 * after `2026_05_09_copilot_document_facts.sql` is applied.
 *
 * Usage from the openemr container:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/document_facts_repository_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/document_facts_repository_smoke.php --json
 *
 * The test uses synthetic UUIDs (all-zero patient_uuid, all-zero
 * documents.uuid binary) so it never collides with a real patient's
 * facts. It cleans up its own rows at the end via DELETE on the three
 * idempotency_keys it created.
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
require_once __DIR__ . '/../src/Repository/DocumentFactsRepository.php';

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Modules\ClinicalCopilot\Repository\DocumentFactsRepository;

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

// AgDR-0082 narrow-before-cast helper for QueryUtils::fetchSingleValue's
// `mixed` return. Closure (not a top-level function) so the project's
// "no functions in global namespace" phpstan rule doesn't fire.
$smokeInt = static fn(mixed $raw): int => is_numeric($raw) ? (int) $raw : 0;

// ----------------------------------------------------------------------
// Prereq: does the table exist? If not, SKIP all three tests.
// ----------------------------------------------------------------------
$tableExists = false;
try {
    $row = QueryUtils::fetchSingleValue(
        "SELECT 1 AS present FROM information_schema.tables "
        . "WHERE table_schema = DATABASE() AND table_name = 'copilot_document_facts' LIMIT 1",
        'present',
        [],
    );
    $tableExists = $row !== null && $row !== false;
} catch (\RuntimeException | \PDOException $exc) {
    // Treat as "table not available" — skip the integration tests.
    $tableExists = false;
}

if (!$tableExists) {
    $report['test_1_first_insert'] = ['skip' => 'copilot_document_facts table missing'];
    $report['test_2_idempotent_reinsert'] = ['skip' => 'copilot_document_facts table missing'];
    $report['test_3_new_fieldpath_inserts'] = ['skip' => 'copilot_document_facts table missing'];
    $report['test_4_collection_date_persisted'] = ['skip' => 'copilot_document_facts table missing'];
    if ($json) {
        echo json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    } else {
        echo "DocumentFactsRepository smoke: SKIPPED (4/4 tests) — copilot_document_facts table missing.\n";
    }
    exit(0);
}

// ----------------------------------------------------------------------
// Test fixture — synthetic UUIDs so we never touch a real patient's
// facts. Patient_uuid is the dashed string form; documents.uuid in the
// DB is the binary 16-byte form, so we pass a literal 16 \x00 bytes.
// ----------------------------------------------------------------------
$testPatientUuid = '00000000-0000-4000-8000-deadbeef0001';
$testDocumentUuidBin = str_repeat("\x00", 16);
$testDocSha256 = str_repeat('a', 64);
$testFieldPath1 = 'wk2_next05_smoke.field_one';
$testFieldPath2 = 'wk2_next05_smoke.field_two';

// Compute the three idempotency keys we expect to land in the table.
$idempotencyKey1 = hash('sha256', $testPatientUuid . $testDocSha256 . $testFieldPath1);
$idempotencyKey2 = hash('sha256', $testPatientUuid . $testDocSha256 . $testFieldPath2);

// Clean up any stale test rows from a prior smoke run before we start.
try {
    QueryUtils::sqlStatementThrowException(
        'DELETE FROM `copilot_document_facts` WHERE `idempotency_key` IN (?, ?)',
        [$idempotencyKey1, $idempotencyKey2],
    );
} catch (\RuntimeException $exc) {
    // Pre-cleanup is best-effort; the test will surface any real issue.
}

$logger = ServiceContainer::getLogger();
$repository = new DocumentFactsRepository($logger);

/**
 * Build a payload with a single field whose name matches $fieldPath.
 *
 * @return array<string, mixed>
 */
$buildPayload = static fn(string $fieldPath): array => [
    'document_sha256' => $testDocSha256,
    'doc_type' => 'intake_form',
    'result' => [
        'extracted_by_model' => 'wk2-smoke-mock',
        'extracted_at' => '2026-05-11 12:00:00',
        'fields' => [
            [
                'name' => $fieldPath,
                'value' => 'smoke-value',
                'collection_date' => '2025-07-18',
                'citation' => [
                    'page_index' => 0,
                    'quote_or_value' => 'smoke-quote',
                    'confidence' => 0.99,
                ],
            ],
        ],
    ],
];

// ----------------------------------------------------------------------
// Test 1 — first insert: expect 1 row affected, exactly 1 row in DB.
// ----------------------------------------------------------------------
try {
    $insertedFirst = $repository->persistExtractedDocument(
        $buildPayload($testFieldPath1),
        $testPatientUuid,
        $testDocumentUuidBin,
        '0',
    );
    $countAfterFirst = QueryUtils::fetchSingleValue(
        'SELECT COUNT(*) AS c FROM `copilot_document_facts` WHERE `idempotency_key` = ?',
        'c',
        [$idempotencyKey1],
    );
    $test1Pass = ($insertedFirst > 0) && ($smokeInt($countAfterFirst) === 1);
    $report['test_1_first_insert'] = [
        'pass' => $test1Pass,
        'last_insert_id' => $insertedFirst,
        'db_count' => $smokeInt($countAfterFirst),
    ];
    if (!$test1Pass) {
        $failures++;
    }
} catch (\RuntimeException | \PDOException $exc) {
    $report['test_1_first_insert'] = ['fail' => 'exception', 'message' => $exc->getMessage()];
    $failures++;
}

// ----------------------------------------------------------------------
// Test 2 — re-insert identical payload: expect 0 rows affected, DB
//          count for the idempotency_key stays at 1.
// ----------------------------------------------------------------------
try {
    $insertedSecond = $repository->persistExtractedDocument(
        $buildPayload($testFieldPath1),
        $testPatientUuid,
        $testDocumentUuidBin,
        '0',
    );
    $countAfterSecond = QueryUtils::fetchSingleValue(
        'SELECT COUNT(*) AS c FROM `copilot_document_facts` WHERE `idempotency_key` = ?',
        'c',
        [$idempotencyKey1],
    );
    $test2Pass = ($insertedSecond === 0) && ($smokeInt($countAfterSecond) === 1);
    $report['test_2_idempotent_reinsert'] = [
        'pass' => $test2Pass,
        'last_insert_id' => $insertedSecond,
        'db_count' => $smokeInt($countAfterSecond),
    ];
    if (!$test2Pass) {
        $failures++;
    }
} catch (\RuntimeException | \PDOException $exc) {
    $report['test_2_idempotent_reinsert'] = ['fail' => 'exception', 'message' => $exc->getMessage()];
    $failures++;
}

// ----------------------------------------------------------------------
// Test 3 — different field_path, same patient + doc_sha256: expect a
//          second row inserted (the idempotency key is per-fact).
// ----------------------------------------------------------------------
try {
    $insertedThird = $repository->persistExtractedDocument(
        $buildPayload($testFieldPath2),
        $testPatientUuid,
        $testDocumentUuidBin,
        '0',
    );
    $countForKey2 = QueryUtils::fetchSingleValue(
        'SELECT COUNT(*) AS c FROM `copilot_document_facts` WHERE `idempotency_key` = ?',
        'c',
        [$idempotencyKey2],
    );
    $test3Pass = ($insertedThird > 0) && ($smokeInt($countForKey2) === 1);
    $report['test_3_new_fieldpath_inserts'] = [
        'pass' => $test3Pass,
        'last_insert_id' => $insertedThird,
        'db_count' => $smokeInt($countForKey2),
    ];
    if (!$test3Pass) {
        $failures++;
    }
} catch (\RuntimeException | \PDOException $exc) {
    $report['test_3_new_fieldpath_inserts'] = ['fail' => 'exception', 'message' => $exc->getMessage()];
    $failures++;
}

// ----------------------------------------------------------------------
// Test 4 - collection_date survives into field_value_json.
// ----------------------------------------------------------------------
try {
    $collectionDate = QueryUtils::fetchSingleValue(
        "SELECT JSON_UNQUOTE(JSON_EXTRACT(`field_value_json`, '$.collection_date')) AS collection_date
           FROM `copilot_document_facts`
          WHERE `idempotency_key` = ?",
        'collection_date',
        [$idempotencyKey1],
    );
    $test4Pass = $collectionDate === '2025-07-18';
    $report['test_4_collection_date_persisted'] = [
        'pass' => $test4Pass,
        'collection_date' => is_scalar($collectionDate) ? (string) $collectionDate : null,
    ];
    if (!$test4Pass) {
        $failures++;
    }
} catch (\RuntimeException | \PDOException $exc) {
    $report['test_4_collection_date_persisted'] = ['fail' => 'exception', 'message' => $exc->getMessage()];
    $failures++;
}

// ----------------------------------------------------------------------
// Cleanup — remove the two rows we created.
// ----------------------------------------------------------------------
try {
    QueryUtils::sqlStatementThrowException(
        'DELETE FROM `copilot_document_facts` WHERE `idempotency_key` IN (?, ?)',
        [$idempotencyKey1, $idempotencyKey2],
    );
} catch (\RuntimeException $exc) {
    // Cleanup failure is non-fatal; print a warning so the operator can
    // run the DELETE manually if needed. The next smoke run will retry.
    if (!$json) {
        fwrite(
            STDERR,
            "WARNING: smoke cleanup DELETE failed: " . $exc->getMessage() . "\n"
            . "Manual cleanup: DELETE FROM copilot_document_facts WHERE idempotency_key IN ('"
            . $idempotencyKey1 . "', '" . $idempotencyKey2 . "');\n"
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
        // phpstan-friendly accessor: keys vary per branch (skip / pass / fail);
        // re-type as a plain string-keyed map so phpstan doesn't lock the
        // union shape and complain about offsets it can't see in every arm.
        /** @var array<string, mixed> $row */
        if (array_key_exists('skip', $row)) {
            $skip = $row['skip'];
            echo "[SKIP] {$name}: " . (is_string($skip) ? $skip : '') . "\n";
            continue;
        }
        $passVal = $row['pass'] ?? false;
        $status = ($passVal === true) ? 'PASS' : 'FAIL';
        echo "[{$status}] {$name}";
        if (array_key_exists('last_insert_id', $row)) {
            $lid = $row['last_insert_id'];
            $dbc = $row['db_count'] ?? '?';
            echo " (last_insert_id=" . (is_scalar($lid) ? (string) $lid : '?')
                . ", db_count=" . (is_scalar($dbc) ? (string) $dbc : '?') . ")";
        } elseif (array_key_exists('fail', $row)) {
            $fail = $row['fail'];
            $msg = $row['message'] ?? '';
            echo " — " . (is_string($fail) ? $fail : '?') . ": "
                . (is_string($msg) ? $msg : '');
        }
        echo "\n";
    }
    echo $failures === 0 ? "DocumentFactsRepository smoke: ALL PASSED\n" : "DocumentFactsRepository smoke: {$failures} FAILED\n";
}

exit($failures === 0 ? 0 : 1);
