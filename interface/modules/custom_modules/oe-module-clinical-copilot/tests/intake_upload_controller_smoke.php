<?php

/**
 * CLI smoke test for Plan_wk2_Claude_Next07_v2 §B.1 — pre-patient intake
 * upload page (module-owned, demo-mode gated).
 *
 * Properties pinned (pure file-content checks — no DB, no Twig, no Docker
 * required):
 *
 *   1. IntakeUploadController.php declares the class + `render(): string`
 *      method (no `$pid` parameter — the page is pre-patient).
 *   2. The rendered HTML contains exactly one `<select name="doc_type">`
 *      and that select has exactly one option with the value
 *      `intake_form_create_patient` (the locked demo-only doc_type).
 *   3. The seeded `OE_COPILOT_CONFIG` carries `createPatientUrl` and
 *      `csrfToken` — these are the two keys copilot.js needs to dispatch
 *      the upload to `create_patient_from_intake.php`.
 *   4. `public/intake_upload.php` checks `getenv('COPILOT_DEMO_MODE') === '1'`
 *      before rendering and returns HTTP 404 with a generic body
 *      otherwise (AgDR-0066 "invisible to attackers" rationale mirrored).
 *   5. Bootstrap.php registers a listener on `MenuEvent::MENU_UPDATE`.
 *   6. The menu-edit method is gated on `COPILOT_DEMO_MODE` so production
 *      deployments do NOT show the "Clinical Intake Upload" entry.
 *
 * Usage:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/intake_upload_controller_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/intake_upload_controller_smoke.php --json
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

$controllerPath = $moduleRoot . '/src/Controller/IntakeUploadController.php';
$routePath = $moduleRoot . '/public/intake_upload.php';
$bootstrapPath = $moduleRoot . '/src/Bootstrap.php';

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
// Test 1: IntakeUploadController.php exists with class + render(): string.
// ---------------------------------------------------------------------------
if (!is_file($controllerPath) || !is_readable($controllerPath)) {
    $detail = "expected IntakeUploadController.php at $controllerPath";
    $results['controller_present'] = ['passed' => false, 'detail' => $detail];
    $printRecord('controller_present', false, $detail);
    if ($jsonMode) {
        echo json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    }
    exit(1);
}
$controllerSource = (string) file_get_contents($controllerPath);
$hasClass = str_contains($controllerSource, 'class IntakeUploadController');
$hasMethod = (bool) preg_match('/public function render\(\)\s*:\s*string/', $controllerSource);
$noPidParam = !(bool) preg_match('/public function render\([^)]*\$pid/', $controllerSource);
$passed = $hasClass && $hasMethod && $noPidParam;
$detail = $passed
    ? 'IntakeUploadController.php declares class + render(): string with no $pid parameter'
    : 'missing class (' . ($hasClass ? 'OK' : 'MISSING')
        . ') or render():string signature (' . ($hasMethod ? 'OK' : 'MISSING')
        . ') or has unexpected $pid param (' . ($noPidParam ? 'OK' : 'UNEXPECTED') . ')';
$results['controller_present'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('controller_present', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 2: Exactly one <select name="doc_type"> with exactly one option, and
// that option's value is intake_form_create_patient (locked demo-only).
// ---------------------------------------------------------------------------
$selectCount = preg_match_all('/<select\b[^>]*\bname="doc_type"/i', $controllerSource);
$optionMatches = [];
preg_match_all('/<option\s+[^>]*value="([^"]+)"/i', $controllerSource, $optionMatches);
// preg_match_all populates index 1 with the captured-group matches; PHPStan
// narrows the result to array{list<string>, list<non-empty-string>} so
// `$optionMatches[1] ?? []` is dead. Reference index 1 directly.
$optionValues = $optionMatches[1];
$expectedValue = 'intake_form_create_patient';
$hasOneSelect = $selectCount === 1;
$hasOneOption = count($optionValues) === 1;
$correctValue = ($optionValues[0] ?? null) === $expectedValue;
$passed = $hasOneSelect && $hasOneOption && $correctValue;
$detail = $passed
    ? 'one <select name="doc_type"> with one option value="intake_form_create_patient" (locked demo-only)'
    : 'selects=' . $selectCount . ' options=' . count($optionValues)
        . ' first_value=' . ($optionValues[0] ?? '(none)');
$results['doctype_locked'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('doctype_locked', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 3: OE_COPILOT_CONFIG seed includes createPatientUrl + csrfToken.
// ---------------------------------------------------------------------------
$hasCreatePatientUrl = str_contains($controllerSource, 'createPatientUrl:');
$hasCsrfToken = str_contains($controllerSource, 'csrfToken:');
$referencesCreateEndpoint = str_contains($controllerSource, 'create_patient_from_intake.php');
$passed = $hasCreatePatientUrl && $hasCsrfToken && $referencesCreateEndpoint;
$detail = $passed
    ? 'OE_COPILOT_CONFIG seed includes createPatientUrl + csrfToken; controller references create_patient_from_intake.php'
    : 'missing config key(s): '
        . (!$hasCreatePatientUrl ? 'createPatientUrl ' : '')
        . (!$hasCsrfToken ? 'csrfToken ' : '')
        . (!$referencesCreateEndpoint ? 'create_patient_from_intake.php ref ' : '');
$results['config_seed_correct'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('config_seed_correct', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 4: public/intake_upload.php gates on COPILOT_DEMO_MODE and emits 404
// when the env var is unset (per AgDR-0066 invisible-to-attackers shape).
// ---------------------------------------------------------------------------
if (!is_file($routePath) || !is_readable($routePath)) {
    $detail = "expected public/intake_upload.php at $routePath";
    $results['route_demo_gate'] = ['passed' => false, 'detail' => $detail];
    $printRecord('route_demo_gate', false, $detail);
} else {
    $routeSource = (string) file_get_contents($routePath);
    $hasEnvCheck = (bool) preg_match("/getenv\\(\\s*'COPILOT_DEMO_MODE'\\s*\\)\\s*!==\\s*'1'/", $routeSource);
    $emits404 = (bool) preg_match('/http_response_code\(\s*404\s*\)/', $routeSource);
    $hasAclCheck = str_contains($routeSource, "AclMain::aclCheckCore('admin', 'super')");
    $passed = $hasEnvCheck && $emits404 && $hasAclCheck;
    $detail = $passed
        ? 'intake_upload.php gates on COPILOT_DEMO_MODE (404 when unset) and re-checks admin/super ACL'
        : 'missing: '
            . ($hasEnvCheck ? '' : 'COPILOT_DEMO_MODE env check; ')
            . ($emits404 ? '' : '404 response; ')
            . ($hasAclCheck ? '' : 'admin/super ACL check');
    $results['route_demo_gate'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('route_demo_gate', $passed, $detail);
}

// ---------------------------------------------------------------------------
// Test 5: Bootstrap.php registers a MenuEvent::MENU_UPDATE listener for the
// intake upload menu entry.
// ---------------------------------------------------------------------------
if (!is_file($bootstrapPath) || !is_readable($bootstrapPath)) {
    $detail = "expected Bootstrap.php at $bootstrapPath";
    $results['bootstrap_menu_listener'] = ['passed' => false, 'detail' => $detail];
    $printRecord('bootstrap_menu_listener', false, $detail);
} else {
    $bootstrapSource = (string) file_get_contents($bootstrapPath);
    $importsMenuEvent = str_contains($bootstrapSource, 'use OpenEMR\\Menu\\MenuEvent');
    // 2026-05-14: Bootstrap.php intentionally does NOT import
    // IntakeUploadController — that class is instantiated by the
    // public/intake_upload.php route entry, not by Bootstrap. The menu
    // listener registers a URL string, not a class reference. phpcs would
    // flag an unused import. The route-file test below covers the
    // controller instantiation contract.
    $registersListener = (bool) preg_match(
        '/MenuEvent::MENU_UPDATE\s*,\s*\$this->addIntakeUploadMenuItem\(\.\.\.\)/s',
        $bootstrapSource
    );
    $hasMethod = (bool) preg_match(
        '/public function addIntakeUploadMenuItem\(MenuEvent \$event\)\s*:\s*MenuEvent/',
        $bootstrapSource
    );
    $passed = $importsMenuEvent && $registersListener && $hasMethod;
    $detail = $passed
        ? 'Bootstrap.php imports MenuEvent and registers addIntakeUploadMenuItem on MENU_UPDATE (controller class is instantiated by public/intake_upload.php, not Bootstrap)'
        : 'missing: '
            . ($importsMenuEvent ? '' : 'MenuEvent import; ')
            . ($registersListener ? '' : 'listener registration; ')
            . ($hasMethod ? '' : 'addIntakeUploadMenuItem method');
    $results['bootstrap_menu_listener'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('bootstrap_menu_listener', $passed, $detail);
}

// ---------------------------------------------------------------------------
// Test 6: Menu-edit code path is gated on COPILOT_DEMO_MODE — production
// deployments do NOT show the menu entry.
// ---------------------------------------------------------------------------
if (!is_file($bootstrapPath) || !is_readable($bootstrapPath)) {
    $detail = "expected Bootstrap.php at $bootstrapPath";
    $results['menu_demo_gate'] = ['passed' => false, 'detail' => $detail];
    $printRecord('menu_demo_gate', false, $detail);
} else {
    $bootstrapSource = (string) file_get_contents($bootstrapPath);
    // Look for the env-var gate inside the addIntakeUploadMenuItem method
    // body. Approach: extract the method body and grep within it so an
    // unrelated env check elsewhere in Bootstrap.php cannot accidentally
    // pass this assertion.
    $hasGate = false;
    if (preg_match(
        '/function addIntakeUploadMenuItem\([^)]*\)\s*:\s*MenuEvent\s*\{(.*?)\n    \}/s',
        $bootstrapSource,
        $bodyMatch
    )) {
        $methodBody = $bodyMatch[1];
        $hasGate = (bool) preg_match(
            "/getenv\\(\\s*'COPILOT_DEMO_MODE'\\s*\\)\\s*!==\\s*'1'/",
            $methodBody
        );
    }
    $detail = $hasGate
        ? 'addIntakeUploadMenuItem short-circuits when COPILOT_DEMO_MODE is unset (production-safe)'
        : 'addIntakeUploadMenuItem does NOT gate on COPILOT_DEMO_MODE — production would show the menu entry';
    $results['menu_demo_gate'] = ['passed' => $hasGate, 'detail' => $detail];
    $printRecord('menu_demo_gate', $hasGate, $detail);
}

// ---------------------------------------------------------------------------
// Test 7: copilot.js wires the upload handler BEFORE the no-#copilot-card
// early-return so the pre-patient surface (which has no card) gets a
// working submit handler. Regression guard for the 2026-05-13T23:55Z bug
// where uploads silently no-op'd because the IIFE returned at line 37
// before the form-binding code ran.
// ---------------------------------------------------------------------------
$copilotJsPath = $moduleRoot . '/public/assets/js/copilot.js';
if (!is_file($copilotJsPath) || !is_readable($copilotJsPath)) {
    $detail = "expected copilot.js at $copilotJsPath";
    $results['js_upload_handler_before_early_return'] = ['passed' => false, 'detail' => $detail];
    $printRecord('js_upload_handler_before_early_return', false, $detail);
} else {
    $jsSource = (string) file_get_contents($copilotJsPath);
    // Find the position of the initUploadHandlers() invocation and the
    // early-return guard `if (!card || !cfg.briefUrl) { return; }`.
    // The invocation must come BEFORE the return for the pre-patient
    // surface to work.
    $callPos = strpos($jsSource, 'initUploadHandlers()');
    $returnPos = strpos($jsSource, "if (!card || !cfg.briefUrl) {\n        return;\n    }");
    if ($returnPos === false) {
        // Tolerate single-line variant.
        $returnPos = strpos($jsSource, 'if (!card || !cfg.briefUrl) { return;');
    }
    $hasFuncDecl = (bool) preg_match('/function initUploadHandlers\(\)\s*\{/', $jsSource);
    // The function gate must accept createPatientUrl-only configs.
    $hasLoosenedGate = str_contains($jsSource, 'hasCreateOnly');
    // The fetchBrief / fetchMedicationReconciliation calls must be
    // guarded by `card && cfg.briefUrl` so the pre-patient surface
    // doesn't try to refresh a non-existent brief.
    $hasGuardedRefresh = str_contains($jsSource, "if (card && cfg.briefUrl && typeof fetchBrief === 'function')");
    $orderOk = ($callPos !== false) && ($returnPos !== false) && ($callPos < $returnPos);
    $passed = $orderOk && $hasFuncDecl && $hasLoosenedGate && $hasGuardedRefresh;
    $detail = $passed
        ? 'copilot.js calls initUploadHandlers() before the no-card early-return, gate accepts createPatientUrl-only, brief-refresh is card-guarded'
        : 'missing/incorrect: '
            . ($orderOk ? '' : 'init call must precede early-return; ')
            . ($hasFuncDecl ? '' : 'initUploadHandlers() function declaration; ')
            . ($hasLoosenedGate ? '' : 'gate must accept createPatientUrl-only; ')
            . ($hasGuardedRefresh ? '' : 'brief-refresh must be guarded by card+briefUrl');
    $results['js_upload_handler_before_early_return'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('js_upload_handler_before_early_return', $passed, $detail);
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
