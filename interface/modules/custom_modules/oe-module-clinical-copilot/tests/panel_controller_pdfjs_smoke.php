<?php

/**
 * CLI smoke test for AgDR-0072 — PDF.js vendored asset + SRI.
 *
 * Verifies that PanelController.php and the vendored PDF.js files stay
 * mutually consistent. The load-bearing properties this smoke pins:
 *
 *   1. PanelController.php references the LOCAL vendored path
 *      (interface/.../public/assets/vendor/pdfjs/pdf.min.js) — no cdnjs
 *      URL anywhere in the rendered <script> tag block.
 *
 *   2. PanelController.php carries an `integrity="sha384-..."` attribute
 *      on the pdf.min.js <script> tag.
 *
 *   3. The integrity hash in PanelController.php matches the actual
 *      SHA-384 of the vendored pdf.min.js file. Catches the stale-hash
 *      drift bug: someone bumps the version of pdf.min.js but forgets
 *      to update the SRI attribute — browser refuses to execute, demo
 *      breaks silently. This smoke catches it before commit.
 *
 *   4. Both pdf.min.js and pdf.worker.min.js exist on disk under the
 *      expected vendored path. Catches accidental deletion of one of
 *      the two files (the worker is loaded at runtime by the main lib;
 *      removing it produces a confusing in-browser worker-load error).
 *
 *   5. The pdfWorkerSrc value in PanelController.php points at the
 *      LOCAL vendored worker path — eliminates the cdnjs trust
 *      requirement at runtime.
 *
 *   6. LICENSE-NOTICE exists alongside the vendored files (Apache-2.0
 *      attribution requirement).
 *
 * No DB access required; this is a pure file-content smoke.
 *
 * Usage (host or container — works either way since no DB):
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/panel_controller_pdfjs_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/panel_controller_pdfjs_smoke.php --json
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

$jsonMode = in_array('--json', $argv ?? [], true);

$moduleRoot = realpath(__DIR__ . '/..');
if ($moduleRoot === false) {
    fwrite(STDERR, "Could not resolve module root.\n");
    exit(2);
}

$panelControllerPath = $moduleRoot . '/src/Controller/PanelController.php';
$vendorDir = $moduleRoot . '/public/assets/vendor/pdfjs';
$pdfMinPath = $vendorDir . '/pdf.min.js';
$pdfWorkerPath = $vendorDir . '/pdf.worker.min.js';
$licenseNoticePath = $vendorDir . '/LICENSE-NOTICE';

/** @var array<string, array<string, mixed>> $results */
$results = [];

// AgDR-0082 phpstan discipline: the print-side helper is a closure (no
// global-namespace named function). It does NOT take $results by reference
// because the @var annotation on $results is widened to mixed when phpstan
// analyzes a closure call that mutates by reference. Each test below
// assigns into $results directly and calls $printRecord for human output.
$printRecord = static function (string $name, bool $passed, string $detail) use ($jsonMode): void {
    if ($jsonMode) {
        return;
    }
    $tag = $passed ? '[PASS]' : '[FAIL]';
    echo $tag . ' ' . $name . "\n        " . $detail . "\n";
};

// ---------------------------------------------------------------------------
// Test 1: PanelController.php exists and is readable.
// ---------------------------------------------------------------------------
if (!is_file($panelControllerPath) || !is_readable($panelControllerPath)) {
    $detail = "expected PanelController.php at $panelControllerPath";
    $results['controller_present'] = ['passed' => false, 'detail' => $detail];
    $printRecord('controller_present', false, $detail);
    if ($jsonMode) {
        echo json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    }
    exit(1);
}
$controllerSource = (string) file_get_contents($panelControllerPath);
$detail = "PanelController.php found (" . strlen($controllerSource) . " bytes)";
$results['controller_present'] = ['passed' => true, 'detail' => $detail];
$printRecord('controller_present', true, $detail);

// ---------------------------------------------------------------------------
// Test 2: No cdnjs URL remains in the controller source.
// ---------------------------------------------------------------------------
$cdnjsHits = substr_count($controllerSource, 'cdnjs.cloudflare.com');
$passed = $cdnjsHits === 0;
$detail = $passed
    ? "no cdnjs.cloudflare.com references in PanelController.php"
    : "found $cdnjsHits cdnjs.cloudflare.com reference(s) — Phase 3.1 mandate (AgDR-0072) violated";
