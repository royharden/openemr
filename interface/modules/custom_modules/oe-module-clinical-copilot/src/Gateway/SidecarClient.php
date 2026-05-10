<?php

/**
 * Sidecar client. Posts source packets + task token to the FastAPI sidecar
 * over HTTPS (or HTTP on private networking).
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Gateway;

use GuzzleHttp\Client;

final class SidecarClient
{
    public function __construct(
        private readonly string $baseUrl,
        private readonly string $sharedSecret,
        private readonly float $timeoutSeconds = 12.0,
    ) {
    }

    /**
     * @param array<int, array<string, mixed>> $packets
     * @param array<int, string>|null $priorTurnSourceIds
     * @param array<int, string>|null $selectedTools
     * @param array<int, array<string, mixed>>|null $toolResultsSummary
     * @return array<string, mixed>
     */
    public function callBrief(
        string $traceId,
        string $taskToken,
        string $useCase,
        array $packets,
        string $patientUuidHash,
        ?string $question = null,
        ?array $priorTurnSourceIds = null,
        ?string $routerFamily = null,
        ?array $selectedTools = null,
        ?string $plannerStatus = null,
        ?array $toolResultsSummary = null,
    ): array {
        $url = rtrim($this->baseUrl, '/') . '/v1/brief';
        $client = new Client([
            'timeout' => $this->timeoutSeconds,
            'http_errors' => false,
        ]);
        $body = [
            'trace_id' => $traceId,
            'use_case' => $useCase,
            'patient_uuid_hash' => $patientUuidHash,
            'packets' => $packets,
        ];
        if ($question !== null) {
            $body['question'] = $question;
        }
        if ($priorTurnSourceIds !== null) {
            $body['prior_turn_source_ids'] = $priorTurnSourceIds;
        }
        if ($routerFamily !== null) {
            $body['router_family'] = $routerFamily;
        }
        if ($selectedTools !== null) {
            $body['selected_tools'] = $selectedTools;
        }
        if ($plannerStatus !== null) {
            $body['planner_status'] = $plannerStatus;
        }
        if ($toolResultsSummary !== null) {
            $body['tool_results_summary'] = $toolResultsSummary;
        }
        try {
            $resp = $client->post($url, [
                'headers' => [
                    'X-Copilot-Gateway-Secret' => $this->sharedSecret,
                    'X-Copilot-Task-Token' => $taskToken,
                    'X-Copilot-Trace-Id' => $traceId,
                    'Content-Type' => 'application/json',
                ],
                'body' => json_encode($body, JSON_UNESCAPED_SLASHES),
            ]);
            return self::classifyResponse($resp->getStatusCode(), (string)$resp->getBody());
        } catch (\Exception $e) {
            return [
                '__sidecar_error' => 'request_failed',
                '__sidecar_message' => $e->getMessage(),
            ];
        }
    }

    /**
     * Execute the Week 2 LangGraph answer endpoint.
     *
     * @param array<int, array<string, mixed>> $packets
     * @return array<string, mixed>
     */
    public function callCopilotAnswer(
        string $traceId,
        string $useCase,
        array $packets,
        string $patientUuidHash,
        ?string $question = null,
    ): array {
        $url = rtrim($this->baseUrl, '/') . '/v1/copilot/answer';
        $client = new Client([
            'timeout' => $this->timeoutSeconds,
            'http_errors' => false,
        ]);
        $body = [
            'trace_id' => $traceId,
            'use_case' => $useCase,
            'patient_uuid_hash' => $patientUuidHash,
            'question' => $question,
            'packets' => $packets,
        ];

        try {
            $resp = $client->post($url, [
                'headers' => [
                    'X-Copilot-Gateway-Secret' => $this->sharedSecret,
                    'X-Copilot-Trace-Id' => $traceId,
                    'Content-Type' => 'application/json',
                ],
                'body' => json_encode($body, JSON_UNESCAPED_SLASHES),
            ]);
            return self::classifyResponse($resp->getStatusCode(), (string)$resp->getBody());
        } catch (\Exception $e) {
            return [
                '__sidecar_error' => 'request_failed',
                '__sidecar_message' => $e->getMessage(),
            ];
        }
    }

    /**
     * Ask the sidecar LLM planner which read-only current-patient tools should
     * be executed by the OpenEMR gateway.
     *
     * @return array<string, mixed>
     */
    public function callToolPlan(
        string $traceId,
        string $useCase,
        string $patientUuidHash,
        ?string $question = null,
        ?string $routerFamily = null,
    ): array {
        $url = rtrim($this->baseUrl, '/') . '/v1/tool-plan';
        $client = new Client([
            'timeout' => 8.0,
            'http_errors' => false,
        ]);
        $body = [
            'trace_id' => $traceId,
            'use_case' => $useCase,
            'patient_uuid_hash' => $patientUuidHash,
        ];
        if ($question !== null) {
            $body['question'] = $question;
        }
        if ($routerFamily !== null) {
            $body['router_family'] = $routerFamily;
        }

        try {
            $resp = $client->post($url, [
                'headers' => [
                    'X-Copilot-Gateway-Secret' => $this->sharedSecret,
                    'X-Copilot-Trace-Id' => $traceId,
                    'Content-Type' => 'application/json',
                ],
                'body' => json_encode($body, JSON_UNESCAPED_SLASHES),
            ]);
            return self::classifyResponse($resp->getStatusCode(), (string)$resp->getBody());
        } catch (\Throwable $e) {
            return [
                '__sidecar_error' => 'request_failed',
                '__sidecar_message' => $e->getMessage(),
            ];
        }
    }

    /**
     * Classify a raw (status, body) into either a verified response payload or
     * a `__sidecar_error` envelope. Public so the CLI smoke harness can exercise
     * it directly without spinning up Guzzle.
     *
     * @return array<string, mixed>
     */
    public static function classifyResponse(int $status, string $rawBody): array
    {
        $decoded = json_decode($rawBody, true);
        $detail = is_array($decoded) ? ($decoded['detail'] ?? null) : null;

        if ($status < 200 || $status >= 300) {
            return [
                '__sidecar_error' => 'http_error',
                '__sidecar_status' => $status,
                '__sidecar_detail' => is_string($detail) ? $detail : null,
            ];
        }

        if (!is_array($decoded)) {
            return [
                '__sidecar_error' => 'invalid_json',
                '__sidecar_status' => $status,
                '__sidecar_raw' => substr($rawBody, 0, 500),
            ];
        }

        /** @var array<string, mixed> $decoded */
        $decoded['__sidecar_status'] = $status;
        return $decoded;
    }

    /**
     * Forward a clinician's feedback verdict for a previous brief.
     *
     * @return array<string, mixed>
     */
    public function callFeedback(
        string $traceId,
        string $verdict,
        string $comment = '',
    ): array {
        $url = rtrim($this->baseUrl, '/') . '/v1/feedback';
        $client = new Client([
            'timeout' => 4.0,
            'http_errors' => false,
        ]);
        $body = [
            'trace_id' => $traceId,
            'verdict' => $verdict,
            'comment' => $comment,
        ];
        try {
            $resp = $client->post($url, [
                'headers' => [
                    'X-Copilot-Gateway-Secret' => $this->sharedSecret,
                    'X-Copilot-Trace-Id' => $traceId,
                    'Content-Type' => 'application/json',
                ],
                'body' => json_encode($body, JSON_UNESCAPED_SLASHES),
            ]);
            return self::classifyResponse($resp->getStatusCode(), (string)$resp->getBody());
        } catch (\Throwable $e) {
            return [
                '__sidecar_error' => 'request_failed',
                '__sidecar_message' => $e->getMessage(),
            ];
        }
    }
}
