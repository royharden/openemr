<?php

/**
 * Persists extracted document facts to copilot_document_facts (Wk2 Workstream A).
 *
 * PHP gateway is the ONLY writer to this table. The sidecar returns an
 * ExtractedDocument JSON payload; this repository converts each field to a row,
 * computing the SHA-256(patient_uuid + document_sha256 + field_path) idempotency
 * key so re-uploads of the same document never create duplicate rows.
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Repository;

use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Logging\SystemLogger;
use OpenEMR\Common\Utils\OEGlobalsBag;

final class DocumentFactsRepository
{
    private const TABLE = 'copilot_document_facts';

    public function __construct(
        private readonly SystemLogger $logger,
    ) {}

    /**
     * Persist all extracted fields from a sidecar ExtractedDocument payload.
     *
     * Idempotent: rows with a matching idempotency_key are silently skipped
     * (INSERT IGNORE). Returns the number of rows actually inserted.
     *
     * @param array<string, mixed> $extractedDoc  Decoded JSON from sidecar ExtractedDocument.
     * @param string               $patientUuid   Raw patient UUID (NOT the hash).
     * @param string               $documentUuidBin  Binary 16-byte OpenEMR documents.uuid.
     * @param string               $createdBy     OpenEMR user id of the uploader.
     */
    public function persistExtractedDocument(
        array $extractedDoc,
        string $patientUuid,
        string $documentUuidBin,
        string $createdBy,
    ): int {
        $docSha256 = (string) ($extractedDoc['document_sha256'] ?? '');
        $docType   = (string) ($extractedDoc['doc_type'] ?? '');
        $result    = $extractedDoc['result'] ?? [];

        if ($docSha256 === '' || $docType === '') {
            $this->logger->errorLogCaller('DocumentFactsRepository: missing document_sha256 or doc_type in payload');
            return 0;
        }

        /** @var list<array<string, mixed>> $fields */
        $fields = is_array($result['fields'] ?? null) ? $result['fields'] : [];
        if ($fields === []) {
            return 0;
        }

        $extractedBy  = (string) ($result['extracted_by_model'] ?? 'unknown');
        $extractedAt  = (string) ($result['extracted_at'] ?? date('Y-m-d H:i:s'));
        $patientHash  = hash('sha256', $patientUuid);
        $inserted     = 0;

        foreach ($fields as $field) {
            if (!is_array($field)) {
                continue;
            }
            $fieldPath = (string) ($field['name'] ?? '');
            if ($fieldPath === '') {
                continue;
            }

            $idempotencyKey = hash('sha256', $patientUuid . $docSha256 . $fieldPath);

            $citation   = $field['citation'] ?? [];
            $pageIndex  = is_array($citation) ? ($citation['page_index'] ?? null) : null;
            $bboxJson   = is_array($citation) && isset($citation['bbox']) && is_array($citation['bbox'])
                ? json_encode($citation['bbox'], JSON_THROW_ON_ERROR)
                : null;
            $bboxUnit   = is_array($citation) ? ($citation['bbox_unit'] ?? null) : null;
            $quote      = is_array($citation) ? ($citation['quote_or_value'] ?? null) : null;
            $pageSection = is_array($citation) ? ($citation['page_or_section'] ?? null) : null;
            $confidence = is_array($citation) ? ($citation['confidence'] ?? null) : null;

            $fieldValueJson = json_encode([
                'value'           => $field['value'] ?? null,
                'unit'            => $field['unit'] ?? null,
                'reference_range' => $field['reference_range'] ?? null,
                'flag'            => $field['flag'] ?? null,
                'loinc_code'      => $field['loinc_code'] ?? null,
            ], JSON_THROW_ON_ERROR);

            $params = [
                $idempotencyKey,
                $patientHash,
                $documentUuidBin,
                $docSha256,
                $docType,
                $fieldPath,
                $fieldValueJson,
                $confidence !== null ? (float) $confidence : null,
                $quote,
                $pageIndex !== null ? (int) $pageIndex : null,
                $pageSection,
                $bboxJson,
                $bboxUnit,
                $extractedBy,
                $extractedAt,
                $createdBy,
            ];

            try {
                $affected = QueryUtils::sqlInsert(
                    'INSERT IGNORE INTO `' . self::TABLE . '`
                        (`idempotency_key`, `patient_uuid_hash`, `document_uuid`,
                         `document_sha256`, `doc_type`, `field_path`,
                         `field_value_json`, `confidence`,
                         `quote_or_value`, `page_index`, `page_or_section`,
                         `bbox_json`, `bbox_unit`,
                         `extracted_by_model`, `extracted_at`, `created_by`)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    $params,
                );
                $inserted += max(0, (int) $affected);
            } catch (\Throwable $e) {
                $this->logger->errorLogCaller('DocumentFactsRepository: insert failed', [
                    'field_path' => $fieldPath,
                    'exception'  => $e,
                ]);
            }
        }

        return $inserted;
    }

    /**
     * Retrieve persisted facts for a patient + document.
     *
     * @param string $patientUuid  Raw patient UUID.
     * @param string $documentSha256  SHA-256 of document body.
     * @return list<array<string, mixed>>
     */
    public function findByPatientAndDocument(
        string $patientUuid,
        string $documentSha256,
    ): array {
        $patientHash = hash('sha256', $patientUuid);
        $rows = QueryUtils::sqlStatementThrowException(
            'SELECT * FROM `' . self::TABLE . '`
              WHERE `patient_uuid_hash` = ? AND `document_sha256` = ?
              ORDER BY `id`',
            [$patientHash, $documentSha256],
        );

        /** @var list<array<string, mixed>> $result */
        $result = [];
        while ($row = sqlFetchArray($rows)) {
            if (is_array($row)) {
                $result[] = $row;
            }
        }
        return $result;
    }
}
