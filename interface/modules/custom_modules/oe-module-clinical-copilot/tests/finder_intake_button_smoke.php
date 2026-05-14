<?php

/**
 * CLI smoke test for Plan_wk2_Claude_Next07_v2 §B.2 — Patient Finder
 * PageHeading affordance.
 *
 * Properties pinned (pure file-content checks — no DB, no Twig, no
 * Docker required):
 *
 *   1. Bootstrap.php imports OpenEMR\Events\UserInterface\PageHeadingRenderEvent
 *      and registers `addFinderIntakeButton` on EVENT_PAGE_HEADING_RENDER.
 *   2. `addFinderIntakeButton` filters by `getPageId() === 'dynamic_finder'`
 *      so other pages firing the same event are not modified.
 *   3. The method gates on `COPILOT_DEMO_MODE === '1'` so the button is
 *      not emitted in production deployments.
 *   4. The injected HTML links to the module-owned
 *      `public/intake_upload.php` page and uses the documented operator
 *      copy ("Upload intake to create new patient (demo only)").
 *
 * Usage:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/finder_intake_button_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/finder_intake_button_smoke.php --json
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

if (!is_file($bootstrapPath) || !is_readable($bootstrapPath)) {
    fwrite(STDERR, "expected Bootstrap.php at $bootstrapPath\n");
    exit(1);
}
$bootstrapSource = (string) file_get_contents($bootstrapPath);

// Extract the addFinderIntakeButton method body once for downstream tests
// so each assertion scopes its grep to the method, not the whole file.
$methodBody = null;
if (preg_match(
    '/function addFinderIntakeButton\([^)]*\)\s*:\s*void\s*\{(.*?)\n    \}/s',
    $bootstrapSource,
    $bodyMatch
)) {
    $methodBody = $bodyMatch[1];
}

// ---------------------------------------------------------------------------
// Test 1: Bootstrap imports PageHeadingRenderEvent and registers the listener.
// ---------------------------------------------------------------------------
$importsEvent = str_contains(
    $bootstrapSource,
    'use OpenEMR\\Events\\UserInterface\\PageHeadingRenderEvent'
);
$registersListener = (bool) preg_match(
    '/PageHeadingRenderEvent::EVENT_PAGE_HEADING_RENDER\s*,\s*\$this->addFinderIntakeButton\(\.\.\.\)/s',
    $bootstrapSource
);
$hasMethod = (bool) preg_match(
    '/public function addFinderIntakeButton\(PageHeadingRenderEvent \$event\)\s*:\s*void/',
    $bootstrapSource
);
$passed = $importsEvent && $registersListener && $hasMethod;
$detail = $passed
    ? 'Bootstrap imports PageHeadingRenderEvent and registers addFinderIntakeButton on EVENT_PAGE_HEADING_RENDER'
    : 'missing: '
        . ($importsEvent ? '' : 'PageHeadingRenderEvent import; ')
        . ($registersListener ? '' : 'listener registration; ')
        . ($hasMethod ? '' : 'addFinderIntakeButton method');
$results['bootstrap_finder_listener'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('bootstrap_finder_listener', $passed, $detail);

// ---------------------------------------------------------------------------
// Test 2: Method filters by page_id === 'dynamic_finder'.
// ---------------------------------------------------------------------------
$hasPageIdFilter = $methodBody !== null && (bool) preg_match(
    "/\\\$event->getPageId\\(\\)\\s*!==\\s*'dynamic_finder'/",
    $methodBody
);
$detail = $hasPageIdFilter
    ? 'addFinderIntakeButton returns early unless page_id === \'dynamic_finder\''
    : 'addFinderIntakeButton does NOT filter by page_id — other pages firing the event would be modified';
$results['page_id_filter'] = ['passed' => $hasPageIdFilter, 'detail' => $detail];
$printRecord('page_id_filter', $hasPageIdFilter, $detail);

// ---------------------------------------------------------------------------
// Test 3: Method gates on COPILOT_DEMO_MODE.
// ---------------------------------------------------------------------------
$hasDemoGate = $methodBody !== null && (bool) preg_match(
    "/getenv\\(\\s*'COPILOT_DEMO_MODE'\\s*\\)\\s*!==\\s*'1'/",
    $methodBody
);
$detail = $hasDemoGate
    ? 'addFinderIntakeButton short-circuits when COPILOT_DEMO_MODE is unset (production-safe)'
    : 'addFinderIntakeButton does NOT gate on COPILOT_DEMO_MODE — production would show the button';
$results['demo_mode_gate'] = ['passed' => $hasDemoGate, 'detail' => $detail];
$printRecord('demo_mode_gate', $hasDemoGate, $detail);

// ---------------------------------------------------------------------------
// Test 4: Emitted HTML references intake_upload.php and the documented
// operator copy.
// ---------------------------------------------------------------------------
$linksToIntakePage = $methodBody !== null
    && str_contains($methodBody, '/public/intake_upload.php');
$hasButtonCopy = $methodBody !== null
    && str_contains($methodBody, 'Upload intake to create new patient (demo only)');
$injectsViaApi = $methodBody !== null
    && str_contains($methodBody, 'appendTitleNavContent(');
$passed = $linksToIntakePage && $hasButtonCopy && $injectsViaApi;
$detail = $passed
    ? 'button links to /public/intake_upload.php with the documented copy and is injected via appendTitleNavContent()'
    : 'missing: '
        . ($linksToIntakePage ? '' : 'intake_upload.php link; ')
        . ($hasButtonCopy ? '' : 'button copy; ')
        . ($injectsViaApi ? '' : 'appendTitleNavContent call');
$results['button_html'] = ['passed' => $passed, 'detail' => $detail];
$printRecord('button_html', $passed, $detail);

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
