<?php

/**
 * CLI smoke test for AgDR-0088 / Plan §7.1 — Lab Trends endpoint + widget wiring.
 *
 * Pure file-content smoke: no DB access. Asserts that:
 *
 *   1. public/api/lab_trends.php exists, declares strict_types, and
 *      uses the same session-cookie + ACL `patients/med` + patient-scope
 *      bind pattern as fhir_observation_preview.php (AgDR-0083). A
 *      regression that removes the ACL check or the pid filter would
 *      surface another patient's labs on the current chart sidebar.
 *
 *   2. The endpoint filters procedure_order rows to `notes LIKE '%[copilot-extracted%'`.
 *      Without this, the trend widget would show every lab on the chart,
 *      including ones not extracted by the Co-Pilot — which Plan §7.1
 *      explicitly scopes against.
 *
 *   3. PanelController.php includes the new lab_trends.css + lab_trends.js
 *      assets and renders the `#copilot-lab-trends` container.
 *
 *   4. PanelController.php emits a `window.OE_COPILOT_LAB_TRENDS_CONFIG`
 *      script block referencing the endpoint URL.
 *
 *   5. The widget JS lives at public/assets/js/lab_trends.js and the
 *      CSS at public/assets/css/lab_trends.css.
 *
 * No DB access required.
 *
 * Usage (host or container):
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/lab_trends_endpoint_smoke.php
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

$endpoint = $moduleRoot . '/public/api/lab_trends.php';
$controller = $moduleRoot . '/src/Controller/PanelController.php';
$widgetJs = $moduleRoot . '/public/assets/js/lab_trends.js';
$widgetCss = $moduleRoot . '/public/assets/css/lab_trends.css';

// phpstan custom rule openemr.noGlobalNsFunctions forbids global-namespace
// function declarations in module files. An anonymous class with static
// helpers gives PHPStan the typed surface it needs (call-site inference
// through closure-by-reference parameters silently degrades to `mixed`
// under phpstan-level-10 — using a class avoids that whole class of
// errors).
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
// Test 1 — endpoint file: auth + scope + provenance filter present
// -----------------------------------------------------------------
$smokeAssert->fileContains($endpoint, [
    "declare(strict_types=1);",
    "require_once(__DIR__ . \"/../../../../../globals.php\");",
    "AclMain::aclCheckCore('patients', 'med')",
    "\$session->get('pid')",
    "BaseService::getUuidById((string) \$pid, 'patient_data', 'pid')",
    'po.notes LIKE "%[copilot-extracted%"',
    'INNER JOIN `procedure_order_code` poc',
    'INNER JOIN `procedure_report` prep',
    'INNER JOIN `procedure_result` pres',
    "LEFT JOIN  `uuid_registry` ur",
    "header('Content-Type: application/json; charset=utf-8');",
    "header('X-Content-Type-Options: nosniff');",
]);

// The endpoint must NOT introduce a CSRF check — same rationale as the
// FHIR Observation preview proxy (read-only GET, same-origin session +
// ACL + scope bind is stricter than CSRF would give). If a refactor
// adds CsrfUtils here, that's a flag worth catching in review.
$smokeAssert->fileDoesNotContain(
    $endpoint,
    'CsrfUtils::verifyCsrfToken',
    'lab_trends.php is read-only GET; CSRF intentionally omitted per AgDR-0083 precedent'
);

// -----------------------------------------------------------------
// Test 2 — endpoint: parameterized SQL (no concatenated user input)
// -----------------------------------------------------------------
// The pid is bound via `?` and the optional LOINC filter is also bound.
// A regression that interpolates either into the SQL string is an
// injection vector. Pin the parameterized markers.
$smokeAssert->fileContains($endpoint, [
    'WHERE po.patient_id = ?',
    "\$params = [\$pid];",
    "\$params[] = \$loincFilter;",
    'AND poc.procedure_code = ?',
]);

$smokeAssert->fileDoesNotContain(
    $endpoint,
    "WHERE po.patient_id = \" . \$pid",
    'pid must be parameterized, not concatenated'
);
$smokeAssert->fileDoesNotContain(
    $endpoint,
    'WHERE po.patient_id = $pid',
    'pid must be parameterized via QueryUtils binding, not double-quoted interpolation'
);

// -----------------------------------------------------------------
// Test 3 — endpoint: LOINC format validation
// -----------------------------------------------------------------
$smokeAssert->fileContains($endpoint, [
    "preg_match('/^[0-9]{1,7}-[0-9]\$/', \$loincFilter)",
    "'error' => 'invalid_loinc'",
]);

// -----------------------------------------------------------------
// Test 4 — PanelController: widget wiring
// -----------------------------------------------------------------
$smokeAssert->fileContains($controller, [
    '$apiLabTrendsUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . \'/public/api/lab_trends.php\';',
    '$assetBase); ?>/css/lab_trends.css',
    '$assetBase); ?>/js/lab_trends.js',
    'id="copilot-lab-trends"',
    'window.OE_COPILOT_LAB_TRENDS_CONFIG',
    "containerId: 'copilot-lab-trends'",
    'minObservations: 3',
]);

// -----------------------------------------------------------------
// Test 5 — assets exist
// -----------------------------------------------------------------
if (!is_file($widgetJs)) {
    $smokeAssert->failures[] = "missing widget JS: $widgetJs";
} else {
    $jsContent = file_get_contents($widgetJs);
    if ($jsContent === false || !str_contains($jsContent, 'OE_COPILOT_LAB_TRENDS_CONFIG')) {
        $smokeAssert->failures[] = "lab_trends.js missing OE_COPILOT_LAB_TRENDS_CONFIG hook";
    }
    if ($jsContent !== false && !str_contains($jsContent, "credentials: 'same-origin'")) {
        $smokeAssert->failures[] = "lab_trends.js must use credentials: 'same-origin' so the session cookie reaches the endpoint";
    }
}

if (!is_file($widgetCss)) {
    $smokeAssert->failures[] = "missing widget CSS: $widgetCss";
}

// -----------------------------------------------------------------
// Report
// -----------------------------------------------------------------
if ($smokeAssert->failures !== []) {
    fwrite(STDERR, "lab_trends_endpoint_smoke: " . count($smokeAssert->failures) . " failure(s):\n");
    foreach ($smokeAssert->failures as $f) {
        fwrite(STDERR, "  - " . $f . "\n");
    }
    exit(1);
}

echo "lab_trends_endpoint_smoke: ALL PASSED\n";
exit(0);
