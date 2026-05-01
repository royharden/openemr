<?php

/**
 * Clinical Co-Pilot Gateway - /brief endpoint.
 *
 * Trust boundary: same-origin OpenEMR session, CSRF token, ACL gate, server-side
 * pid (never trust the client). Builds source packets, optionally calls the
 * Python sidecar, writes an audit row, and returns verified JSON.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

require_once(__DIR__ . "/../../../../../globals.php");

use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Services\BaseService;
use OpenEMR\Modules\ClinicalCopilot\Audit\AgentTurnAuditor;
use OpenEMR\Modules\ClinicalCopilot\Gateway\SidecarClient;
use OpenEMR\Modules\ClinicalCopilot\Gateway\TaskToken;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ActiveMedicationsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ActiveProblemsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\AllergiesPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\IdentityPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ImmunizationsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\RecentLabsPacketBuilder;

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

function copilot_send_json(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

function copilot_uuid_v4(): string
{
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

$traceId = copilot_uuid_v4();

try {
    $session = SessionWrapperFactory::getInstance()->getActiveSession();
    $csrf = $_POST['csrf_token_form'] ?? $_SERVER['HTTP_APICSRFTOKEN'] ?? null;
    if (!is_string($csrf) || !CsrfUtils::verifyCsrfToken($csrf, $session, 'ClinicalCopilot')) {
        copilot_send_json(403, ['error' => 'csrf_failure', 'trace_id' => $traceId]);
    }

    if (!AclMain::aclCheckCore('patients', 'med')) {
        AgentTurnAuditor::record(
            (int)($_SESSION['authUserID'] ?? 0),
            (int)($_SESSION['pid'] ?? 0),
            $traceId,
            (string)($_POST['use_case'] ?? 'pre_room_brief'),
            'denied',
            0,
            'acl_denied',
        );
        copilot_send_json(403, ['error' => 'acl_denied', 'trace_id' => $traceId]);
    }

    $pid = (int)($session->get('pid') ?? 0);
    $userId = (int)($session->get('authUserID') ?? 0);
    $encounterId = (int)($session->get('encounter') ?? 0);

    if ($pid <= 0) {
        copilot_send_json(400, ['error' => 'no_active_patient', 'trace_id' => $traceId]);
    }

    $useCaseRaw = (string)($_POST['use_case'] ?? 'pre_room_brief');
    $allowedUseCases = [
        'pre_room_brief',
        'what-changed',
        'medication_check',
        'allergy_check',
        'recent_abnormal_labs',
    ];
    $useCase = in_array($useCaseRaw, $allowedUseCases, true) ? $useCaseRaw : 'pre_room_brief';

    try {
        $patientUuidBin = BaseService::getUuidById($pid, 'patient_data', 'pid');
        $patientUuid = !empty($patientUuidBin) ? UuidRegistry::uuidToString($patientUuidBin) : (string)$pid;
    } catch (\Throwable $e) {
        $patientUuid = (string)$pid;
    }

    $builders = match ($useCase) {
        'medication_check' => [
            new IdentityPacketBuilder(),
            new ActiveMedicationsPacketBuilder(),
            new AllergiesPacketBuilder(),
        ],
        'allergy_check' => [
            new IdentityPacketBuilder(),
            new AllergiesPacketBuilder(),
            new ActiveMedicationsPacketBuilder(),
        ],
        'recent_abnormal_labs' => [
            new IdentityPacketBuilder(),
            new ActiveProblemsPacketBuilder(),
            new RecentLabsPacketBuilder(),
        ],
        default => [
            new IdentityPacketBuilder(),
            new ActiveProblemsPacketBuilder(),
            new ActiveMedicationsPacketBuilder(),
            new AllergiesPacketBuilder(),
            new RecentLabsPacketBuilder(),
            new ImmunizationsPacketBuilder(),
        ],
    };
    $packets = [];
    foreach ($builders as $builder) {
        foreach ($builder->build($pid, $patientUuid) as $packet) {
            $packets[] = $packet->toArray();
            if (count($packets) >= 50) {
                break 2;
            }
        }
    }

    $sidecarBase = (string)(getenv('COPILOT_API_BASE_URL') ?: '');
    $sharedSecret = (string)(getenv('COPILOT_OPENEMR_GATEWAY_SHARED_SECRET') ?: '');
    $sidecarResponse = null;
    $verifierStatus = 'no_sidecar';

    if ($sidecarBase !== '' && $sharedSecret !== '') {
        $taskToken = TaskToken::mint(
            sharedSecret: $sharedSecret,
            patientUuid: $patientUuid,
            userId: $userId,
            encounterUuid: $encounterId > 0 ? (string)$encounterId : null,
            purposeOfUse: 'TREAT',
        );
        $client = new SidecarClient($sidecarBase, $sharedSecret);
        $sidecarResponse = $client->callBrief(
            traceId: $traceId,
            taskToken: $taskToken,
            useCase: $useCase,
            packets: $packets,
            patientUuidHash: substr(hash('sha256', $patientUuid), 0, 12),
        );
        if (isset($sidecarResponse['__sidecar_error'])) {
            $verifierStatus = 'sidecar_failed';
        } elseif (isset($sidecarResponse['verifier_status'])) {
            $verifierStatus = (string)$sidecarResponse['verifier_status'];
        } else {
            $verifierStatus = 'unknown';
        }
    }

    $response = [
        'trace_id' => $traceId,
        'pid' => $pid,
        'patient_uuid_hash' => substr(hash('sha256', $patientUuid), 0, 12),
        'use_case' => $useCase,
        'packet_count' => count($packets),
        'verifier_status' => $verifierStatus,
    ];

    if (is_array($sidecarResponse) && empty($sidecarResponse['__sidecar_error'])) {
        $response['answer_type'] = $sidecarResponse['answer_type'] ?? 'pre_room_brief';
        $response['claims'] = $sidecarResponse['claims'] ?? [];
        $response['missing_data'] = $sidecarResponse['missing_data'] ?? [];
        $response['refusals'] = $sidecarResponse['refusals'] ?? [];
        $response['suggested_followups'] = $sidecarResponse['suggested_followups'] ?? [];
        $response['unsupported_dropped'] = $sidecarResponse['unsupported_dropped'] ?? 0;
    } else {
        $response['answer_type'] = 'pre_room_brief';
        $response['claims'] = [];
        foreach ($packets as $p) {
            $response['claims'][] = [
                'text' => sprintf('%s: %s', $p['label'], is_scalar($p['value']) ? (string)$p['value'] : json_encode($p['value'])),
                'claim_type' => 'fact',
                'source_ids' => [$p['source_id']],
                'caveat' => $p['freshness'] === 'stale' ? 'stale data' : null,
            ];
            if (count($response['claims']) >= 8) {
                break;
            }
        }
        $response['missing_data'] = [];
        $response['refusals'] = [];
        $response['suggested_followups'] = ['What changed?'];
        $response['unsupported_dropped'] = 0;
        if (is_array($sidecarResponse) && !empty($sidecarResponse['__sidecar_error'])) {
            $response['sidecar_warning'] = $sidecarResponse['__sidecar_error'];
        }
    }

    AgentTurnAuditor::record(
        $userId,
        $pid,
        $traceId,
        $useCase,
        $verifierStatus,
        count($packets),
    );

    copilot_send_json(200, $response);
} catch (\Throwable $e) {
    error_log('ClinicalCopilot brief.php error: ' . $e->getMessage());
    copilot_send_json(500, [
        'error' => 'internal_error',
        'trace_id' => $traceId,
        'message' => $e->getMessage(),
    ]);
}
