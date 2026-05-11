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
use OpenEMR\Modules\ClinicalCopilot\Audit\AgentTurnAuditor;
use OpenEMR\Modules\ClinicalCopilot\Gateway\ClinicalToolExecutor;
use OpenEMR\Modules\ClinicalCopilot\Gateway\LocalTraceLogger;
use OpenEMR\Modules\ClinicalCopilot\Gateway\QuestionRouter;
use OpenEMR\Modules\ClinicalCopilot\Gateway\SidecarClient;
use OpenEMR\Modules\ClinicalCopilot\Gateway\TaskToken;
use OpenEMR\Services\BaseService;

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

/**
 * @param array<string, mixed> $payload
 */
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

function copilot_int(mixed $value, int $default = 0): int
{
    if (is_int($value)) {
        return $value;
    }
    if (is_float($value) || is_numeric($value)) {
        return (int)$value;
    }
    return $default;
}

function copilot_string(mixed $value, string $default = ''): string
{
    if (is_string($value)) {
        return $value;
    }
    if (is_int($value) || is_float($value) || is_bool($value)) {
        return (string)$value;
    }
    return $default;
}

function copilot_env_string(string $name): string
{
    $value = getenv($name);
    return is_string($value) ? $value : '';
}

/**
 * @return array<int, mixed>
 */
function copilot_list(mixed $value): array
{
    return is_array($value) ? array_values($value) : [];
}

/**
 * @param array<string, mixed>|null $payload
 */
function copilot_payload_string(?array $payload, string $key, string $default = ''): string
{
    return copilot_string($payload[$key] ?? null, $default);
}

/**
 * @param array<string, mixed>|null $payload
 */
function copilot_payload_int(?array $payload, string $key, int $default = 0): int
{
    return copilot_int($payload[$key] ?? null, $default);
}

/**
 * @param array<int, string> $selectedTools
 */
function copilot_audit_tag(?string $routerFamily, string $plannerStatus, array $selectedTools): string
{
    $prefix = ($routerFamily !== null && $routerFamily !== '') ? $routerFamily . ' ' : '';
    return trim($prefix . 'planner=' . $plannerStatus . ' tools=' . implode(',', $selectedTools));
}

function copilot_scalar_text(mixed $value): string
{
    if (is_scalar($value)) {
        return (string)$value;
    }
    $encoded = json_encode($value, JSON_UNESCAPED_SLASHES);
    return is_string($encoded) ? $encoded : '';
}

/**
 * @param array<int, string> $allowedKeys
 * @param array<int, array<string, mixed>> $packets
 * @return array<int, array<string, mixed>>
 */
function copilot_filter_builders(array $packets, array $allowedKeys): array
{
    if (in_array('all', $allowedKeys, true)) {
        return $packets;
    }
    return $packets;
}

/**
 * @param array<int, array<string, mixed>> $packets
 * @return array<int, array<string, mixed>>
 */
