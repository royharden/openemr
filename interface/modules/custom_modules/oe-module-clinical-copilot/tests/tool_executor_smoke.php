<?php

/**
 * CLI smoke for ClinicalToolExecutor allowlist and fallback behavior.
 *
 * Usage:
 *   php tool_executor_smoke.php
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
require_once __DIR__ . '/../src/SourcePackets/PacketBuilder.php';
require_once __DIR__ . '/../src/SourcePackets/PacketDto.php';
require_once __DIR__ . '/../src/SourcePackets/IdentityPacketBuilder.php';
require_once __DIR__ . '/../src/SourcePackets/ActiveProblemsPacketBuilder.php';
require_once __DIR__ . '/../src/SourcePackets/ActiveMedicationsPacketBuilder.php';
require_once __DIR__ . '/../src/SourcePackets/AllergiesPacketBuilder.php';
require_once __DIR__ . '/../src/SourcePackets/RecentLabsPacketBuilder.php';
require_once __DIR__ . '/../src/SourcePackets/ImmunizationsPacketBuilder.php';
require_once __DIR__ . '/../src/Gateway/ClinicalToolExecutor.php';

use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Modules\ClinicalCopilot\Gateway\ClinicalToolExecutor;
use OpenEMR\Services\BaseService;

$pid = 9001;
try {
    $patientUuidBin = BaseService::getUuidById((string)$pid, 'patient_data', 'pid');
    $patientUuid = $patientUuidBin !== false && $patientUuidBin !== ''
        ? UuidRegistry::uuidToString($patientUuidBin)
        : (string)$pid;
} catch (\RuntimeException | \PDOException $e) {
    // Plan §4.2 / AgDR-0082 — enumerated catch (matches brief.php:243 pattern).
    $patientUuid = (string)$pid;
}

$executor = new ClinicalToolExecutor();
$fallback = $executor->fallbackToolCalls('immunization_history', null);
$result = $executor->execute($pid, $patientUuid, $fallback['tool_calls']);

$failures = [];
if (!in_array('get_immunization_history', $result['selected_tools'], true)) {
    $failures[] = 'immunization fallback did not select get_immunization_history';
}
if (count($result['packets']) < 1) {
    $failures[] = 'immunization fallback returned no packets for demo pid 9001';
}

$rejected = $executor->execute($pid, $patientUuid, [
    ['name' => 'read_arbitrary_table', 'arguments' => []],
    ['name' => 'get_recent_labs', 'arguments' => ['patient_uuid' => 'other']],
]);
if ($rejected['selected_tools'] !== []) {
    $failures[] = 'unknown/patient-override calls should not execute';
}
if (count($rejected['rejected_tools']) < 2) {
    $failures[] = 'unknown and patient-override calls were not both rejected';
}

if ($failures !== []) {
    foreach ($failures as $failure) {
        echo "FAIL  {$failure}\n";
    }
    exit(1);
}

echo "PASS  ClinicalToolExecutor allowlist, fallback, and rejection behavior\n";
exit(0);
