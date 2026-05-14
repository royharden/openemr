<?php

/**
 * CLI smoke test for Plan_wk2_Claude_Next08 §W1 — upload trace_id
 * end-to-end propagation from sidecar response to UI chip.
 *
 * Properties pinned (pure file-content checks — no DB, no Twig, no Docker
 * required):
 *
 *   1. The Pydantic ExtractedDocument schema declares a `trace_id` field
 *      with a default factory (UUID v4). Existing callers don't break.
 *   2. Each of the three /v1/extract/* route handlers in routes.py
 *      generates a `run_id = str(uuid.uuid4())` BEFORE calling the
 *      extractor and overrides `validated.trace_id = run_id` after
 *      validation — so the response carries a stable, Langfuse-emitted
 *      trace ID, not a fresh one from the default factory.
 *   3. observability.py exports a `record_extract` helper + an
 *      `EXTRACT_TRACE_NAME` constant; the three routes call
 *      `record_extract(...)` for both the success and error paths.
 *   4. `create_patient_from_intake.php` echoes `$payload['trace_id']`
 *      back to the browser as `trace_id` in the JSON response.
 *   5. `copilot.js`'s upload handler renders the chip in the
 *      upload-status text using the "[trace: <8-char-prefix>…]" format.
 *
 * Usage:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/upload_trace_id_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/upload_trace_id_smoke.php --json
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

$jsonMode = in_array('--json', $argv ?? [], true);

$moduleRoot = realpath(__DIR__ . '/..');
if ($moduleRoot === false) {
    fwrite(STDERR, "Could not resolve module root.\n");
    exit(2);
}

// Repo root is four levels up from moduleRoot (custom_modules / modules /
// interface / openemr). Resolve via realpath to keep the test path-agnostic
// across host vs container invocation.
$repoRoot = realpath($moduleRoot . '/../../../../');
if ($repoRoot === false) {
    fwrite(STDERR, "Could not resolve repo root.\n");
    exit(2);
}

$schemasPath = $repoRoot . '/agent/copilot-api/app/schemas.py';
$routesPath = $repoRoot . '/agent/copilot-api/app/routes.py';
$observabilityPath = $repoRoot . '/agent/copilot-api/app/observability.py';
$createPatientPath = $moduleRoot . '/public/api/create_patient_from_intake.php';
$copilotJsPath = $moduleRoot . '/public/assets/js/copilot.js';

/** @var array<string, array<string, mixed>> $results */
$results = [];

$printRecord = static function (string $name, bool $passed, string $detail) use ($jsonMode): void {
    if ($jsonMode) {
        return;
    }
    $tag = $passed ? '[PASS]' : '[FAIL]';
    echo $tag . ' ' . $name . "\n        " . $detail . "\n";
};

// ---------------------------------------------------------------------------
// Test 1: Pydantic ExtractedDocument has a trace_id field with default factory.
// ---------------------------------------------------------------------------
$schemasSource = is_file($schemasPath) ? (string) file_get_contents($schemasPath) : '';
$hasTraceField = (bool) preg_match(
    '/trace_id:\s*str\s*=\s*Field\(\s*default_factory\s*=\s*lambda\s*:\s*str\(uuid\.uuid4\(\)\)/',
    $schemasSource
);
$detail = $hasTraceField
    ? 'ExtractedDocument.trace_id declared with default_factory=lambda: str(uuid.uuid4())'
    : 'ExtractedDocument missing trace_id field with default factory';
$results['schema_trace_id'] = ['passed' => $hasTraceField, 'detail' => $detail];
$printRecord('schema_trace_id', $hasTraceField, $detail);

// ---------------------------------------------------------------------------
// Test 2: Each extract route handler generates run_id and overrides validated.trace_id.
// ---------------------------------------------------------------------------
$routesSource = is_file($routesPath) ? (string) file_get_contents($routesPath) : '';
$runIdCount = preg_match_all('/run_id\s*=\s*str\(uuid\.uuid4\(\)\)/', $routesSource);
$overrideCount = preg_match_all('/validated\.trace_id\s*=\s*run_id/', $routesSource);
$passed = ($runIdCount >= 3) && ($overrideCount >= 3);
$detail = $passed
    ? sprintf('routes.py: %d run_id generations, %d validated.trace_id overrides (≥3 expected for the three extract handlers)', $runIdCount, $overrideCount)
    : sprintf('routes.py: run_id=%d (need ≥3), validated.trace_id override=%d (need ≥3)', $runIdCount, $overrideCount);
