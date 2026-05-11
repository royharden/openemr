<?php

/**
 * CLI smoke test for AgDR-0081 — LabResultWriter native writeback gating
 * and preliminary-status posture.
 *
 * Verifies:
 *   1. Without COPILOT_NATIVE_LAB_WRITEBACK_DEMO_MODE=1 the writer returns
 *      ['gated' => true, 'written' => 0, 'reason' => 'native_writeback_disabled']
 *      WITHOUT touching procedure_* or the map table (gate runs before
 *      ensureMapSchema()).
 *   2. With the env var set AND a seeded demo patient + lab fact, the writer
 *      creates procedure_* rows whose status fields are the LEAST-FINAL
 *      values the OpenEMR enums support: order_status='pending',
 *      report_status='prelim', review_status='received', result_status='prelim'.
 *      VLM extractions must NEVER appear as clinician-signed clinical truth.
 *   3. The provenance comment carries the "[Co-Pilot extracted - pending
 *      clinician review]" human-readable label so a clinician on the Lab
 *      Review screen sees the unreviewed status before parsing the
 *      machine-readable prefix.
 *
 * Usage from the openemr container:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/lab_result_writer_demo_mode_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/lab_result_writer_demo_mode_smoke.php --pid=9101 --json
 *
 * The "with env var on" portion (test 2 + 3) requires a seeded demo patient
 * (Chen, pid 9101 by default) AND a copilot_document_facts row tagged
 * doc_type='lab_pdf' for that patient. Both are produced by Phase 5.1's
 * 21-step Docker verification harness. If the prerequisites are absent
 * the test prints SKIP for tests 2+3 and PASS for test 1 (the gate check
 * works without any DB state).
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
require_once __DIR__ . '/../src/Service/LabResultWriter.php';

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Modules\ClinicalCopilot\Service\LabResultWriter;

$pid = 9101;
$json = false;
$cliArgs = $argv ?? [];
foreach (array_slice($cliArgs, 1) as $arg) {
    if ($arg === '--json') {
        $json = true;
        continue;
    }
    if (str_starts_with($arg, '--pid=')) {
        $pid = (int) substr($arg, 6);
    }
}

$report = [];
/** @var int $failures */
$failures = 0;

// ----------------------------------------------------------------------
// Test 1 — without env var, writer returns gated=true and touches nothing.
// ----------------------------------------------------------------------
putenv('COPILOT_NATIVE_LAB_WRITEBACK_DEMO_MODE');  // explicitly unset
$_ENV['COPILOT_NATIVE_LAB_WRITEBACK_DEMO_MODE'] = '';

$writer = new LabResultWriter(ServiceContainer::getLogger());

// Use a fake doc sha so we never accidentally touch a real document's facts.
$fakeDocSha = str_repeat('0', 64);
$fakePatientUuid = '00000000-0000-0000-0000-000000000000';

$result = $writer->writeLabFactsForDocument(
    /* patientId */       0,
    /* patientUuid */     $fakePatientUuid,
    /* documentId */      0,
    /* documentUuidStr */ '00000000-0000-0000-0000-000000000000',
    /* documentSha256 */  $fakeDocSha,
    /* providerId */      0,
);

$gatedFlag = $result['gated'] ?? false;
$writtenCount = $result['written'];
$reasonStr = $result['reason'] ?? null;
$test1Pass = (
    $gatedFlag === true
    && $writtenCount === 0
    && $reasonStr === 'native_writeback_disabled'
);
$report['test_1_gate_off'] = [
    'pass' => $test1Pass,
    'result' => $result,
];
if ($test1Pass !== true) {
    $failures++;
}

// ----------------------------------------------------------------------
// Test 2 — with env var on, real demo patient + lab fact:
//   verify the four status fields are the least-final values.
// ----------------------------------------------------------------------
putenv('COPILOT_NATIVE_LAB_WRITEBACK_DEMO_MODE=1');
$_ENV['COPILOT_NATIVE_LAB_WRITEBACK_DEMO_MODE'] = '1';

$prereq = QueryUtils::fetchSingleValue(
    "SELECT COUNT(*) AS c
       FROM patient_data pd
      WHERE pd.pid = ?
        AND EXISTS (
            SELECT 1 FROM copilot_document_facts f
             WHERE f.patient_uuid_hash = SHA2(LOWER(BIN_TO_UUID(pd.uuid, true)), 256)
               AND f.doc_type = 'lab_pdf'
        )",
    'c',
    [$pid],
);
$prereqSatisfied = is_numeric($prereq) && (int) $prereq > 0;

