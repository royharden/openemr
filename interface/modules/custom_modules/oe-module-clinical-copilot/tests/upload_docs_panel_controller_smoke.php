<?php

/**
 * CLI smoke test for Plan_wk2_Claude_Next06 — split-upload-docs-card.
 *
 * Verifies that the standalone "Upload documents" card is wired correctly
 * and that the existing Co-Pilot card's upload form is untouched. Pure
 * file-content checks — no DB, no Twig, no Docker required.
 *
 * Properties pinned:
 *   1. UploadDocsController.php exists with the expected class + method.
 *   2. The new card emits class="copilot-upload-form" (the JS contract that
 *      lets copilot.js wire up every form on the page).
 *   3. The new card uses id="copilot-upload-form-top" — distinct from the
 *      Co-Pilot card's id="copilot-upload-form" so HTML id-uniqueness holds.
 *   4. The new card references all four upload backend URLs in its
 *      seeded OE_COPILOT_CONFIG (lab / intake / medication / create-patient).
 *   5. Bootstrap.php registers a single renderTopRow listener on
 *      EVENT_SECTION_LIST_RENDER_BEFORE and emits id="copilot-top-row"
 *      with the col-md-8 / col-md-4 split (Co-Pilot 2/3 left, Upload 1/3
 *      right). Plan_wk2_Claude_Next06 refinement 2026-05-13.
 *   6. copilot.js wires upload forms by class — querySelectorAll('form.copilot-upload-form')
 *      — and no longer relies on getElementById('copilot-upload-form').
 *   7. PanelController.php still contains id="copilot-upload-form" — the
 *      embedded form in the Co-Pilot card is intentionally preserved
 *      (regression guard for the user's "keep it in there" direction).
 *   8. PanelController.php defaults the doc-type dropdown back to lab upload
 *      and uses the broadened Upload Labs / Upload Medications labels.
 *   9. copilot.js carries the DOMContentLoaded relocation that hoists
 *      #copilot-top-row above the Allergies / Medical Problems /
 *      Medications three-card row (the user's preferred placement).
 *
 * Usage (host or container — no DB):
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/upload_docs_panel_controller_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/upload_docs_panel_controller_smoke.php --json
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

$uploadDocsControllerPath = $moduleRoot . '/src/Controller/UploadDocsController.php';
$panelControllerPath = $moduleRoot . '/src/Controller/PanelController.php';
$bootstrapPath = $moduleRoot . '/src/Bootstrap.php';
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
// Test 1: UploadDocsController.php exists with class + renderPanel method.
// ---------------------------------------------------------------------------
if (!is_file($uploadDocsControllerPath) || !is_readable($uploadDocsControllerPath)) {
    $detail = "expected UploadDocsController.php at $uploadDocsControllerPath";
    $results['controller_present'] = ['passed' => false, 'detail' => $detail];
    $printRecord('controller_present', false, $detail);
    if ($jsonMode) {
        echo json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    }
    exit(1);
}
$controllerSource = (string) file_get_contents($uploadDocsControllerPath);
$hasClass = str_contains($controllerSource, 'class UploadDocsController');
$hasMethod = str_contains($controllerSource, 'public function renderPanel(int $pid): string');
$passed = $hasClass && $hasMethod;
$detail = $passed
    ? "UploadDocsController.php declares class + renderPanel(int): string"
    : "missing class declaration (" . ($hasClass ? 'OK' : 'MISSING')
        . ") or renderPanel signature (" . ($hasMethod ? 'OK' : 'MISSING') . ')';
$results['controller_present'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('controller_present', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 2: New card emits class="copilot-upload-form" (the JS wiring contract).
// ---------------------------------------------------------------------------
$hasFormClass = (bool) preg_match('/class="copilot-upload-form[^"]*"/', $controllerSource);
$detail = $hasFormClass
    ? 'UploadDocsController emits class="copilot-upload-form" — copilot.js will wire it'
    : 'UploadDocsController does not emit class="copilot-upload-form" — JS handler will not attach';
$results['form_class_present'] = ['passed' => $hasFormClass, 'detail' => $detail];
$printRecord('form_class_present', $hasFormClass, $detail);

// ---------------------------------------------------------------------------
// Test 3: New card uses id="copilot-upload-form-top" (distinct from old card).
// ---------------------------------------------------------------------------
$hasTopId = str_contains($controllerSource, 'id="copilot-upload-form-top"');
$detail = $hasTopId
    ? 'UploadDocsController uses id="copilot-upload-form-top" — no ID collision with Co-Pilot card'
    : 'UploadDocsController is missing id="copilot-upload-form-top" — risks duplicate ID with PanelController';
$results['form_id_distinct'] = ['passed' => $hasTopId, 'detail' => $detail];
$printRecord('form_id_distinct', $hasTopId, $detail);

// ---------------------------------------------------------------------------
// Test 4: Four upload URLs referenced in the new card's config.
// ---------------------------------------------------------------------------
$requiredEndpoints = ['upload_lab.php', 'upload_intake.php', 'upload_medication_list.php', 'create_patient_from_intake.php'];
$missingEndpoints = [];
foreach ($requiredEndpoints as $endpoint) {
    if (!str_contains($controllerSource, $endpoint)) {
        $missingEndpoints[] = $endpoint;
    }
}
$allPresent = $missingEndpoints === [];
$detail = $allPresent
    ? 'all four upload endpoints referenced in UploadDocsController'
    : 'missing endpoint reference(s): ' . implode(', ', $missingEndpoints);
$results['upload_endpoints_present'] = ['passed' => $allPresent, 'detail' => $detail];
$printRecord('upload_endpoints_present', $allPresent, $detail);

// ---------------------------------------------------------------------------
// Test 5: Bootstrap.php registers renderTopRow on EVENT_SECTION_LIST_RENDER_BEFORE
// emits id="copilot-top-row" with the Co-Pilot card as a full-width child.
//
// Plan_wk2_Claude_Next07_v2 follow-up (Roy decision 2026-05-14): the
// standalone Upload Documents card is DEACTIVATED. Bootstrap.php still
// imports UploadDocsController (file preserved for future Patient
// Documents reintegration) but does NOT invoke its renderPanel() — the
// invocation is commented out. The top-row now renders Co-Pilot only.
// ---------------------------------------------------------------------------
if (!is_file($bootstrapPath) || !is_readable($bootstrapPath)) {
    $detail = "expected Bootstrap.php at $bootstrapPath";
    $results['bootstrap_top_row'] = ['passed' => false, 'detail' => $detail];
    $printRecord('bootstrap_top_row', false, $detail);
} else {
    $bootstrapSource = (string) file_get_contents($bootstrapPath);
    // Strip comments to make the assertions test executable code only —
    // otherwise our deactivation comment block satisfies the str_contains
    // greps and the test gives a false-positive pass.
    $bootstrapCode = preg_replace('!//.*$!m', '', $bootstrapSource);
    $bootstrapCode = preg_replace('!/\*.*?\*/!s', '', (string) $bootstrapCode);
    $usesPanelController = str_contains((string) $bootstrapCode, 'new PanelController()');
    $hasRenderTopRow = (bool) preg_match('/function renderTopRow\(RenderEvent \$event\)/s', $bootstrapSource);
    $hasListener = (bool) preg_match('/EVENT_SECTION_LIST_RENDER_BEFORE\s*,\s*\$this->renderTopRow\(\.\.\.\)/s', $bootstrapSource);
    $emitsRowId = str_contains((string) $bootstrapCode, 'id="copilot-top-row"');
    // Deactivation: UploadDocsController must NOT be invoked from
    // executable code. The class import / file may still exist.
    $invokesUploadDocs = (bool) preg_match('/new UploadDocsController\(\)/', (string) $bootstrapCode);
    $passed = $usesPanelController && $hasRenderTopRow && $hasListener && $emitsRowId && !$invokesUploadDocs;
    $missing = [];
    if (!$usesPanelController)      { $missing[] = 'PanelController instantiation in executable code'; }
    if (!$hasRenderTopRow)          { $missing[] = 'renderTopRow method'; }
    if (!$hasListener)              { $missing[] = 'renderTopRow listener registration'; }
    if (!$emitsRowId)               { $missing[] = 'id="copilot-top-row" in executable code'; }
    if ($invokesUploadDocs)         { $missing[] = 'UploadDocsController invocation (must be deactivated)'; }
    $detail = $passed
        ? 'Bootstrap.php renders Co-Pilot top-row only; UploadDocsController invocation is deactivated (commented)'
        : 'missing/incorrect: ' . implode(', ', $missing);
    $results['bootstrap_top_row'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('bootstrap_top_row', $passed, $detail);
}

