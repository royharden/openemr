<?php

/**
 * CLI smoke test for SidecarClient::classifyResponse(). Returns non-zero on
 * regression. The classifier is the seam that decides whether the gateway
 * should treat the sidecar's reply as a verified response or as a transport
 * failure — getting it wrong silently masks 4xx auth failures behind 200 OK.
 *
 * Usage: php sidecar_client_smoke.php
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

require_once __DIR__ . '/../src/Gateway/SidecarClient.php';

use OpenEMR\Modules\ClinicalCopilot\Gateway\SidecarClient;

/** @var array<int, array{label: string, status: int, body: string, expect_error: ?string, expect_status: ?int, expect_detail: ?string, expect_passthrough_key: ?string}> */
$cases = [
    [
        'label' => '200 with verified response',
        'status' => 200,
        'body' => json_encode([
            'trace_id' => 't-1',
            'answer_type' => 'pre_room_brief',
            'verifier_status' => 'passed',
            'claims' => [],
        ]),
        'expect_error' => null,
        'expect_status' => 200,
        'expect_detail' => null,
        'expect_passthrough_key' => 'verifier_status',
    ],
    [
        'label' => '200 with tool-plan response',
        'status' => 200,
        'body' => json_encode([
            'trace_id' => 't-plan',
            'planner_status' => 'planned',
            'tool_calls' => [
                ['name' => 'get_patient_identity', 'arguments' => []],
            ],
        ]),
        'expect_error' => null,
        'expect_status' => 200,
        'expect_detail' => null,
        'expect_passthrough_key' => 'planner_status',
    ],
    [
        'label' => '403 missing task token',
        'status' => 403,
        'body' => json_encode(['detail' => 'task_token_missing']),
        'expect_error' => 'http_error',
        'expect_status' => 403,
        'expect_detail' => 'task_token_missing',
        'expect_passthrough_key' => null,
    ],
    [
        'label' => '403 expired task token',
        'status' => 403,
        'body' => json_encode(['detail' => 'task_token_expired']),
        'expect_error' => 'http_error',
        'expect_status' => 403,
        'expect_detail' => 'task_token_expired',
        'expect_passthrough_key' => null,
    ],
    [
        'label' => '500 server error',
        'status' => 500,
        'body' => json_encode(['detail' => 'internal']),
        'expect_error' => 'http_error',
        'expect_status' => 500,
        'expect_detail' => 'internal',
        'expect_passthrough_key' => null,
    ],
    [
        'label' => '502 with empty body',
        'status' => 502,
        'body' => '',
        'expect_error' => 'http_error',
        'expect_status' => 502,
        'expect_detail' => null,
        'expect_passthrough_key' => null,
    ],
    [
        'label' => '200 with non-JSON body',
        'status' => 200,
        'body' => '<html>not json</html>',
        'expect_error' => 'invalid_json',
        'expect_status' => 200,
        'expect_detail' => null,
        'expect_passthrough_key' => null,
    ],
];

$failures = 0;
foreach ($cases as $case) {
    $body = is_string($case['body']) ? $case['body'] : '';
    $result = SidecarClient::classifyResponse($case['status'], $body);

    $errors = [];
    $gotError = $result['__sidecar_error'] ?? null;
    if ($case['expect_error'] === null) {
        if ($gotError !== null) {
            $errors[] = "expected no error, got " . var_export($gotError, true);
        }
        if ($case['expect_passthrough_key'] !== null && !array_key_exists($case['expect_passthrough_key'], $result)) {
            $errors[] = "expected passthrough key " . $case['expect_passthrough_key'] . " to be present";
        }
    } else {
        if ($gotError !== $case['expect_error']) {
            $errors[] = "expected error " . var_export($case['expect_error'], true) . ", got " . var_export($gotError, true);
        }
    }

    if ($case['expect_status'] !== null) {
        $gotStatus = $result['__sidecar_status'] ?? null;
        if ($gotStatus !== $case['expect_status']) {
            $errors[] = "expected status " . $case['expect_status'] . ", got " . var_export($gotStatus, true);
        }
    }

    if ($case['expect_detail'] !== null) {
        $gotDetail = $result['__sidecar_detail'] ?? null;
        if ($gotDetail !== $case['expect_detail']) {
            $errors[] = "expected detail " . var_export($case['expect_detail'], true) . ", got " . var_export($gotDetail, true);
        }
    }

    if ($errors === []) {
        echo sprintf("PASS  %s\n", $case['label']);
    } else {
        $failures++;
        echo sprintf("FAIL  %s\n", $case['label']);
        foreach ($errors as $e) {
            echo "      - {$e}\n";
        }
    }
}

echo "\n";
echo $failures === 0
    ? sprintf("All %d sidecar-client smoke cases passed.\n", count($cases))
    : sprintf("%d/%d sidecar-client smoke cases failed.\n", $failures, count($cases));

exit($failures === 0 ? 0 : 1);
