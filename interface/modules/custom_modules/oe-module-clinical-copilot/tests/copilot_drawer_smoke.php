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

/**
 * @param array<string, array<string, mixed>> $report
 */
$record = static function (array &$report, string $name, bool $passed, string $detail) use ($jsonMode): void {
    $report[$name] = ['passed' => $passed, 'detail' => $detail];
    if (!$jsonMode) {
        $tag = $passed ? '[PASS]' : '[FAIL]';
        echo $tag . ' ' . $name . "\n        " . $detail . "\n";
    }
};

// ---------------------------------------------------------------------------
// Test 1: copilot.js exists and is readable.
// ---------------------------------------------------------------------------
if (!is_file($copilotJsPath) || !is_readable($copilotJsPath)) {
    $record($results, 'copilot_js_present', false, "expected copilot.js at $copilotJsPath");
    if ($jsonMode) {
        echo json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    }
    exit(1);
}
$jsSource = (string) file_get_contents($copilotJsPath);
$record($results, 'copilot_js_present', true, "copilot.js found (" . strlen($jsSource) . " bytes)");

// ---------------------------------------------------------------------------
// Test 2: drawer DOM class literal present.
// ---------------------------------------------------------------------------
$drawerClassLiteral = 'class="copilot-preview-drawer"';
$drawerClassHits = substr_count($jsSource, $drawerClassLiteral);
$record(
    $results,
    'drawer_dom_class_present',
    $drawerClassHits >= 1,
    $drawerClassHits >= 1
        ? "found $drawerClassHits occurrence(s) of $drawerClassLiteral"
        : "copilot.js does not emit the drawer DOM class — JS/CSS contract broken"
);

// ---------------------------------------------------------------------------
// Test 3: currentDrawerSource state variable present.
// ---------------------------------------------------------------------------
$stateVarHits = substr_count($jsSource, 'currentDrawerSource');
$record(
    $results,
    'drawer_state_variable_present',
    $stateVarHits >= 1,
    $stateVarHits >= 1
        ? "found $stateVarHits reference(s) to currentDrawerSource"
        : "copilot.js missing currentDrawerSource — drawer cannot pin a chip"
);

// ---------------------------------------------------------------------------
// Test 4: openOrUpdateDrawer function present.
// ---------------------------------------------------------------------------
$openFnHits = preg_match('/function\s+openOrUpdateDrawer\s*\(/', $jsSource);
$record(
    $results,
    'open_or_update_drawer_fn_present',
    $openFnHits === 1,
    $openFnHits === 1
        ? "openOrUpdateDrawer() defined in copilot.js"
        : "copilot.js missing openOrUpdateDrawer() — chip click handler has no entry point"
);

// ---------------------------------------------------------------------------
// Test 5: closeDrawer function present.
// ---------------------------------------------------------------------------
$closeFnHits = preg_match('/function\s+closeDrawer\s*\(/', $jsSource);
$record(
    $results,
    'close_drawer_fn_present',
    $closeFnHits === 1,
    $closeFnHits === 1
        ? "closeDrawer() defined in copilot.js"
        : "copilot.js missing closeDrawer() — × button has no teardown handler"
);

// ---------------------------------------------------------------------------
// Test 6: showBboxOverlay regression canary — old function name MUST NOT
// appear (the modal was superseded, not kept alongside the drawer).
// ---------------------------------------------------------------------------
$oldFnHits = substr_count($jsSource, 'showBboxOverlay');
$record(
    $results,
    'old_modal_fn_removed',
    $oldFnHits === 0,
    $oldFnHits === 0
        ? "no showBboxOverlay references — modal pattern fully superseded by drawer"
        : "found $oldFnHits showBboxOverlay reference(s) — partial rollback risk; spec calls for full supersession"
);

// ---------------------------------------------------------------------------
// Test 7: copilot.css contains the drawer selector.
// ---------------------------------------------------------------------------
if (!is_file($copilotCssPath) || !is_readable($copilotCssPath)) {
    $record($results, 'drawer_css_selector_present', false, "expected copilot.css at $copilotCssPath");
} else {
    $cssSource = (string) file_get_contents($copilotCssPath);
    $cssSelectorHits = substr_count($cssSource, '.copilot-preview-drawer');
    $record(
        $results,
        'drawer_css_selector_present',
        $cssSelectorHits >= 1,
        $cssSelectorHits >= 1
            ? "found $cssSelectorHits .copilot-preview-drawer selector occurrence(s)"
            : "copilot.css missing .copilot-preview-drawer — drawer would render unstyled"
    );

    // -----------------------------------------------------------------------
    // Test 8: copilot.css contains a media query for mobile collapse.
    // -----------------------------------------------------------------------
    $mqHits = preg_match('/@media\s*\([^)]*max-width\s*:\s*768px/', $cssSource);
    $record(
        $results,
        'drawer_css_media_query_present',
        $mqHits === 1,
        $mqHits === 1
            ? "found @media (max-width: 768px) block for mobile collapse"
            : "copilot.css missing mobile collapse media query — drawer would clip on phones"
    );
}

// ---------------------------------------------------------------------------
// Summary.
// ---------------------------------------------------------------------------
$passed = count(array_filter($results, static fn(array $r): bool => (bool) $r['passed']));
$total = count($results);

if ($jsonMode) {
    echo json_encode(
        ['summary' => ['passed' => $passed, 'total' => $total], 'tests' => $results],
        JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES
    ) . "\n";
} else {
    echo "\n--- $passed/$total passed ---\n";
}

exit($passed === $total ? 0 : 1);
