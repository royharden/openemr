<?php

/**
 * CLI smoke test for source-packet builders against the live OpenEMR DB.
 *
 * This intentionally exercises the same packet builders used by public/api/brief.php,
 * without requiring a browser login or a running sidecar.
 *
 * Usage from the openemr container:
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/packet_builders_smoke.php
 *   php interface/modules/custom_modules/oe-module-clinical-copilot/tests/packet_builders_smoke.php --pid=9001 --json
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

use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ActiveMedicationsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ActiveProblemsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\AllergiesPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\IdentityPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ImmunizationsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\RecentLabsPacketBuilder;
use OpenEMR\Services\BaseService;

$pid = 9001;
$json = false;
// $argv is only defined when invoked via the PHP CLI SAPI. Guard with
// null-coalesce so phpstan does not flag this as "Variable $argv might not
// be defined" — the upstream FatalBaselineCapsIsolatedTest caps that
// category and refuses growth.
$cliArgs = $argv ?? [];
foreach (array_slice($cliArgs, 1) as $arg) {
    if ($arg === '--json') {
        $json = true;
        continue;
    }
    if (str_starts_with($arg, '--pid=')) {
        $pid = (int)substr($arg, 6);
    }
}

try {
    $patientUuidBin = BaseService::getUuidById($pid, 'patient_data', 'pid');
    $patientUuid = !empty($patientUuidBin) ? UuidRegistry::uuidToString($patientUuidBin) : (string)$pid;
} catch (\Throwable $e) {
    $patientUuid = (string)$pid;
}

$builders = [
    new IdentityPacketBuilder(),
    new ActiveProblemsPacketBuilder(),
    new ActiveMedicationsPacketBuilder(),
    new AllergiesPacketBuilder(),
    new RecentLabsPacketBuilder(),
    new ImmunizationsPacketBuilder(),
];

$packets = [];
foreach ($builders as $builder) {
    foreach ($builder->build($pid, $patientUuid) as $packet) {
        $packets[] = $packet->toArray();
    }
}

if ($json) {
    echo json_encode([
        'pid' => $pid,
        'patient_uuid_hash' => substr(hash('sha256', $patientUuid), 0, 12),
        'packet_count' => count($packets),
        'packets' => $packets,
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL;
    exit(0);
}

$failures = [];
if (count($packets) === 0) {
    $failures[] = 'no packets built';
}

$immunizations = array_values(array_filter(
    $packets,
    static fn(array $p): bool => ($p['source_table'] ?? '') === 'immunizations'
));
if (count($immunizations) !== 1) {
    $failures[] = 'expected exactly one immunization packet for demo pid';
} else {
    $value = strtolower((string)($immunizations[0]['value'] ?? ''));
    if (!str_contains($value, 'pneumococcal')) {
        $failures[] = 'demo immunization packet does not resolve to pneumococcal text';
    }
    if (str_contains($value, 'hepatitis')) {
        $failures[] = 'demo immunization packet incorrectly resolves to hepatitis text';
    }
}

if ($failures !== []) {
    echo "FAIL  packet builder smoke for pid={$pid}\n";
    foreach ($failures as $failure) {
        echo "      - {$failure}\n";
    }
    foreach ($immunizations as $packet) {
        echo '      immunization source=' . (string)($packet['source_id'] ?? '')
            . ' value=' . (string)($packet['value'] ?? '') . "\n";
    }
    exit(1);
}

echo "PASS  packet builder smoke for pid={$pid}\n";
echo '      packets=' . count($packets) . "\n";
echo '      immunization=' . (string)$immunizations[0]['value']
    . ' [' . (string)$immunizations[0]['source_id'] . ']' . "\n";
exit(0);
