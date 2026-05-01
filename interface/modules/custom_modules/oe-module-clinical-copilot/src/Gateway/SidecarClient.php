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
use GuzzleHttp\Exception\GuzzleException;

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
     * @return array<string, mixed>
     */
    public function callBrief(
        string $traceId,
        string $taskToken,
        string $useCase,
        array $packets,
        string $patientUuidHash,
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
            $status = $resp->getStatusCode();
            $raw = (string)$resp->getBody();
            $decoded = json_decode($raw, true);
            if (!is_array($decoded)) {
                return [
                    '__sidecar_error' => 'invalid_json',
                    '__sidecar_status' => $status,
                    '__sidecar_raw' => substr($raw, 0, 500),
                ];
            }
            $decoded['__sidecar_status'] = $status;
            return $decoded;
        } catch (GuzzleException | \Throwable $e) {
            return [
                '__sidecar_error' => 'request_failed',
                '__sidecar_message' => $e->getMessage(),
            ];
        }
    }
}