$results['routes_run_id_pattern'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('routes_run_id_pattern', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 3: observability.py exports record_extract + EXTRACT_TRACE_NAME,
// and routes.py calls record_extract on success + error paths.
// ---------------------------------------------------------------------------
$obsSource = is_file($observabilityPath) ? (string) file_get_contents($observabilityPath) : '';
$hasTraceName = str_contains($obsSource, "EXTRACT_TRACE_NAME = \"clinical_copilot.extract\"");
$hasRecordExtract = (bool) preg_match('/^def record_extract\(/m', $obsSource);
// Each of the three route handlers calls record_extract on success (3) +
// invalid_input (3) + failed (3) = 9 total. Allow ≥6 to tolerate a future
// path consolidation.
$recordCallCount = preg_match_all('/record_extract\s*\(/', $routesSource);
$passed = $hasTraceName && $hasRecordExtract && ($recordCallCount >= 6);
$detail = $passed
    ? sprintf('observability.py has EXTRACT_TRACE_NAME + record_extract(); routes.py calls record_extract %d× (≥6)', $recordCallCount)
    : 'missing: '
        . ($hasTraceName ? '' : 'EXTRACT_TRACE_NAME; ')
        . ($hasRecordExtract ? '' : 'record_extract() declaration; ')
        . ($recordCallCount >= 6 ? '' : sprintf('record_extract calls: %d (need ≥6)', $recordCallCount));
$results['observability_record_extract'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('observability_record_extract', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 4: create_patient_from_intake.php echoes trace_id in JSON response.
// ---------------------------------------------------------------------------
$cpfiSource = is_file($createPatientPath) ? (string) file_get_contents($createPatientPath) : '';
$hasTraceExtract = (bool) preg_match(
    "/\\\$traceId\\s*=\\s*is_string\\(\\\$payload\\[\\s*'trace_id'\\s*\\]\\s*\\?\\?\\s*null\\)/",
    $cpfiSource
);
$echoesInResponse = (bool) preg_match(
    "/'trace_id'\\s*=>\\s*\\\$traceId/",
    $cpfiSource
);
$passed = $hasTraceExtract && $echoesInResponse;
$detail = $passed
    ? 'create_patient_from_intake.php extracts $payload[\'trace_id\'] and includes it in the JSON response'
    : 'missing: '
        . ($hasTraceExtract ? '' : '$traceId extraction; ')
        . ($echoesInResponse ? '' : 'trace_id key in JSON response');
$results['cpfi_trace_id_echo'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('cpfi_trace_id_echo', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 5: copilot.js renders the trace chip in the upload-status text.
// ---------------------------------------------------------------------------
$jsSource = is_file($copilotJsPath) ? (string) file_get_contents($copilotJsPath) : '';
$readsTraceId = str_contains($jsSource, "typeof resp.body.trace_id === 'string'");
$rendersChip = (bool) preg_match("/'\\s*\\[trace:\\s*'\\s*\\+\\s*traceId\\.slice\\(0,\\s*8\\)/", $jsSource);
$passed = $readsTraceId && $rendersChip;
$detail = $passed
    ? 'copilot.js reads resp.body.trace_id and renders "[trace: <8-char>…]" suffix on every upload success'
    : 'missing: '
        . ($readsTraceId ? '' : 'trace_id read from response; ')
        . ($rendersChip ? '' : 'chip render pattern "[trace: <prefix>…]"');
$results['js_trace_chip'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('js_trace_chip', $passed, $detail);

// ---------------------------------------------------------------------------
// Summary.
// ---------------------------------------------------------------------------
$passedCount = 0;
foreach ($results as $r) {
    if (isset($r['passed']) && $r['passed'] === true) {
        $passedCount++;
    }
}
$total = count($results);

if ($jsonMode) {
    echo json_encode(
        ['summary' => ['passed' => $passedCount, 'total' => $total], 'tests' => $results],
        JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES
    ) . "\n";
} else {
    echo "\n--- $passedCount/$total passed ---\n";
}

exit($passedCount === $total ? 0 : 1);