// ---------------------------------------------------------------------------
// Test 6: copilot.js wires upload forms by class, not by single ID.
// ---------------------------------------------------------------------------
if (!is_file($copilotJsPath) || !is_readable($copilotJsPath)) {
    $detail = "expected copilot.js at $copilotJsPath";
    $results['js_class_wiring'] = ['passed' => false, 'detail' => $detail];
    $printRecord('js_class_wiring', false, $detail);
} else {
    $jsSource = (string) file_get_contents($copilotJsPath);
    $hasQuerySelectorAll = str_contains($jsSource, "querySelectorAll('form.copilot-upload-form')");
    $hasOldGetElementById = (bool) preg_match("/getElementById\\(\\s*['\"]copilot-upload-form['\"]\\s*\\)/", $jsSource);
    $passed = $hasQuerySelectorAll && !$hasOldGetElementById;
    $detail = $passed
        ? 'copilot.js iterates form.copilot-upload-form and no longer relies on getElementById'
        : 'expected querySelectorAll wiring (' . ($hasQuerySelectorAll ? 'OK' : 'MISSING')
            . ') and absence of stale getElementById (' . ($hasOldGetElementById ? 'STILL PRESENT' : 'OK') . ')';
    $results['js_class_wiring'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('js_class_wiring', $passed, $detail);
}

// ---------------------------------------------------------------------------
// Test 7: PanelController.php still emits id="copilot-upload-form" (regression
// guard — user direction: keep the embedded form in the Co-Pilot card).
// ---------------------------------------------------------------------------
if (!is_file($panelControllerPath) || !is_readable($panelControllerPath)) {
    $detail = "expected PanelController.php at $panelControllerPath";
    $results['panel_form_preserved'] = ['passed' => false, 'detail' => $detail];
    $printRecord('panel_form_preserved', false, $detail);
} else {
    $panelSource = (string) file_get_contents($panelControllerPath);
    $stillHasForm = str_contains($panelSource, 'id="copilot-upload-form"');
    $detail = $stillHasForm
        ? 'PanelController.php still emits id="copilot-upload-form" — embedded form preserved'
        : 'PanelController.php no longer emits id="copilot-upload-form" — the embedded form was removed against plan direction';
    $results['panel_form_preserved'] = ['passed' => $stillHasForm, 'detail' => $detail];
    $printRecord('panel_form_preserved', $stillHasForm, $detail);
}

// ---------------------------------------------------------------------------
// Test 8: PanelController.php defaults the document-type selector back to
// lab upload, and the labels match the PDF+image upload behavior.
// ---------------------------------------------------------------------------
if (!is_file($panelControllerPath) || !is_readable($panelControllerPath)) {
    $detail = "expected PanelController.php at $panelControllerPath";
    $results['panel_lab_default_labels'] = ['passed' => false, 'detail' => $detail];
    $printRecord('panel_lab_default_labels', false, $detail);
} else {
    $panelSource = (string) file_get_contents($panelControllerPath);
    $hasSelectedLab = str_contains($panelSource, '<option value="lab_pdf" selected><?php echo xlt(\'Upload Labs\'); ?></option>');
    $hasUploadMedicationLabel = str_contains($panelSource, '<option value="medication_list"><?php echo xlt(\'Upload Medications\'); ?></option>');
    $demoIntakeSelected = str_contains($panelSource, '<option value="intake_form_create_patient" selected>');
    $passed = $hasSelectedLab && $hasUploadMedicationLabel && !$demoIntakeSelected;
    $detail = $passed
        ? 'PanelController doc-type dropdown defaults to Upload Labs and leaves create-patient intake unselected'
        : 'expected selected Upload Labs label, Upload Medications label, and unselected create-patient intake option';
    $results['panel_lab_default_labels'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('panel_lab_default_labels', $passed, $detail);
}

// ---------------------------------------------------------------------------
// Test 9: copilot.js carries the relocateTopRow() hoister and binds it to
// DOMContentLoaded (or runs it immediately if the document is already
// parsed). The hoister is what places #copilot-top-row above the
// Allergies / Medical Problems / Medications three-card row.
// ---------------------------------------------------------------------------
if (!is_file($copilotJsPath) || !is_readable($copilotJsPath)) {
    $detail = "expected copilot.js at $copilotJsPath";
    $results['js_top_row_relocation'] = ['passed' => false, 'detail' => $detail];
    $printRecord('js_top_row_relocation', false, $detail);
} else {
    $jsSource = (string) file_get_contents($copilotJsPath);
    $hasRelocateFn = str_contains($jsSource, 'function relocateTopRow()');
    $hasTopRowRef = str_contains($jsSource, "getElementById('copilot-top-row')");
    $hasDomReadyHook = str_contains($jsSource, "addEventListener('DOMContentLoaded', relocateTopRow)")
        || str_contains($jsSource, 'document.readyState');
    $passed = $hasRelocateFn && $hasTopRowRef && $hasDomReadyHook;
    $detail = $passed
        ? 'copilot.js defines relocateTopRow() and runs it on DOMContentLoaded (or immediately)'
        : 'missing: '
            . ($hasRelocateFn ? '' : 'relocateTopRow fn; ')
            . ($hasTopRowRef ? '' : 'copilot-top-row lookup; ')
            . ($hasDomReadyHook ? '' : 'DOMContentLoaded binding');
    $results['js_top_row_relocation'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('js_top_row_relocation', $passed, $detail);
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
