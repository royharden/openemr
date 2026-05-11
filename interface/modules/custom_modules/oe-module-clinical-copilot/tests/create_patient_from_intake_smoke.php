<?php

/**
 * CLI smoke test for create_patient_from_intake.php helper functions
 * (Plan_wk2_Claude_Next05 §2.6 smoke #2, AgDR-0071 + AgDR-0066 + AgDR-0068).
 *
 * The endpoint file itself runs procedural request-handling code at
 * top-of-file (CSRF + ACL + multipart upload) which can only be exercised
 * via a real HTTP POST. The helper functions and AmbiguousDobException
 * class were extracted to `create_patient_from_intake_helpers.php` (Phase
 * 2.6 refactor) so this smoke can require them directly without the
 * endpoint logic firing.
 *
 * Phase 5.1's 21-step Docker verification exercises the full
 * endpoint via curl. This smoke covers the pure-function helpers that
 * are too cheap to exercise from a curl harness:
 *
 *   1. copilot_create_normalize_dob — happy paths (ISO, wordy, EU dash,
 *      US slash, EU slash that disagrees), the AmbiguousDobException
 *      throw path, and null on garbage.
 *   2. copilot_create_normalize_sex — male/female/unknown mapping
 *      including edge inputs.
 *   3. copilot_create_demographics_from_extract — multi-convention
 *      field plucking (bare name vs intake.* vs demographics.* vs
 *      intake.demographics.*) per the agent_lessons 2026-05-10T21:45Z
 *      lesson.
 *   4. copilot_create_lookup_existing_patient_by_usertext1 — miss returns
 *      null (we cannot easily insert a synthetic patient_data row from
 *      a smoke without breaking referential integrity).
 *
 * Skip-gracefully on test 4 if patient_data is unreachable; tests 1–3 are
 * pure functions and never SKIP.
 *
 * Usage from the openemr container:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/create_patient_from_intake_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/create_patient_from_intake_smoke.php --json
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
require_once __DIR__ . '/../public/api/create_patient_from_intake_helpers.php';

use OpenEMR\Modules\ClinicalCopilot\Api\Internal\AmbiguousDobException;
use function OpenEMR\Modules\ClinicalCopilot\Api\Internal\copilot_create_demographics_from_extract;
use function OpenEMR\Modules\ClinicalCopilot\Api\Internal\copilot_create_lookup_existing_patient_by_usertext1;
use function OpenEMR\Modules\ClinicalCopilot\Api\Internal\copilot_create_normalize_dob;
use function OpenEMR\Modules\ClinicalCopilot\Api\Internal\copilot_create_normalize_sex;

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

// ----------------------------------------------------------------------
// Test 1 — DOB normalizer covers each parser arm + ambiguity throw.
// ----------------------------------------------------------------------
$dobCases = [
    // [raw, expected_iso (null = expect null), expects_ambiguous]
    ['2026-05-11',     '2026-05-11', false], // ISO direct.
    ['Aug 14, 1962',   '1962-08-14', false], // Wordy short.
    ['August 14, 1962', '1962-08-14', false], // Wordy long.
    ['14-08-1962',     '1962-08-14', false], // d-m-Y dash European.
    ['12/12/1990',     '1990-12-12', false], // Both conventions agree.
    ['10/20/1985',     '1985-10-20', false], // m/d/Y only (20 is not a valid month).
    ['25/12/1985',     '1985-12-25', false], // d/m/Y only (25 is not a valid month US).
    ['not-a-date',     null,         false], // No parser matches → null.
    ['',               null,         false], // Empty → null.
    [null,             null,         false], // null → null.
    ['05/03/1962',     null,         true ], // Ambiguous: May 3 (US) vs March 5 (EU).
];
$dobFailures = [];
foreach ($dobCases as $idx => [$raw, $expectedIso, $expectsAmbiguous]) {
    try {
        $got = copilot_create_normalize_dob($raw);
        if ($expectsAmbiguous) {
            $dobFailures[] = sprintf('case %d (%s): expected AmbiguousDobException, got "%s"', $idx, var_export($raw, true), $got ?? 'null');
        } elseif ($got !== $expectedIso) {
            $dobFailures[] = sprintf('case %d (%s): expected "%s", got "%s"', $idx, var_export($raw, true), $expectedIso ?? 'null', $got ?? 'null');
        }
    } catch (AmbiguousDobException $exc) {
        if (!$expectsAmbiguous) {
            $dobFailures[] = sprintf('case %d (%s): unexpected AmbiguousDobException with candidates %s', $idx, var_export($raw, true), implode(',', $exc->candidates));
        } else {
            // The "05/03/1962" case must surface both candidates.
            if (count($exc->candidates) !== 2) {
                $dobFailures[] = sprintf('case %d: AmbiguousDobException had %d candidates, expected 2', $idx, count($exc->candidates));
            }
        }
    }
}
$test1Pass = $dobFailures === [];
$report['test_1_dob_normalizer'] = [
    'pass' => $test1Pass,
    'cases_tested' => count($dobCases),
    'failures' => $dobFailures,
];
if (!$test1Pass) {
    $failures++;
}

// ----------------------------------------------------------------------
// Test 2 — sex normalizer.
// ----------------------------------------------------------------------
$sexCases = [
    [null,        'Unknown'],
    ['',          'Unknown'],
    [' ',         'Unknown'],
    ['M',         'Male'],
    ['m',         'Male'],
    ['male',      'Male'],
    ['Male',      'Male'],
    [' MALE ',    'Male'],
    ['F',         'Female'],
    ['female',    'Female'],
    ['Female',    'Female'],
    ['femme',     'Female'],
    ['other',     'Unknown'],
    ['nonbinary', 'Unknown'],
    ['xyz',       'Unknown'],
];
$sexFailures = [];
foreach ($sexCases as $idx => [$raw, $expected]) {
    $got = copilot_create_normalize_sex($raw);
    if ($got !== $expected) {
        $sexFailures[] = sprintf('case %d (%s): expected "%s", got "%s"', $idx, var_export($raw, true), $expected, $got);
    }
}
$test2Pass = $sexFailures === [];
$report['test_2_sex_normalizer'] = [
    'pass' => $test2Pass,
    'cases_tested' => count($sexCases),
    'failures' => $sexFailures,
];
if (!$test2Pass) {
    $failures++;
}

// ----------------------------------------------------------------------
// Test 3 — demographics multi-convention plucking.
// ----------------------------------------------------------------------
$demographicsCases = [
    // Bare-name convention.
    [
        'label' => 'bare_names',
        'payload' => [
            'result' => [
                'fields' => [
                    ['name' => 'first_name', 'value' => 'Alice'],
                    ['name' => 'last_name', 'value' => 'Chen'],
                    ['name' => 'date_of_birth', 'value' => '1962-05-11'],
                ],
            ],
        ],
        'expected' => ['fname' => 'Alice', 'lname' => 'Chen', 'DOB' => '1962-05-11'],
    ],
    // intake.* convention.
    [
        'label' => 'intake_prefixed',
        'payload' => [
            'result' => [
                'fields' => [
                    ['name' => 'intake.first_name', 'value' => 'Bob'],
                    ['name' => 'intake.last_name', 'value' => 'Smith'],
                    ['name' => 'intake.dob', 'value' => '01/15/1970'],
                ],
            ],
        ],
        'expected' => ['fname' => 'Bob', 'lname' => 'Smith', 'DOB' => '01/15/1970'],
    ],
    // demographics.* convention.
    [
        'label' => 'demographics_prefixed',
        'payload' => [
            'result' => [
                'fields' => [
                    ['name' => 'demographics.first_name', 'value' => 'Carol'],
                    ['name' => 'demographics.last_name', 'value' => 'Jones'],
                    ['name' => 'demographics.date_of_birth', 'value' => '12 Mar 1985'],
                ],
            ],
        ],
        'expected' => ['fname' => 'Carol', 'lname' => 'Jones', 'DOB' => '12 Mar 1985'],
    ],
    // intake.demographics.* convention.
    [
        'label' => 'intake_demographics_prefixed',
        'payload' => [
            'result' => [
                'fields' => [
                    ['name' => 'intake.demographics.fname', 'value' => 'Dave'],
                    ['name' => 'intake.demographics.lname', 'value' => 'Lee'],
                    ['name' => 'intake.demographics.DOB', 'value' => '1999-02-28'],
                ],
            ],
        ],
        'expected' => ['fname' => 'Dave', 'lname' => 'Lee', 'DOB' => '1999-02-28'],
    ],
    // Empty fields list → all null.
    [
        'label' => 'empty_fields',
        'payload' => ['result' => ['fields' => []]],
        'expected' => ['fname' => null, 'lname' => null, 'DOB' => null],
    ],
];
$demographicsFailures = [];
foreach ($demographicsCases as $case) {
    $got = copilot_create_demographics_from_extract($case['payload']);
    foreach (['fname', 'lname', 'DOB'] as $field) {
        if (($got[$field] ?? null) !== $case['expected'][$field]) {
            $demographicsFailures[] = sprintf(
                'case "%s" field %s: expected "%s", got "%s"',
                $case['label'],
                $field,
                $case['expected'][$field] ?? 'null',
                $got[$field] ?? 'null',
            );
        }
    }
}
$test3Pass = $demographicsFailures === [];
$report['test_3_demographics_multi_convention'] = [
    'pass' => $test3Pass,
    'cases_tested' => count($demographicsCases),
    'failures' => $demographicsFailures,
];
if (!$test3Pass) {
    $failures++;
}

// ----------------------------------------------------------------------
// Test 4 — lookup miss returns null (AgDR-0068 invariant on no-match).
//          Hit case requires a synthetic patient_data row which is hard
//          to insert from a smoke without FK gymnastics; Phase 5.1
//          exercises the hit path via the full upload flow.
// ----------------------------------------------------------------------
try {
    $missResult = copilot_create_lookup_existing_patient_by_usertext1(
        'wk2-smoke-no-such-usertext1-' . bin2hex(random_bytes(4)),
    );
    $test4Pass = $missResult === null;
    $report['test_4_lookup_miss'] = [
        'pass' => $test4Pass,
        'result' => $missResult === null ? 'null' : 'non-null (BUG)',
    ];
    if (!$test4Pass) {
        $failures++;
    }
} catch (\RuntimeException | \PDOException $exc) {
    // patient_data table unreachable — SKIP gracefully (the function's
    // own catch handles DB errors and returns null, so this branch
    // shouldn't even be hit, but defensive).
    $report['test_4_lookup_miss'] = ['skip' => 'patient_data unreachable: ' . $exc->getMessage()];
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
        $count = $row['cases_tested'] ?? null;
        echo "[{$status}] {$name}";
        if (is_int($count)) {
            echo " ({$count} cases)";
        } elseif (array_key_exists('result', $row)) {
            $r = $row['result'];
            echo " (result=" . (is_string($r) ? $r : '?') . ")";
        }
        echo "\n";
        $failuresList = $row['failures'] ?? null;
        if ($passVal !== true && is_array($failuresList)) {
            foreach ($failuresList as $f) {
                echo "    - " . (is_string($f) ? $f : '') . "\n";
            }
        }
    }
    echo $failures === 0 ? "create_patient_from_intake smoke: ALL PASSED\n" : "create_patient_from_intake smoke: {$failures} FAILED\n";
}

exit($failures === 0 ? 0 : 1);
