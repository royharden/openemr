<?php

/**
 * Clinical Co-Pilot Feedback endpoint.
 *
 * Receives a clinician's verdict on a single agent turn (Helpful / Missing
 * data / Incorrect / Too slow / Source unclear). The trace_id from the
 * original brief response is the join key — gateway audits it locally and
 * forwards the score to the sidecar so it can be attached to the matching
 * Langfuse trace.
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
use OpenEMR\Modules\ClinicalCopilot\Audit\AgentTurnAuditor;
use OpenEMR\Modules\ClinicalCopilot\Gateway\SidecarClient;

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

function copilot_feedback_send(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

$ALLOWED_VERDICTS = [
    'helpful',
    'missing_data',
    'incorrect',
    'too_slow',
    'source_unclear',
];

try {
    $session = SessionWrapperFactory::getInstance()->getActiveSession();
    $csrf = $_POST['csrf_token_form'] ?? $_SERVER['HTTP_APICSRFTOKEN'] ?? null;
    if (!is_string($csrf) || !CsrfUtils::verifyCsrfToken($csrf, $session, 'ClinicalCopilot')) {
        copilot_feedback_send(403, ['error' => 'csrf_failure']);
    }

    if (!AclMain::aclCheckCore('patients', 'med')) {
        copilot_feedback_send(403, ['error' => 'acl_denied']);
    }

    $traceId = trim((string)($_POST['trace_id'] ?? ''));
    $verdict = strtolower(trim((string)($_POST['verdict'] ?? '')));
    $comment = (string)($_POST['comment'] ?? '');

    if ($traceId === '' || !preg_match('/^[a-f0-9-]{8,}$/i', $traceId)) {
        copilot_feedback_send(400, ['error' => 'invalid_trace_id']);
    }
    if (!in_array($verdict, $ALLOWED_VERDICTS, true)) {
        copilot_feedback_send(400, ['error' => 'invalid_verdict']);
    }
    if (strlen($comment) > 500) {
        $comment = substr($comment, 0, 500);
    }

    $userId = (int)($session->get('authUserID') ?? 0);
    $pid = (int)($session->get('pid') ?? 0);

    AgentTurnAuditor::record(
        $userId,
        $pid,
        $traceId,
        'feedback:' . $verdict,
        'feedback',
        0,
    );

    $sidecarBase = (string)(getenv('COPILOT_API_BASE_URL') ?: '');
    $sharedSecret = (string)(getenv('COPILOT_OPENEMR_GATEWAY_SHARED_SECRET') ?: '');
    $sidecarStatus = 'no_sidecar';
    if ($sidecarBase !== '' && $sharedSecret !== '') {
        $client = new SidecarClient($sidecarBase, $sharedSecret);
        $resp = $client->callFeedback(
            traceId: $traceId,
            verdict: $verdict,
            comment: $comment,
        );
        $sidecarStatus = isset($resp['__sidecar_error']) ? 'sidecar_failed' : 'forwarded';
    }

    copilot_feedback_send(200, [
        'trace_id' => $traceId,
        'verdict' => $verdict,
        'sidecar' => $sidecarStatus,
    ]);
} catch (\RuntimeException | \PDOException | \JsonException $e) {
    // Plan §4.2 / AgDR-0082 — enumerated catch. Inside the try: AgentTurnAuditor::record
    // can throw SqlQueryException (extends RuntimeException); session/CSRF helpers may
    // throw RuntimeException; SidecarClient::callFeedback wraps its own Guzzle errors
    // and returns an array. \JsonException is defensive against a future json_encode
    // path that adopts JSON_THROW_ON_ERROR.
    error_log('ClinicalCopilot feedback.php error: ' . $e->getMessage());
    copilot_feedback_send(500, ['error' => 'internal_error']);
}
