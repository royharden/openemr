<?php

/**
 * Posts a "local refusal" trace shape to the sidecar so observability covers
 * gateway-only refusal turns (refused_by_router) — the LLM was never called,
 * but Langfuse still gets a trace_id-keyed record so the full distribution
 * of turn outcomes is visible in one place.
 *
 * Best-effort: a sidecar outage MUST NOT break the refusal response.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Gateway;

use GuzzleHttp\Client;

final class LocalTraceLogger
{
    public function __construct(
        private readonly string $baseUrl,
        private readonly string $sharedSecret,
        private readonly float $timeoutSeconds = 2.0,
    ) {
    }

    public function recordLocalRefusal(
        string $traceId,
        string $useCase,
        string $routerFamily,
        string $refusalReason,
        string $patientUuidHash,
    ): void {
        if ($this->baseUrl === '' || $this->sharedSecret === '') {
            return;
        }
        $url = rtrim($this->baseUrl, '/') . '/v1/trace/local_refusal';
        try {
            $client = new Client([
                'timeout' => $this->timeoutSeconds,
                'http_errors' => false,
            ]);
            $client->post($url, [
                'headers' => [
                    'X-Copilot-Gateway-Secret' => $this->sharedSecret,
                    'X-Copilot-Trace-Id' => $traceId,
                    'Content-Type' => 'application/json',
                ],
                'body' => json_encode([
                    'trace_id' => $traceId,
                    'use_case' => $useCase,
                    'router_family' => $routerFamily,
                    'refusal_reason' => $refusalReason,
                    'patient_uuid_hash' => $patientUuidHash,
                ], JSON_UNESCAPED_SLASHES),
            ]);
        } catch (\Throwable $e) {
            error_log('ClinicalCopilot LocalTraceLogger error: ' . $e->getMessage());
        }
    }
}
