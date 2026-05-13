<?php

/**
 * CLI smoke test for AgDR-0077 / Plan §6.3 — medication-list upload wiring.
 *
 * Pure file-content smoke: no DB / sidecar access. Asserts that:
 *
 *   1. public/api/upload_medication_list.php exists, declares strict_types,
 *      and delegates to copilot_upload_handle('medication_list').
 *
 *   2. public/api/upload_common.php has a `medication_list` dispatch branch
 *      that calls `$controller->uploadMedicationList(...)` (mirrors the
 *      lab_pdf / intake_form branches).
 *
 *   3. DocumentUploadController.php exposes a public `uploadMedicationList`
 *      method that posts to `/v1/extract/medication-list` and persists via
 *      DocumentFactsRepository (same shape as `uploadLabPdf`).
 *
 *   4. PanelController.php registers the medication-list upload URL, the
 *      reconciliation URL, the `<option value="medication_list">` in the
 *      doc-type selector, and the `#copilot-medication-reconciliation`
 *      container.
 *
 *   5. copilot.js routes a `medication_list` doc_type through
 *      `cfg.uploadMedicationListUrl` and calls `fetchMedicationReconciliation`
 *      on successful upload.
 *
 * No DB access required.
 *
 * Usage (host or container):
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/medication_list_upload_smoke.php
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

$endpoint = $moduleRoot . '/public/api/upload_medication_list.php';
$dispatcher = $moduleRoot . '/public/api/upload_common.php';
$controller = $moduleRoot . '/src/Controller/DocumentUploadController.php';
$panelController = $moduleRoot . '/src/Controller/PanelController.php';
$copilotJs = $moduleRoot . '/public/assets/js/copilot.js';

// phpstan openemr.noGlobalNsFunctions forbids global-namespace function
// declarations. Closure-by-reference (`array &$failures`) erases the
// list<string> type at every call site under phpstan-level-10 (see
// agentdocs/agent_lessons.md 2026-05-11T20:30Z + 2026-05-13T03:10Z, AND
// the canonical reference at lab_trends_endpoint_smoke.php which uses
// the anonymous-class pattern below). An anonymous class with a typed
// property keeps types intact end-to-end.
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
};

// -----------------------------------------------------------------
// Test 1 — endpoint file present and delegates to upload_common.
// -----------------------------------------------------------------
$smokeAssert->fileContains($endpoint, [
    "declare(strict_types=1);",
    "require_once(__DIR__ . '/upload_common.php');",
    "copilot_upload_handle('medication_list');",
]);

// -----------------------------------------------------------------
// Test 2 — dispatcher routes `medication_list` to the controller.
// -----------------------------------------------------------------
$smokeAssert->fileContains($dispatcher, [
    "elseif (\$docType === 'medication_list')",
    "\$controller->uploadMedicationList(",
]);

// -----------------------------------------------------------------
// Test 3 — controller method exposed and posts to the right sidecar path.
// -----------------------------------------------------------------
$smokeAssert->fileContains($controller, [
    "public function uploadMedicationList(",
    "/v1/extract/medication-list",
    // persistExtractedDocument call lives in this method too (mirror lab/intake)
    "\$this->repository->persistExtractedDocument(",
]);

// -----------------------------------------------------------------
// Test 4 — panel wires upload URL, reconciliation URL, option, container.
// -----------------------------------------------------------------
$smokeAssert->fileContains($panelController, [
    "\$apiUploadMedicationListUrl = \$webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/upload_medication_list.php';",
    "\$apiMedicationReconciliationUrl = \$webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/medication_reconciliation.php';",
    'uploadMedicationListUrl: <?php echo js_escape($apiUploadMedicationListUrl); ?>,',
    'medicationReconciliationUrl: <?php echo js_escape($apiMedicationReconciliationUrl); ?>,',
    '<option value="medication_list">',
    'id="copilot-medication-reconciliation"',
]);

// -----------------------------------------------------------------
// Test 5 — copilot.js routes doc_type=medication_list correctly.
// -----------------------------------------------------------------
$smokeAssert->fileContains($copilotJs, [
    "var isMedicationList = (docType === 'medication_list');",
    "url = cfg.uploadMedicationListUrl;",
    "function fetchMedicationReconciliation()",
    "cfg.medicationReconciliationUrl",
    "renderMedicationReconciliation(",
]);

// -----------------------------------------------------------------
// Report
// -----------------------------------------------------------------
if ($smokeAssert->failures !== []) {
    fwrite(STDERR, "medication_list_upload_smoke: " . count($smokeAssert->failures) . " failure(s):\n");
    foreach ($smokeAssert->failures as $f) {
        fwrite(STDERR, "  - " . $f . "\n");
    }
    exit(1);
}

echo "medication_list_upload_smoke: ALL PASSED\n";
exit(0);