function copilot_packets_summary(array $packets): array
{
    $summary = [];
    foreach ($packets as $p) {
        $item = [
            'source_id' => $p['source_id'] ?? '',
            'source_table' => $p['source_table'] ?? '',
            'label' => $p['label'] ?? '',
            'observed_at' => $p['observed_at'] ?? null,
            'freshness' => $p['freshness'] ?? 'unknown',
        ];
        foreach ([
            'source_type',
            'field_or_chunk_id',
            'quote_or_value',
            'bbox',
            'bbox_unit',
            'page_index',
            'page_or_section',
            'confidence',
            'document_name',
            'doc_url',
            'recommendation_grade',
            'source_year',
            'source_organization',
            // AgDR-0065 — native lab chain links for DocumentFact packets.
            'procedure_result_uuid',
            'fhir_observation_url',
            'openemr_lab_review_url',
        ] as $key) {
            if (array_key_exists($key, $p)) {
                $item[$key] = $p[$key];
            }
        }
        $summary[] = $item;
    }
    return $summary;
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
            copilot_int($_SESSION['authUserID'] ?? null),
            copilot_int($_SESSION['pid'] ?? null),
            $traceId,
            copilot_string($_POST['use_case'] ?? null, 'pre_room_brief'),
            'denied',
            0,
            'acl_denied',
        );
        copilot_send_json(403, ['error' => 'acl_denied', 'trace_id' => $traceId]);
    }

    $pid = copilot_int($session->get('pid'));
    $userId = copilot_int($session->get('authUserID'));
    $encounterId = copilot_int($session->get('encounter'));

    if ($pid <= 0) {
        copilot_send_json(400, ['error' => 'no_active_patient', 'trace_id' => $traceId]);
    }

    $useCaseRaw = copilot_string($_POST['use_case'] ?? null, 'pre_room_brief');
    $allowedUseCases = [
        'pre_room_brief',
        'what-changed',
        'medication_check',
        'allergy_check',
        'recent_abnormal_labs',
        'immunization_history',
        'free_text_followup',
    ];
    $useCase = in_array($useCaseRaw, $allowedUseCases, true) ? $useCaseRaw : 'pre_room_brief';

    $rawQuestion = '';
    $normalizedQuestion = '';
    $routerFamily = null;
    $routerRefusalReason = null;
    $routerBuilders = null;

    if ($useCase === 'free_text_followup') {
        $rawQuestion = copilot_string($_POST['question'] ?? null);
        $normalizedQuestion = QuestionRouter::normalize($rawQuestion);
        if ($normalizedQuestion === '') {
            copilot_send_json(400, ['error' => 'empty_question', 'trace_id' => $traceId]);
        }
        $decision = QuestionRouter::classify($normalizedQuestion);
        $routerFamily = $decision['family'];
        $routerRefusalReason = $decision['refusal_reason'];
        $routerBuilders = $decision['builders'];
    }

    try {
        $patientUuidBin = BaseService::getUuidById((string)$pid, 'patient_data', 'pid');
        $patientUuid = $patientUuidBin !== false && $patientUuidBin !== ''
            ? UuidRegistry::uuidToString($patientUuidBin)
            : (string)$pid;
    } catch (\Throwable $e) {
        $patientUuid = (string)$pid;
    }
    $patientUuidHash = TaskToken::patientUuidHash($patientUuid);

    $sidecarBase = copilot_env_string('COPILOT_API_BASE_URL');
    $sharedSecret = copilot_env_string('COPILOT_OPENEMR_GATEWAY_SHARED_SECRET');

    // Local refusal: short-circuit before building any packets or calling the sidecar.
    if ($useCase === 'free_text_followup' && $routerRefusalReason !== null) {
        $localRefusal = QuestionRouter::buildRefusalResponse(
            $traceId,
            $routerFamily,
            $routerRefusalReason,
        );

        // Best-effort: tell the sidecar's observability endpoint about this refusal so
        // Langfuse keeps a trace_id-keyed record. PHI never sent.
        if ($sidecarBase !== '' && $sharedSecret !== '') {
            try {
                $logger = new LocalTraceLogger($sidecarBase, $sharedSecret);
                $logger->recordLocalRefusal(
                    $traceId,
                    $useCase,
                    $routerFamily,
                    $routerRefusalReason,
                    $patientUuidHash,
                );
            } catch (\Throwable $e) {
                error_log('ClinicalCopilot local refusal trace log failed: ' . $e->getMessage());
            }
        }

        $localRefusal['pid'] = $pid;
        $localRefusal['patient_uuid_hash'] = $patientUuidHash;
        $localRefusal['use_case'] = $useCase;
        $localRefusal['packet_count'] = 0;
        $localRefusal['packets_summary'] = [];

        AgentTurnAuditor::record(
            $userId,
            $pid,
            $traceId,
            $useCase,
            'refused_by_router',
            0,
            copilot_audit_tag($routerFamily, 'not_called', []),
        );

        copilot_send_json(200, $localRefusal);
    }

    $sidecarConfigured = $sidecarBase !== '' && $sharedSecret !== '';
    $sidecarResponse = null;
    $verifierStatus = $sidecarConfigured ? 'unknown' : 'no_sidecar';
    $executor = new ClinicalToolExecutor();
    $plannerStatus = $sidecarConfigured ? 'unknown' : 'fallback_required';
    $toolCalls = [];
    $selectedTools = [];
    $toolResultsSummary = [];
    $rejectedTools = [];

    if ($sidecarConfigured) {
        $taskToken = TaskToken::mint(
            sharedSecret: $sharedSecret,
            patientUuid: $patientUuid,
            userId: $userId,
            encounterUuid: $encounterId > 0 ? (string)$encounterId : null,
            purposeOfUse: 'TREAT',
        );
        $client = new SidecarClient($sidecarBase, $sharedSecret);

        $toolPlan = $client->callToolPlan(
            traceId: $traceId,
            useCase: $useCase,
            patientUuidHash: $patientUuidHash,
            question: $useCase === 'free_text_followup' ? $normalizedQuestion : null,
            routerFamily: $routerFamily,
        );
        if (isset($toolPlan['__sidecar_error'])) {
            $response = [
                'trace_id' => $traceId,
                'pid' => $pid,
                'patient_uuid_hash' => $patientUuidHash,
                'use_case' => $useCase,
                'packet_count' => 0,
                'verifier_status' => 'sidecar_failed',
                'planner_status' => 'failed',
                'selected_tools' => [],
                'tool_results_summary' => [],
                'packets_summary' => [],
                'answer_type' => $useCase === 'free_text_followup' ? 'follow_up' : 'pre_room_brief',
                'claims' => [],
                'missing_data' => ['Verification temporarily unavailable for this turn - open the chart panels directly.'],
                'refusals' => [],
                'suggested_followups' => [],
                'unsupported_dropped' => 0,
                'sidecar_warning' => copilot_payload_string($toolPlan, '__sidecar_error'),
            ];
            if (isset($toolPlan['__sidecar_status'])) {
                $response['sidecar_status'] = copilot_payload_int($toolPlan, '__sidecar_status');
            }
            AgentTurnAuditor::record(
                $userId,
                $pid,
                $traceId,
                $useCase,
                'sidecar_failed',
                0,
                'tool_plan_failed',
            );
            copilot_send_json(502, $response);
        }

        $plannerStatus = is_string($toolPlan['planner_status'] ?? null)
            ? $toolPlan['planner_status']
            : 'fallback_required';
        $toolCalls = copilot_list($toolPlan['tool_calls'] ?? null);
    }

    if (!$sidecarConfigured || $toolCalls === []) {
        $fallback = $executor->fallbackToolCalls($useCase, $routerFamily);
        $toolCalls = $fallback['tool_calls'];
        $plannerStatus = 'fallback_required';
    }

    $toolResult = $executor->execute($pid, $patientUuid, $toolCalls);
    $packets = $toolResult['packets'];
    $selectedTools = $toolResult['selected_tools'];
    $toolResultsSummary = $toolResult['summary'];
    $rejectedTools = $toolResult['rejected_tools'];

    if ($selectedTools === []) {
        $fallback = $executor->fallbackToolCalls($useCase, $routerFamily);
        $toolResult = $executor->execute($pid, $patientUuid, $fallback['tool_calls']);
        $packets = $toolResult['packets'];
        $selectedTools = $toolResult['selected_tools'];
        $toolResultsSummary = $toolResult['summary'];
        $rejectedTools = array_merge($rejectedTools, $toolResult['rejected_tools']);
        $plannerStatus = 'fallback_required';
    }

    if ($sidecarConfigured) {

        $priorIds = [];
        $priorIdsRaw = $_POST['prior_turn_source_ids'] ?? null;
        if (is_string($priorIdsRaw) && $priorIdsRaw !== '') {
            $decoded = json_decode($priorIdsRaw, true);
            if (is_array($decoded)) {
                foreach ($decoded as $sid) {
                    if (is_string($sid) && strlen($sid) <= 128) {
                        $priorIds[] = $sid;
                        if (count($priorIds) >= 20) {
                            break;
                        }
                    }
                }
            }
        }

        $sidecarResponse = $client->callCopilotAnswer(
            traceId: $traceId,
            useCase: $useCase,
            packets: $packets,
            patientUuidHash: $patientUuidHash,
            question: $useCase === 'free_text_followup' ? $normalizedQuestion : null,
        );
        if (isset($sidecarResponse['__sidecar_error'])) {
            $verifierStatus = 'sidecar_failed';
        } elseif (isset($sidecarResponse['verifier_status'])) {
            $verifierStatus = copilot_payload_string($sidecarResponse, 'verifier_status');
        }
    }

    $response = [
        'trace_id' => $traceId,
        'pid' => $pid,
        'patient_uuid_hash' => $patientUuidHash,
        'use_case' => $useCase,
        'packet_count' => count($packets),
        'verifier_status' => $verifierStatus,
        'planner_status' => $plannerStatus,
        'selected_tools' => $selectedTools,
        'tool_results_summary' => $toolResultsSummary,
        'packets_summary' => copilot_packets_summary($packets),
    ];
    if ($routerFamily !== null) {
        $response['router_family'] = $routerFamily;
    }
    if ($rejectedTools !== []) {
        $response['rejected_tools'] = $rejectedTools;
    }

    $sidecarErrored = is_array($sidecarResponse)
        && isset($sidecarResponse['__sidecar_error'])
        && $sidecarResponse['__sidecar_error'] !== '';

    if (is_array($sidecarResponse) && !$sidecarErrored) {
        // Normal verified path: sidecar produced a VerifiedResponse.
        $response['answer_type'] = $sidecarResponse['answer_type'] ?? 'pre_room_brief';
        $response['claims'] = $sidecarResponse['claims'] ?? [];
        $response['missing_data'] = $sidecarResponse['missing_data'] ?? [];
        $response['refusals'] = $sidecarResponse['refusals'] ?? [];
        $response['suggested_followups'] = $sidecarResponse['suggested_followups'] ?? [];
        $response['unsupported_dropped'] = $sidecarResponse['unsupported_dropped'] ?? 0;
        $response['selected_tools'] = $sidecarResponse['selected_tools'] ?? $selectedTools;
        $response['planner_status'] = $sidecarResponse['planner_status'] ?? $plannerStatus;
        $response['tool_results_summary'] = $sidecarResponse['tool_results_summary'] ?? $toolResultsSummary;

        AgentTurnAuditor::record(
            $userId,
            $pid,
            $traceId,
            $useCase,
            $verifierStatus,
            count($packets),
            copilot_audit_tag($routerFamily, $plannerStatus, $selectedTools),
        );
        copilot_send_json(200, $response);
    } elseif ($sidecarErrored) {
        // Sidecar configured but transport/HTTP/JSON failure. Do NOT flatten
        // packets into pseudo-claims — that previously hid 4xx auth failures
        // behind a "successful" 200 response. Surface as 502 sidecar_failed
        // with empty claims and a missing_data hint.
        error_log(sprintf(
            'ClinicalCopilot sidecar_failed trace_id=%s err=%s status=%s',
            $traceId,
            copilot_payload_string($sidecarResponse, '__sidecar_error', 'unknown'),
            copilot_payload_string($sidecarResponse, '__sidecar_status')
        ));
        $response['answer_type'] = $useCase === 'free_text_followup' ? 'follow_up' : 'pre_room_brief';
        $response['claims'] = [];
        $response['missing_data'] = [
            'Verification temporarily unavailable for this turn — open the chart panels directly.',
        ];
        $response['refusals'] = [];
        $response['suggested_followups'] = [];
        $response['unsupported_dropped'] = 0;
        $response['sidecar_warning'] = copilot_payload_string($sidecarResponse, '__sidecar_error');
        if (isset($sidecarResponse['__sidecar_status'])) {
            $response['sidecar_status'] = copilot_payload_int($sidecarResponse, '__sidecar_status');
        }

        AgentTurnAuditor::record(
            $userId,
            $pid,
            $traceId,
            $useCase,
            'sidecar_failed',
            count($packets),
            copilot_audit_tag($routerFamily, $plannerStatus, $selectedTools),
        );
        copilot_send_json(502, $response);
    } else {
        // No sidecar configured at all — local-only dev mode. Flatten packets
        // into pseudo-claims so the chart card still has something to show
        // for development without an API key.
        $response['answer_type'] = $useCase === 'free_text_followup' ? 'follow_up' : 'pre_room_brief';
        $response['claims'] = [];
        foreach ($packets as $p) {
            $response['claims'][] = [
                'text' => sprintf(
                    '%s: %s',
                    copilot_string($p['label'] ?? null, 'Source'),
                    copilot_scalar_text($p['value'] ?? null)
                ),
                'claim_type' => 'fact',
                'source_ids' => [copilot_string($p['source_id'] ?? null)],
                'caveat' => copilot_string($p['freshness'] ?? null) === 'stale' ? 'stale data' : null,
            ];
            if (count($response['claims']) >= 8) {
                break;
            }
        }
        $response['missing_data'] = [];
        $response['refusals'] = [];
        $response['suggested_followups'] = ['What changed?'];
        $response['unsupported_dropped'] = 0;

        AgentTurnAuditor::record(
            $userId,
            $pid,
            $traceId,
            $useCase,
            $verifierStatus,
            count($packets),
            copilot_audit_tag($routerFamily, $plannerStatus, $selectedTools),
        );
        copilot_send_json(200, $response);
    }
} catch (\Throwable $e) {
    // Log full detail server-side; never leak the exception message to the browser.
    error_log(sprintf(
        'ClinicalCopilot brief.php internal_error trace_id=%s exception=%s message=%s',
        $traceId,
        $e::class,
        $e->getMessage()
    ));
    copilot_send_json(500, [
        'error' => 'internal_error',
        'trace_id' => $traceId,
    ]);
}
