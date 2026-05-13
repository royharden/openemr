<?php

/**
 * CLI smoke test for AgDR-0077 / Plan §6.3 — MedicationReconciliation service
 * + medication_reconciliation.php endpoint.
 *
 * Two layers:
 *
 *   A. File-content smoke (no DB): assert the endpoint file shape (auth,
 *      patient scope, JSON response, no CSRF check — same posture as
 *      lab_trends.php per AgDR-0083), and assert MedicationReconciliation.php
 *      exposes `reconcileForPatient`, `buildReconciliation`, and
 *      `normalizeDrugName`.
 *
 *   B. Pure-function unit assertions (no DB): call
 *      `MedicationReconciliation::buildReconciliation(...)` and
 *      `::normalizeDrugName(...)` with fixed inputs and assert the
 *      classification + summary counts.
 *
 *      Fixture: Kowalski-discharge × seed prescriptions, which is exactly the
 *      reconciliation_mismatch eval case shape:
 *        * Both sides:   Lisinopril, Atorvastatin, Hydrochlorothiazide
 *                        → confirmed (3 rows)
 *        * Discharge only: Pantoprazole, Furosemide, Acetaminophen, Metformin
 *                        → newly_listed (4 rows)
 *        * Rx only:        Atenolol (legacy drug not on discharge)
 *                        → possibly_discontinued (1 row)
 *      Expected summary: confirmed=3, newly_listed=4, possibly_discontinued=1, total=8.
 *
 * No DB access required — Layer A uses file_get_contents, Layer B calls
 * the pure-function path.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

$moduleRoot = realpath(__DIR__ . '/..');
if ($moduleRoot === false) {
    fwrite(STDERR, "FAIL: cannot resolve module root\n");
    exit(2);
}

$endpoint = $moduleRoot . '/public/api/medication_reconciliation.php';
$service = $moduleRoot . '/src/Service/MedicationReconciliation.php';

// phpstan openemr.noGlobalNsFunctions forbids global-namespace function
// declarations. Closure-by-reference (`array &$failures`) erases the
// list<string> type at every call site under phpstan-level-10 (see
// agentdocs/agent_lessons.md and the canonical reference at
// lab_trends_endpoint_smoke.php). Anonymous class with a typed property
// keeps types intact end-to-end.
$smokeAssert = new class {
    /** @var list<string> */
    public array $failures = [];

    /** @param list<string> $required */
    public function fileContains(string $path, array $required): void
    {
        if (!is_file($path)) {
            $this->failures[] = "missing file: $path";
            return;
        }
        $content = file_get_contents($path);
        if ($content === false) {
            $this->failures[] = "cannot read: $path";
            return;
        }
        foreach ($required as $needle) {
            if (!str_contains($content, $needle)) {
                $this->failures[] = "$path: missing required substring: $needle";
            }
        }
    }

    public function fileDoesNotContain(string $path, string $needle, string $why): void
    {
        if (!is_file($path)) {
            $this->failures[] = "missing file: $path";
            return;
        }
        $content = file_get_contents($path);
        if ($content === false) {
            $this->failures[] = "cannot read: $path";
            return;
        }
        if (str_contains($content, $needle)) {
            $this->failures[] = "$path: forbidden substring present ($why): $needle";
        }
    }
};

// -----------------------------------------------------------------
// Layer A — file-content smoke for endpoint + service.
// -----------------------------------------------------------------
$smokeAssert->fileContains($endpoint, [
    "declare(strict_types=1);",
    "require_once(__DIR__ . \"/../../../../../globals.php\");",
    "AclMain::aclCheckCore('patients', 'med')",
    "\$session->get('pid')",
    "BaseService::getUuidById((string) \$pid, 'patient_data', 'pid')",
    "use OpenEMR\\Modules\\ClinicalCopilot\\Service\\MedicationReconciliation;",
    "\$service->reconcileForPatient(\$pid)",
    "header('Content-Type: application/json; charset=utf-8');",
    "header('X-Content-Type-Options: nosniff');",
]);

// Read-only GET — CSRF intentionally omitted (AgDR-0083 precedent).
$smokeAssert->fileDoesNotContain(
    $endpoint,
    'CsrfUtils::verifyCsrfToken',
    'medication_reconciliation.php is read-only GET; CSRF intentionally omitted'
);

$smokeAssert->fileContains($service, [
    "final class MedicationReconciliation",
    "public function reconcileForPatient(int \$pid): array",
    "public static function buildReconciliation(array \$extracted, array \$prescriptions): array",
    "public static function normalizeDrugName(string \$raw): string",
    "const STATUS_CONFIRMED",
    "const STATUS_NEWLY_LISTED",
    "const STATUS_POSSIBLY_DISCONTINUED",
    // Query joins prescriptions for the current patient with active=1.
    "FROM prescriptions",
    "AND active = 1",
    // SQL is parameterized — no string interpolation of pid.
    "WHERE patient_id = ?",
]);

$smokeAssert->fileDoesNotContain(
    $service,
    'WHERE patient_id = " . $pid',
    'pid must be parameterized in the prescriptions query, not concatenated'
);

// -----------------------------------------------------------------
// Layer B — pure-function classification assertions.
// -----------------------------------------------------------------
require_once $service;

use OpenEMR\Modules\ClinicalCopilot\Service\MedicationReconciliation;

