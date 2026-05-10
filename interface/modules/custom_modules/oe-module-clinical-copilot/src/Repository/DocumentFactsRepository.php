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
use Psr\Log\LoggerInterface;

final class DocumentFactsRepository
{
    private const TABLE = 'copilot_document_facts';

    public function __construct(
        private readonly LoggerInterface $logger,
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
        $this->ensureSchema();

        $docSha256Raw = $extractedDoc['document_sha256'] ?? '';
        $docTypeRaw   = $extractedDoc['doc_type'] ?? '';

        $docSha256 = is_string($docSha256Raw) ? $docSha256Raw : '';
        $docType   = is_string($docTypeRaw)   ? $docTypeRaw   : '';

        if ($docSha256 === '' || $docType === '') {
            $this->logger->error('DocumentFactsRepository: missing document_sha256 or doc_type in payload');
            return 0;
        }

        $result = $extractedDoc['result'] ?? [];
        if (!is_array($result)) {
            $this->logger->error('DocumentFactsRepository: result field is not an array in payload');
            return 0;
        }

        $fieldsRaw = $result['fields'] ?? null;
        /** @var list<array<string, mixed>> $fields */
        $fields = is_array($fieldsRaw) ? $fieldsRaw : [];
        if ($fields === []) {
            return 0;
        }

        $extractedByRaw = $result['extracted_by_model'] ?? 'unknown';
        $extractedAtRaw = $result['extracted_at'] ?? date('Y-m-d H:i:s');

        $extractedBy = is_string($extractedByRaw) ? $extractedByRaw : 'unknown';
        $extractedAt = is_string($extractedAtRaw) ? $extractedAtRaw : date('Y-m-d H:i:s');

        $patientHash  = hash('sha256', $patientUuid);
        $inserted     = 0;

        foreach ($fields as $field) {
            $fieldPathRaw = $field['name'] ?? '';
            $fieldPath = is_string($fieldPathRaw) ? $fieldPathRaw : '';
            if ($fieldPath === '') {
                continue;
            }

            $idempotencyKey = hash('sha256', $patientUuid . $docSha256 . $fieldPath);

            $citation = $field['citation'] ?? [];
            if (!is_array($citation)) {
                $citation = [];
            }

            $pageIndex = $citation['page_index'] ?? $field['page_index'] ?? null;
            $bboxValue = $citation['bbox'] ?? $field['bbox'] ?? null;
            $bboxJson = is_array($bboxValue)
                ? json_encode($bboxValue, JSON_THROW_ON_ERROR)
                : null;
            $bboxUnit = $citation['bbox_unit'] ?? $field['bbox_unit'] ?? null;
            $quote = $citation['quote_or_value'] ?? $field['quote_or_value'] ?? $field['value'] ?? null;
            $pageSection = $citation['page_or_section'] ?? $field['page_or_section'] ?? null;
            $confidence = $citation['confidence'] ?? $field['confidence'] ?? null;

            $confidenceFloat = null;
            if ($confidence !== null) {
                if (is_float($confidence)) {
                    $confidenceFloat = $confidence;
                } elseif (is_int($confidence)) {
                    $confidenceFloat = (float) $confidence;
                } elseif (is_numeric($confidence)) {
                    $confidenceFloat = (float) $confidence;
                }
            }

            $pageIndexInt = null;
            if ($pageIndex !== null) {
                if (is_int($pageIndex)) {
                    $pageIndexInt = $pageIndex;
                } elseif (is_numeric($pageIndex)) {
                    $pageIndexInt = (int) $pageIndex;
                }
            }

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
                $confidenceFloat,
                is_string($quote) ? $quote : null,
                $pageIndexInt,
                is_string($pageSection) ? $pageSection : null,
                is_string($bboxJson) ? $bboxJson : null,
                is_string($bboxUnit) ? $bboxUnit : null,
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
            } catch (\RuntimeException $e) {
                $this->logger->error('DocumentFactsRepository: insert failed', [
                    'field_path' => $fieldPath,
                    'exception'  => $e,
                ]);
                throw $e;
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
        $this->ensureSchema();

        $patientHash = hash('sha256', $patientUuid);

        /** @var list<array<string, mixed>> $rows */
        $rows = QueryUtils::fetchRecords(
            'SELECT * FROM `' . self::TABLE . '`
              WHERE `patient_uuid_hash` = ? AND `document_sha256` = ?
              ORDER BY `id`',
            [$patientHash, $documentSha256],
        );

        return $rows;
    }

    public function ensureSchema(): void
    {
        $migration = dirname(__DIR__, 2) . '/sql/migrations/2026_05_09_copilot_document_facts.sql';
        $sql = is_file($migration) ? file_get_contents($migration) : false;
        if (!is_string($sql) || trim($sql) === '') {
            $this->logger->error('DocumentFactsRepository: migration file missing');
            return;
        }

        try {
            QueryUtils::sqlStatementThrowException($sql);
        } catch (\RuntimeException $e) {
            $this->logger->error('DocumentFactsRepository: schema bootstrap failed', [
                'exception' => $e,
            ]);
            throw $e;
        }
    }
}