$results['no_cdnjs_url'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('no_cdnjs_url', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 3: Vendored pdf.min.js path appears in the script tag.
// ---------------------------------------------------------------------------
$expectedPathFragment = 'vendor/pdfjs/pdf.min.js';
$pathHits = substr_count($controllerSource, $expectedPathFragment);
$passed = $pathHits >= 1;
$detail = $passed
    ? "found $pathHits reference(s) to $expectedPathFragment"
    : "PanelController.php does not reference $expectedPathFragment — vendor swap incomplete";
$results['vendored_path_referenced'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('vendored_path_referenced', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 4: Worker source points at vendored path (not cdnjs).
// ---------------------------------------------------------------------------
$workerPathFragment = 'vendor/pdfjs/pdf.worker.min.js';
$workerPathHits = substr_count($controllerSource, $workerPathFragment);
$passed = $workerPathHits >= 1;
$detail = $passed
    ? "found $workerPathHits reference(s) to $workerPathFragment"
    : "PanelController.php does not reference $workerPathFragment — runtime worker load would still hit a CDN";
$results['vendored_worker_path_referenced'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('vendored_worker_path_referenced', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 5: integrity="sha384-..." attribute present on pdf.min.js.
// ---------------------------------------------------------------------------
$integrityRegex = '/integrity="sha384-([A-Za-z0-9+\/=]{56,})"/';
$integrityMatched = preg_match($integrityRegex, $controllerSource, $integrityMatch) === 1;
$declaredIntegrity = $integrityMatched ? $integrityMatch[1] : null;
$detail = $integrityMatched
    ? 'integrity="sha384-' . substr((string) $declaredIntegrity, 0, 16) . '..." present in PanelController.php'
    : 'no integrity="sha384-..." attribute found — SRI defense-in-depth missing';
$results['sri_attribute_present'] = ['passed' => $integrityMatched, 'detail' => $detail];
$printRecord('sri_attribute_present', $integrityMatched, $detail);

// ---------------------------------------------------------------------------
// Test 6: pdf.min.js exists on disk at the expected vendored location.
// ---------------------------------------------------------------------------
$pdfMinExists = is_file($pdfMinPath) && is_readable($pdfMinPath);
$detail = $pdfMinExists
    ? "pdf.min.js found at $pdfMinPath (" . filesize($pdfMinPath) . " bytes)"
    : "expected pdf.min.js at $pdfMinPath — vendoring incomplete";
$results['pdf_min_js_present'] = ['passed' => $pdfMinExists, 'detail' => $detail];
$printRecord('pdf_min_js_present', $pdfMinExists, $detail);

// ---------------------------------------------------------------------------
// Test 7: pdf.worker.min.js exists on disk at the expected vendored location.
// ---------------------------------------------------------------------------
$pdfWorkerExists = is_file($pdfWorkerPath) && is_readable($pdfWorkerPath);
$detail = $pdfWorkerExists
    ? "pdf.worker.min.js found at $pdfWorkerPath (" . filesize($pdfWorkerPath) . " bytes)"
    : "expected pdf.worker.min.js at $pdfWorkerPath — runtime worker load would 404";
$results['pdf_worker_min_js_present'] = ['passed' => $pdfWorkerExists, 'detail' => $detail];
$printRecord('pdf_worker_min_js_present', $pdfWorkerExists, $detail);

// ---------------------------------------------------------------------------
// Test 8: LICENSE-NOTICE present alongside vendored files (Apache-2.0).
// ---------------------------------------------------------------------------
$licenseExists = is_file($licenseNoticePath) && is_readable($licenseNoticePath);
$detail = $licenseExists
    ? "LICENSE-NOTICE found at $licenseNoticePath"
    : "missing LICENSE-NOTICE — Apache-2.0 attribution requirement unmet";
$results['license_notice_present'] = ['passed' => $licenseExists, 'detail' => $detail];
$printRecord('license_notice_present', $licenseExists, $detail);

// ---------------------------------------------------------------------------
// Test 9: integrity hash in PanelController.php matches the actual
// SHA-384 of the vendored pdf.min.js. Catches stale-hash drift.
// ---------------------------------------------------------------------------
if ($pdfMinExists && $declaredIntegrity !== null) {
    $actualHashBinary = hash_file('sha384', $pdfMinPath, true);
    if (!is_string($actualHashBinary) || strlen($actualHashBinary) !== 48) {
        $detail = 'hash_file failed for pdf.min.js';
        $results['sri_hash_matches_file'] = ['passed' => false, 'detail' => $detail];
        $printRecord('sri_hash_matches_file', false, $detail);
    } else {
        $actualBase64 = base64_encode($actualHashBinary);
        $hashesMatch = hash_equals($actualBase64, (string) $declaredIntegrity);
        $detail = $hashesMatch
            ? "SRI in PanelController.php matches actual SHA-384 of pdf.min.js"
            : "SRI MISMATCH — controller declares 'sha384-" . substr((string) $declaredIntegrity, 0, 16) . "...'"
                . " but file SHA-384 is 'sha384-" . substr($actualBase64, 0, 16) . "...' (browser would refuse to execute)";
        $results['sri_hash_matches_file'] = ['passed' => $hashesMatch, 'detail' => $detail];
        $printRecord('sri_hash_matches_file', $hashesMatch, $detail);
    }
} else {
    $detail = 'cannot verify SRI hash — either pdf.min.js missing or integrity attribute absent';
    $results['sri_hash_matches_file'] = ['passed' => false, 'detail' => $detail];
    $printRecord('sri_hash_matches_file', false, $detail);
}

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
