<?php

/**
 * Handles document uploads for the Clinical Co-Pilot (Wk2 Workstream A).
 *
 * Responsibilities:
 *  - Validate file size (max 10 pages / 8 MB) and MIME type before touching the sidecar.
 *  - Compute document SHA-256 for idempotency.
 *  - Forward the file to the sidecar /v1/extract/* endpoint.
 *  - Persist the returned ExtractedDocument via DocumentFactsRepository.
 *  - Return the parsed result to the caller.
 *
 * The PHP gateway is the only DB writer — the sidecar never touches the DB.
 * Re-uploading the same file for the same patient is idempotent (INSERT IGNORE
 * on the SHA-256(patient_uuid + document_sha256 + field_path) key).
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Controller;

use GuzzleHttp\Client;
use GuzzleHttp\Exception\GuzzleException;
use OpenEMR\Modules\ClinicalCopilot\Repository\DocumentFactsRepository;
use Psr\Log\LoggerInterface;

final class DocumentUploadController
{
    private const MAX_BYTES = 8 * 1024 * 1024; // 8 MB
    private const MAX_PAGES = 10;

    /** Accepted MIME types for upload. */
    private const ALLOWED_MIME_TYPES = [
        'application/pdf',
        'image/png',
        'image/jpeg',
    ];

    public function __construct(
        private readonly string $sidecarBaseUrl,
        private readonly string $gatewaySecret,
        private readonly DocumentFactsRepository $repository,
        private readonly LoggerInterface $logger,
        private readonly float $timeoutSeconds = 60.0,
    ) {}

    /**
     * Upload and extract a lab PDF.
     *
     * @param string $tmpPath       Filesystem path to the uploaded temp file.
     * @param string $originalName  Original filename from the upload.
     * @param string $mimeType      MIME type declared by the upload (e.g. 'application/pdf').
     * @param string $patientUuid   Raw patient UUID.
     * @param string $documentUuidBin  OpenEMR documents.uuid (binary 16 bytes).
     * @param string $createdBy     OpenEMR user id.
     * @return array<string, mixed>  The ExtractedDocument payload.
     * @throws \RuntimeException on sidecar failure or size/page/MIME violation.
     */
    public function uploadLabPdf(
        string $tmpPath,
        string $originalName,
        string $mimeType,
        string $patientUuid,
        string $documentUuidBin,
        string $createdBy,
    ): array {
        $this->validateMimeType($mimeType, $originalName);
        $content = $this->readAndValidate($tmpPath, $originalName);
        $sha256  = hash('sha256', $content);

        $patientUuidHash = hash('sha256', $patientUuid);
        $payload = $this->callSidecar('/v1/extract/lab-pdf', $content, $originalName, $patientUuidHash);

        $inserted = $this->repository->persistExtractedDocument(
            $payload,
            $patientUuid,
            $documentUuidBin,
            $createdBy,
        );

        $this->logger->debug('DocumentUploadController: lab-pdf extracted', [
            'sha256'        => $sha256,
            'fields'        => $payload['extracted_field_count'] ?? 0,
            'rows_inserted' => $inserted,
        ]);

        return $payload;
    }

    /**
     * Upload and extract an intake form (PDF, PNG, or JPEG).
     *
     * @param string $tmpPath       Filesystem path to the uploaded temp file.
     * @param string $originalName  Original filename.
     * @param string $mimeType      MIME type declared by the upload.
     * @param string $patientUuid   Raw patient UUID.
     * @param string $documentUuidBin  OpenEMR documents.uuid (binary 16 bytes).
     * @param string $createdBy     OpenEMR user id.
     * @return array<string, mixed>  The ExtractedDocument payload.
     * @throws \RuntimeException on sidecar failure or size/page/MIME violation.
     */
    public function uploadIntakeForm(
        string $tmpPath,
        string $originalName,
        string $mimeType,
        string $patientUuid,
        string $documentUuidBin,
        string $createdBy,
    ): array {
        $this->validateMimeType($mimeType, $originalName);
        $content = $this->readAndValidate($tmpPath, $originalName);
        $sha256  = hash('sha256', $content);

        $patientUuidHash = hash('sha256', $patientUuid);
        $payload = $this->callSidecar('/v1/extract/intake-form', $content, $originalName, $patientUuidHash);

        $inserted = $this->repository->persistExtractedDocument(
            $payload,
            $patientUuid,
            $documentUuidBin,
            $createdBy,
        );

        $this->logger->debug('DocumentUploadController: intake-form extracted', [
            'sha256'        => $sha256,
            'fields'        => $payload['extracted_field_count'] ?? 0,
            'rows_inserted' => $inserted,
        ]);

        return $payload;
    }

    /**
     * Validate that the declared MIME type is in the allowed list.
     *
     * @throws \RuntimeException if the MIME type is not permitted.
     */
    private function validateMimeType(string $mimeType, string $originalName): void
    {
        if (!in_array($mimeType, self::ALLOWED_MIME_TYPES, true)) {
            throw new \RuntimeException(
                "File {$originalName} has unsupported MIME type '{$mimeType}'; "
                . 'allowed: ' . implode(', ', self::ALLOWED_MIME_TYPES)
            );
        }
    }

    /**
     * Read the file and enforce hard size / page limits.
     *
     * @throws \RuntimeException on violation.
     */
    private function readAndValidate(string $tmpPath, string $originalName): string
    {
        if (!is_readable($tmpPath)) {
            throw new \RuntimeException("Upload temp file not readable: {$tmpPath}");
        }

        $size = filesize($tmpPath);
        if ($size === false || $size > self::MAX_BYTES) {
            $mb = $size === false ? '?' : round($size / 1024 / 1024, 1);
            throw new \RuntimeException(
                "File {$originalName} is {$mb} MB; maximum is 8 MB"
            );
        }

        $content = file_get_contents($tmpPath);
        if ($content === false) {
            throw new \RuntimeException("Failed to read upload temp file: {$tmpPath}");
        }

        // PDF page-count enforcement
        if (str_starts_with($content, '%PDF')) {
            $this->validatePdfPageCount($content, $originalName);
        }

        return $content;
    }

    /**
     * Count PDF pages via a simple cross-reference scan (no extension required).
     * Falls back to accepting the file if the count cannot be determined.
     *
     * @throws \RuntimeException if page count exceeds MAX_PAGES.
     */
    private function validatePdfPageCount(string $content, string $originalName): void
    {
        // Count /Type /Page (non-/Pages) occurrences as a fast page estimator.
        // Full parse is done by the sidecar (pypdfium2); this is a conservative
        // guard-rail to avoid sending monster PDFs to the API at all.
        $matches = [];
        preg_match_all('/\/Type\s*\/Page\b(?!s)/', $content, $matches);
        $count = count($matches[0]);

        if ($count > self::MAX_PAGES) {
            throw new \RuntimeException(
                "PDF {$originalName} appears to have {$count} pages; maximum is " . self::MAX_PAGES
            );
        }
    }

    /**
     * POST the file to a sidecar multipart endpoint and return the decoded JSON.
     *
     * @return array<string, mixed>
     * @throws \RuntimeException on HTTP error or JSON decode failure.
     */
    private function callSidecar(
        string $path,
        string $content,
        string $originalName,
        string $patientUuidHash,
    ): array {
        $url    = rtrim($this->sidecarBaseUrl, '/') . $path;
        $client = new Client([
            'timeout'     => $this->timeoutSeconds,
            'http_errors' => false,
        ]);

        try {
            $response = $client->post($url, [
                'headers' => [
                    'X-Copilot-Gateway-Secret' => $this->gatewaySecret,
                ],
                'multipart' => [
                    [
                        'name'     => 'file',
                        'contents' => $content,
                        'filename' => $originalName,
                    ],
                    [
                        'name'     => 'patient_uuid_hash',
                        'contents' => $patientUuidHash,
                    ],
                ],
            ]);
        } catch (GuzzleException $e) {
            throw new \RuntimeException("Sidecar request failed: {$e->getMessage()}", 0, $e);
        }

        $status = $response->getStatusCode();
        $body   = (string) $response->getBody();

        if ($status < 200 || $status >= 300) {
            $this->logger->error('DocumentUploadController: sidecar error', [
                'status' => $status,
                'path'   => $path,
                'body'   => substr($body, 0, 512),
            ]);
            throw new \RuntimeException("Sidecar returned HTTP {$status} for {$path}");
        }

        try {
            $decoded = json_decode($body, associative: true, flags: JSON_THROW_ON_ERROR);
        } catch (\JsonException $e) {
            throw new \RuntimeException("Sidecar response was not valid JSON: {$e->getMessage()}", 0, $e);
        }

        if (!is_array($decoded)) {
            throw new \RuntimeException("Sidecar response JSON was not an object for {$path}");
        }

        /** @var array<string, mixed> $decoded */
        return $decoded;
    }
}