// Normalization rules: lowercase, strip parentheticals, collapse whitespace.
$normCases = [
    ['Aspirin (low-dose)', 'aspirin'],
    ['  Metformin  ',        'metformin'],
    ['Patel, N.',            'patel, n'],
    ['',                      ''],
    ['Lisinopril',            'lisinopril'],
];
foreach ($normCases as [$input, $expected]) {
    $actual = MedicationReconciliation::normalizeDrugName($input);
    if ($actual !== $expected) {
        $smokeAssert->failures[] = "normalizeDrugName($input): expected '$expected', got '$actual'";
    }
}

// Kowalski mismatch fixture — see file header.
$extracted = [
    ['drug_name' => 'Pantoprazole',         'dose' => '40 mg',    'route' => 'PO', 'frequency' => 'BID'],
    ['drug_name' => 'Acetaminophen',        'dose' => '650 mg',   'route' => 'PO', 'frequency' => 'Q6H PRN'],
    ['drug_name' => 'Hydrochlorothiazide',  'dose' => '12.5 mg',  'route' => 'PO', 'frequency' => 'Daily'],
    ['drug_name' => 'Lisinopril',           'dose' => '20 mg',    'route' => 'PO', 'frequency' => 'Daily'],
    ['drug_name' => 'Atorvastatin',         'dose' => '40 mg',    'route' => 'PO', 'frequency' => 'QHS'],
    ['drug_name' => 'Metformin',            'dose' => '500 mg',   'route' => 'PO', 'frequency' => 'BID'],
    ['drug_name' => 'Furosemide',           'dose' => '20 mg',    'route' => 'PO', 'frequency' => 'Daily'],
];
$prescriptions = [
    ['drug_name' => 'Lisinopril',          'dose' => '20 mg',  'route' => 'PO', 'active' => 1],
    ['drug_name' => 'Atorvastatin',        'dose' => '20 mg',  'route' => 'PO', 'active' => 1],
    ['drug_name' => 'Hydrochlorothiazide', 'dose' => '25 mg',  'route' => 'PO', 'active' => 1],
    ['drug_name' => 'Atenolol',            'dose' => '50 mg',  'route' => 'PO', 'active' => 1],
];

$result = MedicationReconciliation::buildReconciliation($extracted, $prescriptions);

$expectSummary = [
    'confirmed'             => 3,
    'newly_listed'          => 4,
    'possibly_discontinued' => 1,
    'total'                 => 8,
];
foreach ($expectSummary as $k => $expected) {
    // The `summary` shape is locked by MedicationReconciliation::buildReconciliation's
    // return-type annotation; every key is guaranteed-present. phpstan flags
    // a `?? null` here as nullCoalesce.offset.
    $actual = $result['summary'][$k];
    if ($actual !== $expected) {
        $actual_repr = var_export($actual, true);
        $smokeAssert->failures[] = "buildReconciliation.summary.{$k}: expected {$expected}, got {$actual_repr}";
    }
}

if (count($result['rows']) !== 8) {
    $smokeAssert->failures[] = 'buildReconciliation: expected 8 rows, got ' . count($result['rows']);
}

// Spot-check per-status classifications.
$byDrug = [];
foreach ($result['rows'] as $row) {
    $byDrug[strtolower($row['drug_name'])] = $row;
}
$statusChecks = [
    'lisinopril'          => 'confirmed',
    'atorvastatin'        => 'confirmed',
    'hydrochlorothiazide' => 'confirmed',
    'pantoprazole'        => 'newly_listed',
    'acetaminophen'       => 'newly_listed',
    'metformin'           => 'newly_listed',
    'furosemide'          => 'newly_listed',
    'atenolol'            => 'possibly_discontinued',
];
foreach ($statusChecks as $drug => $expected) {
    $actual = $byDrug[$drug]['status'] ?? null;
    if ($actual !== $expected) {
        $actual_repr = var_export($actual, true);
        $smokeAssert->failures[] = "buildReconciliation: {$drug} expected status '{$expected}', got {$actual_repr}";
    }
}

// Happy path — all drugs match (reconciliation_match case).
$happyExtracted = [
    ['drug_name' => 'Lisinopril',  'dose' => '10 mg', 'route' => 'PO', 'frequency' => 'Daily'],
    ['drug_name' => 'Atorvastatin', 'dose' => '20 mg', 'route' => 'PO', 'frequency' => 'QHS'],
];
$happyRx = [
    ['drug_name' => 'lisinopril',  'dose' => '10 mg', 'route' => 'PO', 'active' => 1],
    ['drug_name' => 'ATORVASTATIN', 'dose' => '20 mg', 'route' => 'PO', 'active' => 1],
];
$happy = MedicationReconciliation::buildReconciliation($happyExtracted, $happyRx);
if ($happy['summary']['confirmed'] !== 2) {
    $smokeAssert->failures[] = 'reconciliation_match: expected confirmed=2, got ' . $happy['summary']['confirmed'];
}
if ($happy['summary']['newly_listed'] !== 0 || $happy['summary']['possibly_discontinued'] !== 0) {
    $smokeAssert->failures[] = 'reconciliation_match: case-insensitive normalization should produce zero new/discontinued rows';
}

// -----------------------------------------------------------------
// Report
// -----------------------------------------------------------------
if ($smokeAssert->failures !== []) {
    fwrite(STDERR, "medication_reconciliation_smoke: " . count($smokeAssert->failures) . " failure(s):\n");
    foreach ($smokeAssert->failures as $f) {
        fwrite(STDERR, "  - " . $f . "\n");
    }
    exit(1);
}

echo "medication_reconciliation_smoke: ALL PASSED\n";
exit(0);
