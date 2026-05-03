<?php

/**
 * CLI smoke test for Clinical Co-Pilot agent-turn audit logging.
 *
 * Usage from the openemr container:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/agent_turn_auditor_smoke.php
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
require_once __DIR__ . '/../src/Audit/AgentTurnAuditor.php';

use OpenEMR\Modules\ClinicalCopilot\Audit\AgentTurnAuditor;

$traceId = 'auditor-smoke-' . bin2hex(random_bytes(4));

AgentTurnAuditor::record(
    1,
    9001,
    $traceId,
    'smoke',
    'passed',
    0,
    'auditor_smoke'
);

$row = sqlQuery(
    "SELECT event, patient_id, category, FROM_BASE64(comments) AS decoded_comments
       FROM log
      WHERE event = 'agent_turn'
        AND patient_id = ?
        AND FROM_BASE64(comments) LIKE ?
      ORDER BY id DESC
      LIMIT 1",
    [9001, '%' . $traceId . '%']
);

if (empty($row)) {
    echo "FAIL  agent turn audit smoke\n";
    echo "      - no log row found for trace {$traceId}\n";
    exit(1);
}

$decoded = (string)($row['decoded_comments'] ?? '');
$failures = [];
if (($row['event'] ?? '') !== 'agent_turn') {
    $failures[] = 'event is not agent_turn';
}
if ((int)($row['patient_id'] ?? 0) !== 9001) {
    $failures[] = 'patient_id is not 9001';
}
if (($row['category'] ?? '') !== 'agent_turn') {
    $failures[] = 'category is not agent_turn';
}
foreach (['use_case=smoke', 'verifier=passed', 'sources=0', 'tag=auditor_smoke'] as $needle) {
    if (!str_contains($decoded, $needle)) {
        $failures[] = "decoded comments missing {$needle}";
    }
}

if ($failures !== []) {
    echo "FAIL  agent turn audit smoke\n";
    foreach ($failures as $failure) {
        echo "      - {$failure}\n";
    }
    exit(1);
}

echo "PASS  agent turn audit smoke trace={$traceId}\n";
