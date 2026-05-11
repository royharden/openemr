<?php

/**
 * CLI smoke test for AgDR-0072 / Phase 6.2 — click-to-source preview drawer.
 *
 * Pure file-content smoke (no DB) pinning the JS/CSS contract for the
 * persistent right-side drawer that replaced the previous one-shot bbox
 * modal pattern. The load-bearing properties this smoke pins:
 *
 *   1. copilot.js exists at the expected vendored path.
 *   2. copilot.js renders the new DOM container literal
 *      (`class="copilot-preview-drawer"`) — guards against accidental
 *      class-name drift between JS and CSS.
 *   3. copilot.js declares `currentDrawerSource` — the state-machine
 *      anchor the spec mandates for tracking which chip is pinned.
 *   4. copilot.js exposes an `openOrUpdateDrawer` function — the
 *      "update in place, never stack" entry point.
 *   5. copilot.js exposes a `closeDrawer` function — the explicit
 *      teardown counterpart that unsets currentDrawerSource.
 *   6. copilot.js NO LONGER contains `showBboxOverlay` — regression
 *      canary that catches a partial rollback to the old modal
 *      pattern (the spec calls for the modal to be SUPERSEDED, not
 *      kept alongside the drawer).
 *   7. copilot.css contains `.copilot-preview-drawer` — keeps the JS
 *      and CSS contract in lockstep.
 *   8. copilot.css contains a media query for the mobile responsive
 *      collapse — the spec calls for a single media query to switch
 *      the drawer from a side panel to a bottom panel below 768px.
 *
 * Usage (host or container — works either way since no DB):
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/copilot_drawer_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/copilot_drawer_smoke.php --json
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

$copilotJsPath = $moduleRoot . '/public/assets/js/copilot.js';
$copilotCssPath = $moduleRoot . '/public/assets/css/copilot.css';

/** @var array<string, array<string, mixed>> $results */
$results = [];

// AgDR-0082 phpstan discipline: print-side helper is a closure (no
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
// Test 1: copilot.js exists and is readable.
// ---------------------------------------------------------------------------
if (!is_file($copilotJsPath) || !is_readable($copilotJsPath)) {
    $detail = "expected copilot.js at $copilotJsPath";
    $results['copilot_js_present'] = ['passed' => false, 'detail' => $detail];
    $printRecord('copilot_js_present', false, $detail);
    if ($jsonMode) {
        echo json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    }
    exit(1);
}
$jsSource = (string) file_get_contents($copilotJsPath);
$detail = "copilot.js found (" . strlen($jsSource) . " bytes)";
$results['copilot_js_present'] = ['passed' => true, 'detail' => $detail];
$printRecord('copilot_js_present', true, $detail);

// ---------------------------------------------------------------------------
// Test 2: drawer DOM class literal present.
// ---------------------------------------------------------------------------
$drawerClassLiteral = 'class="copilot-preview-drawer"';
$drawerClassHits = substr_count($jsSource, $drawerClassLiteral);
$passed = $drawerClassHits >= 1;
$detail = $passed
    ? "found $drawerClassHits occurrence(s) of $drawerClassLiteral"
    : "copilot.js does not emit the drawer DOM class — JS/CSS contract broken";
$results['drawer_dom_class_present'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('drawer_dom_class_present', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 3: currentDrawerSource state variable present.
// ---------------------------------------------------------------------------
$stateVarHits = substr_count($jsSource, 'currentDrawerSource');
$passed = $stateVarHits >= 1;
$detail = $passed
    ? "found $stateVarHits reference(s) to currentDrawerSource"
    : "copilot.js missing currentDrawerSource — drawer cannot pin a chip";
$results['drawer_state_variable_present'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('drawer_state_variable_present', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 4: openOrUpdateDrawer function present.
// ---------------------------------------------------------------------------
$openFnHits = preg_match('/function\s+openOrUpdateDrawer\s*\(/', $jsSource);
$passed = $openFnHits === 1;
$detail = $passed
    ? "openOrUpdateDrawer() defined in copilot.js"
    : "copilot.js missing openOrUpdateDrawer() — chip click handler has no entry point";
$results['open_or_update_drawer_fn_present'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('open_or_update_drawer_fn_present', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 5: closeDrawer function present.
// ---------------------------------------------------------------------------
$closeFnHits = preg_match('/function\s+closeDrawer\s*\(/', $jsSource);
$passed = $closeFnHits === 1;
$detail = $passed
    ? "closeDrawer() defined in copilot.js"
    : "copilot.js missing closeDrawer() — × button has no teardown handler";
$results['close_drawer_fn_present'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('close_drawer_fn_present', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 6: showBboxOverlay regression canary — old function name MUST NOT
// appear (the modal was superseded, not kept alongside the drawer).
// ---------------------------------------------------------------------------
$oldFnHits = substr_count($jsSource, 'showBboxOverlay');
$passed = $oldFnHits === 0;
$detail = $passed
    ? "no showBboxOverlay references — modal pattern fully superseded by drawer"
    : "found $oldFnHits showBboxOverlay reference(s) — partial rollback risk; spec calls for full supersession";
$results['old_modal_fn_removed'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('old_modal_fn_removed', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 7 + 8: copilot.css selector + media query.
// ---------------------------------------------------------------------------
if (!is_file($copilotCssPath) || !is_readable($copilotCssPath)) {
    $detail = "expected copilot.css at $copilotCssPath";
    $results['drawer_css_selector_present'] = ['passed' => false, 'detail' => $detail];
    $printRecord('drawer_css_selector_present', false, $detail);
} else {
    $cssSource = (string) file_get_contents($copilotCssPath);

    $cssSelectorHits = substr_count($cssSource, '.copilot-preview-drawer');
    $passed = $cssSelectorHits >= 1;
    $detail = $passed
        ? "found $cssSelectorHits .copilot-preview-drawer selector occurrence(s)"
        : "copilot.css missing .copilot-preview-drawer — drawer would render unstyled";
    $results['drawer_css_selector_present'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('drawer_css_selector_present', $passed, $detail);

    $mqHits = preg_match('/@media\s*\([^)]*max-width\s*:\s*768px/', $cssSource);
    $passed = $mqHits === 1;
    $detail = $passed
        ? "found @media (max-width: 768px) block for mobile collapse"
        : "copilot.css missing mobile collapse media query — drawer would clip on phones";
    $results['drawer_css_media_query_present'] = ['passed' => $passed, 'detail' => $detail];
    $printRecord('drawer_css_media_query_present', $passed, $detail);
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