if (!$prereqSatisfied) {
    $report['test_2_status_values'] = [
        'pass' => null,
        'skip_reason' => 'no demo lab fact for pid=' . $pid . ' - run Phase 5.1 21-step verification first',
    ];
    $report['test_3_provenance_label'] = [
        'pass' => null,
        'skip_reason' => 'depends on test_2',
    ];
} else {
    /** @var int $beforeMaxOrderId */
    $beforeMaxOrderIdRaw = QueryUtils::fetchSingleValue(
        'SELECT COALESCE(MAX(procedure_order_id), 0) AS m FROM procedure_order',
        'm',
        [],
    );
    $beforeMaxOrderId = is_numeric($beforeMaxOrderIdRaw) ? (int) $beforeMaxOrderIdRaw : 0;

    $patientRows = QueryUtils::fetchRecords(
        'SELECT pid, uuid FROM patient_data WHERE pid = ? LIMIT 1',
        [$pid],
    );
    $patientUuidStr = '';
    if (isset($patientRows[0]['uuid']) && is_string($patientRows[0]['uuid'])) {
        $patientUuidStr = UuidRegistry::uuidToString($patientRows[0]['uuid']);
    }

    $factRows = QueryUtils::fetchRecords(
        "SELECT document_sha256, COUNT(*) AS c
           FROM copilot_document_facts
          WHERE patient_uuid_hash = SHA2(LOWER(?), 256)
            AND doc_type = 'lab_pdf'
          GROUP BY document_sha256
          ORDER BY c DESC
          LIMIT 1",
        [$patientUuidStr],
    );

    if ($factRows === [] || !isset($factRows[0]['document_sha256'])) {
        $report['test_2_status_values'] = [
            'pass' => null,
            'skip_reason' => 'no copilot_document_facts row located via patient_uuid_hash',
        ];
        $report['test_3_provenance_label'] = ['pass' => null, 'skip_reason' => 'depends on test_2'];
    } else {
        $factRow = $factRows[0];

        $docRows = QueryUtils::fetchRecords(
            'SELECT id, uuid FROM documents WHERE foreign_id = ? AND deleted = 0 ORDER BY id DESC LIMIT 1',
            [$pid],
        );

        $documentId = 0;
        $documentUuidStr = '';
        if (isset($docRows[0])) {
            $docRow = $docRows[0];
            $documentId = is_numeric($docRow['id'] ?? null) ? (int) $docRow['id'] : 0;
            if (isset($docRow['uuid']) && is_string($docRow['uuid'])) {
                $documentUuidStr = UuidRegistry::uuidToString($docRow['uuid']);
            }
        }

        $documentSha256 = is_string($factRow['document_sha256']) ? $factRow['document_sha256'] : '';

        $result2 = $writer->writeLabFactsForDocument(
            $pid,
            $patientUuidStr,
            $documentId,
            $documentUuidStr,
            $documentSha256,
            /* providerId */ 1,
        );

        $newOrderRows = QueryUtils::fetchRecords(
            'SELECT po.procedure_order_id, po.order_status,
                    pr.report_status, pr.review_status,
                    pres.result_status, pres.comments
               FROM procedure_order po
          LEFT JOIN procedure_report  pr   ON pr.procedure_order_id   = po.procedure_order_id
          LEFT JOIN procedure_result  pres ON pres.procedure_report_id = pr.procedure_report_id
              WHERE po.procedure_order_id > ?
                AND po.patient_id = ?',
            [$beforeMaxOrderId, $pid],
        );

        $newRowList = $newOrderRows;
        $allStatusFieldsCorrect = $newRowList !== [];
        $anyMissingLabel = false;
        foreach ($newRowList as $row) {
            if (($row['order_status'] ?? '') !== 'pending') {
                $allStatusFieldsCorrect = false;
            }
            if (($row['report_status'] ?? '') !== 'prelim') {
                $allStatusFieldsCorrect = false;
            }
            if (($row['review_status'] ?? '') !== 'received') {
                $allStatusFieldsCorrect = false;
            }
            if (($row['result_status'] ?? '') !== 'prelim') {
                $allStatusFieldsCorrect = false;
            }
            $commentsRaw = $row['comments'] ?? null;
            if (!is_string($commentsRaw) || !str_contains($commentsRaw, '[Co-Pilot extracted')) {
                $anyMissingLabel = true;
            }
        }

        $report['test_2_status_values'] = [
            'pass' => $allStatusFieldsCorrect,
            'rows_inspected' => count($newRowList),
            'writer_result' => $result2,
        ];
        $report['test_3_provenance_label'] = [
            'pass' => !$anyMissingLabel && $newRowList !== [],
            'rows_inspected' => count($newRowList),
        ];

        if (!$allStatusFieldsCorrect) {
            $failures++;
        }
        if ($anyMissingLabel) {
            $failures++;
        }
    }
}

// ----------------------------------------------------------------------
// Output
// ----------------------------------------------------------------------
if ($json) {
    echo json_encode([
        'failures' => $failures,
        'tests' => $report,
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL;
} else {
    foreach ($report as $name => $payload) {
        $verdict = $payload['pass'] === true
            ? 'PASS'
            : ($payload['pass'] === false ? 'FAIL' : 'SKIP');
        echo str_pad($verdict, 6) . $name . PHP_EOL;
        if (isset($payload['skip_reason'])) {
            echo '       reason: ' . $payload['skip_reason'] . PHP_EOL;
        }
    }
    echo PHP_EOL;
    echo $failures === 0
        ? "OK ({$failures} failures)" . PHP_EOL
        : "FAIL ({$failures} failures)" . PHP_EOL;
}

exit($failures === 0 ? 0 : 1);
