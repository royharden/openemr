<?php

/**
 * Writes Co-Pilot extracted lab facts to OpenEMR's native lab chain
 * (procedure_order / procedure_order_code / procedure_report / procedure_result)
 * so the existing FhirObservationLaboratoryService surfaces them as
 * FHIR Observation resources.
 *
 * AgDR-0065 (supersedes AgDR-0037's "defer to Wk3") — closes the FHIR /
 * OpenEMR Integrity gate in the Wk2 PRD.
 *
 * Pattern:
 *   * One procedure_order per extracted fact (1:1:1 with procedure_report and
 *     procedure_result). This matches the Maria G. seed shape and avoids the
 *     cartesian-join issue that arises when multiple procedure_result rows
 *     share a single (order_id, order_seq) pair.
 *   * procedure_order_code is the JOIN target the FHIR read path requires —
 *     see agent_lessons "OpenEMR lab FHIR search needs order-code rows or
 *     Observation laboratory returns zero." We always insert one per fact.
 *   * procedure_result.comments carries a "[copilot-extracted: doc_uuid=...]"
 *     provenance prefix so a clinician on the Lab Review screen can tell
 *     this row came from a Co-Pilot upload, not a clinician entry. The reset
 *     script does NOT key on this string — it keys on the
 *     copilot_fact_to_result_map rows, which gives exactly-once cleanup.
 *
 * Idempotency:
 *   * copilot_fact_to_result_map has UNIQUE(copilot_document_fact_id).
 *   * We skip any fact whose id already appears in the map.
 *   * Repeated calls for the same (patient, document) are silent no-ops.
 *
 * Best-effort failure mode:
 *   * Every step is wrapped in a transaction. On any throw, we ROLLBACK so
 *     no orphaned procedure_* rows leak. The throw is logged and the upload
 *     is NOT failed — the extracted facts still live in copilot_document_facts
 *     and can be retried by a janitor or a subsequent re-upload.
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Service;

use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Logging\SystemLogger;
use OpenEMR\Common\Uuid\UuidRegistry;

final class LabResultWriter
{
    private const TABLE_ORDER = 'procedure_order';
    private const TABLE_ORDER_CODE = 'procedure_order_code';
    private const TABLE_REPORT = 'procedure_report';
    private const TABLE_RESULT = 'procedure_result';
    private const MAP_TABLE = 'copilot_fact_to_result_map';

    /**
     * Fallback LOINC mapping for common lab field paths. Used when the sidecar
     * extractor does not emit `field_value_json.loinc_code`. Match is on the
     * lowercased tail of the field_path (e.g. "lipid.ldl_cholesterol_calculated"
     * → matches the key "ldl_cholesterol_calculated").
     *
     * Without this fallback, facts without LOINC are skipped by writeOneFact()
     * and the FHIR Observation read path never sees them. This map is the
     * minimum set that covers the four fixture documents (lipid panel, CBC,
     * HbA1c, CMP) at openemr/agent/copilot-api/evals/fixtures/documents/.
     *
     * Source: LOINC.org canonical codes.
     */
    private const FIELD_PATH_TO_LOINC = [
        // Lipid panel
        'cholesterol_total' => '2093-3',
        'total_cholesterol' => '2093-3',
        'hdl_cholesterol' => '2085-9',
        'hdl' => '2085-9',
        'ldl_cholesterol' => '13457-7',
        'ldl_cholesterol_calculated' => '13457-7',
        'ldl_calculated' => '13457-7',
        'ldl' => '13457-7',
        'triglycerides' => '2571-8',
        'non_hdl_cholesterol' => '43396-1',
        'non_hdl' => '43396-1',
        // CBC
        'wbc' => '6690-2',
        'white_blood_cell_count' => '6690-2',
        'rbc' => '789-8',
        'red_blood_cell_count' => '789-8',
        'hemoglobin' => '718-7',
        'hematocrit' => '4544-3',
        'platelets' => '777-3',
        'platelet_count' => '777-3',
        'mcv' => '787-2',
        'mch' => '785-6',
        'mchc' => '786-4',
        // HbA1c
        'hba1c' => '4548-4',
        'a1c' => '4548-4',
        'hemoglobin_a1c' => '4548-4',
        'glycated_hemoglobin' => '4548-4',
        // CMP / BMP
        'glucose' => '2345-7',
        'bun' => '3094-0',
        'blood_urea_nitrogen' => '3094-0',
        'creatinine' => '2160-0',
        'egfr' => '33914-3',
        'sodium' => '2951-2',
        'potassium' => '2823-3',
        'chloride' => '2075-0',
        'co2' => '2028-9',
        'bicarbonate' => '1959-6',
        'calcium' => '17861-6',
        'total_protein' => '2885-2',
        'albumin' => '1751-7',
        'bilirubin_total' => '1975-2',
        'total_bilirubin' => '1975-2',
        'alkaline_phosphatase' => '6768-6',
        'alt' => '1742-6',
        'ast' => '1920-8',
    ];

    public function __construct(
        private readonly SystemLogger $logger,
    ) {}

    /**
     * Idempotently write all unmapped lab facts for one (patient, document)
     * pair into OpenEMR's native lab chain.
     *
     * @param int    $patientId       patient_data.pid
     * @param string $patientUuid     raw 36-char UUID string (used to hash the fact lookup)
     * @param int    $documentId      OpenEMR documents.id (the source PDF)
     * @param string $documentUuidStr OpenEMR documents.uuid (string form, for the provenance tag)
     * @param string $documentSha256  hex SHA-256 of the source document body
     * @param int    $providerId      OpenEMR user id of the uploader
     *
     * @return array{written: int, skipped: int, fact_ids: list<int>, result_ids: list<int>}
     */
    public function writeLabFactsForDocument(
        int $patientId,
        string $patientUuid,
        int $documentId,
        string $documentUuidStr,
        string $documentSha256,
        int $providerId,
    ): array {
        $this->ensureMapSchema();

        $facts = $this->loadUnmappedLabFacts($patientUuid, $documentSha256);
        if ($facts === []) {
            return ['written' => 0, 'skipped' => 0, 'fact_ids' => [], 'result_ids' => []];
        }

        $written = 0;
        $skipped = 0;
        $writtenFactIds = [];
        $writtenResultIds = [];

        foreach ($facts as $fact) {
            try {
                $resultId = $this->writeOneFact(
                    $fact,
                    $patientId,
                    $documentId,
                    $documentUuidStr,
                    $providerId,
                );
                if ($resultId !== null) {
                    $written++;
                    $writtenFactIds[] = (int) $fact['id'];
                    $writtenResultIds[] = $resultId;
                } else {
                    $skipped++;
                }
            } catch (\Throwable $exc) {
                $skipped++;
                $this->logger->warning(
                    'LabResultWriter: per-fact write failed (best-effort, continuing)',
                    [
                        'fact_id' => $fact['id'] ?? null,
                        'exception' => $exc,
                    ],
                );
            }
        }

        return [
            'written' => $written,
            'skipped' => $skipped,
            'fact_ids' => $writtenFactIds,
            'result_ids' => $writtenResultIds,
        ];
    }

    /**
     * Resolve a fact id to its FHIR Observation UUID (string form) for the
     * UI source-chip dual-link beat. Returns null if the fact has not been
     * mapped to a procedure_result yet (e.g., not a lab_pdf, or the writer
     * has not run).
     */
    public function findObservationUuidForFact(int $factId): ?string
    {
        try {
            $uuidBin = QueryUtils::fetchSingleValue(
                'SELECT procedure_result_uuid FROM `' . self::MAP_TABLE . '`
                  WHERE copilot_document_fact_id = ?
                  LIMIT 1',
                'procedure_result_uuid',
                [$factId],
            );
        } catch (\Throwable $exc) {
            $this->logger->warning(
                'LabResultWriter: map lookup failed',
                ['fact_id' => $factId, 'exception' => $exc],
            );
            return null;
        }
        if (!is_string($uuidBin) || strlen($uuidBin) !== 16) {
            return null;
        }
        return UuidRegistry::uuidToString($uuidBin);
    }

    // ------------------------------------------------------------------
    // Private helpers
    // ------------------------------------------------------------------

    /**
     * @return list<array<string, mixed>>
     */
    private function loadUnmappedLabFacts(string $patientUuid, string $documentSha256): array
    {
        $patientHash = hash('sha256', $patientUuid);
        try {
            /** @var list<array<string, mixed>> $rows */
            $rows = QueryUtils::fetchRecords(
                'SELECT f.id, f.field_path, f.field_value_json, f.quote_or_value,
                        f.confidence, f.extracted_at
                   FROM copilot_document_facts AS f
                  WHERE f.patient_uuid_hash = ?
                    AND f.document_sha256   = ?
                    AND f.doc_type          = "lab_pdf"
                    AND NOT EXISTS (
                        SELECT 1 FROM `' . self::MAP_TABLE . '` AS m
                         WHERE m.copilot_document_fact_id = f.id
                    )
                  ORDER BY f.id',
                [$patientHash, $documentSha256],
            );
            return $rows;
        } catch (\Throwable $exc) {
            $this->logger->warning(
                'LabResultWriter: unmapped-fact query failed',
                ['exception' => $exc],
            );
            return [];
        }
    }

    /**
     * Write one extracted lab fact as a complete (order, order_code, report,
     * result, map) chain inside a single transaction.
     *
     * Returns the procedure_result.procedure_result_id on success, or null
     * if the fact lacked a LOINC code (cannot surface as a FHIR Observation
     * without one — log and skip).
     *
     * @param array<string, mixed> $fact
     */
    private function writeOneFact(
        array $fact,
        int $patientId,
        int $documentId,
        string $documentUuidStr,
        int $providerId,
    ): ?int {
        $fieldValue = json_decode(
            is_string($fact['field_value_json']) ? $fact['field_value_json'] : '[]',
            true,
            512,
            JSON_THROW_ON_ERROR,
        );
        if (!is_array($fieldValue)) {
            $fieldValue = [];
        }

        $loinc = $fieldValue['loinc_code'] ?? null;
        if (!is_string($loinc) || $loinc === '') {
            // Sidecar extractor may not emit loinc_code reliably for every
            // fixture; consult the in-class FIELD_PATH_TO_LOINC fallback.
            $loinc = $this->loincFromFieldPath(
                is_string($fact['field_path'] ?? null) ? (string) $fact['field_path'] : '',
            );
        }
        if (!is_string($loinc) || $loinc === '') {
            $this->logger->info(
                'LabResultWriter: skipping fact without LOINC code (cannot surface as FHIR Observation)',
                ['fact_id' => $fact['id'] ?? null, 'field_path' => $fact['field_path'] ?? null],
            );
            return null;
        }

        $value = $fieldValue['value'] ?? null;
        $units = $fieldValue['unit'] ?? null;
        $range = $this->normalizeReferenceRange($fieldValue['reference_range'] ?? null);
        $abnormal = $this->normalizeAbnormalFlag($fieldValue['flag'] ?? null);
        $resultDate = $this->normalizeResultDate($fact['extracted_at'] ?? null);
        $displayName = $this->resolveDisplayName(
            is_string($fact['field_path']) ? $fact['field_path'] : '',
            $loinc,
        );

        $provenanceComment = sprintf(
            '[copilot-extracted: doc_uuid=%s; fact_id=%d; extraction=%s]',
            $documentUuidStr,
            (int) $fact['id'],
            (string) ($fact['extracted_at'] ?? ''),
        );
        if (is_string($fact['quote_or_value']) && $fact['quote_or_value'] !== '') {
            $provenanceComment .= ' Quote: ' . substr($fact['quote_or_value'], 0, 240);
        }

        // --- Transaction begin ---
        QueryUtils::sqlStatementThrowException('START TRANSACTION');
        try {
            // 1) procedure_order
            QueryUtils::sqlStatementThrowException(
                'INSERT INTO `' . self::TABLE_ORDER . '`
                    (patient_id, provider_id, date_ordered, date_collected,
                     order_status, procedure_order_type, activity,
                     order_diagnosis, clinical_hx, patient_instructions)
                 VALUES (?, ?, ?, ?, "complete", "laboratory_test", 1,
                         "copilot-extracted", ?, NULL)',
                [
                    $patientId,
                    $providerId > 0 ? $providerId : null,
                    $resultDate,
                    $resultDate,
                    $provenanceComment,
                ],
            );
            $orderId = $this->lastInsertId();

            // 2) procedure_order_code  (REQUIRED for FHIR Observation visibility)
            QueryUtils::sqlStatementThrowException(
                'INSERT INTO `' . self::TABLE_ORDER_CODE . '`
                    (procedure_order_id, procedure_order_seq, procedure_code,
                     procedure_name, procedure_order_title, procedure_type)
                 VALUES (?, 1, ?, ?, ?, "laboratory_test")',
                [$orderId, $loinc, $displayName, $displayName],
            );

            // 3) procedure_report  — seq=1 to match the order_code seq
            QueryUtils::sqlStatementThrowException(
                'INSERT INTO `' . self::TABLE_REPORT . '`
                    (procedure_order_id, procedure_order_seq, date_collected,
                     date_report, report_status, review_status)
                 VALUES (?, 1, ?, ?, "complete", "reviewed")',
                [$orderId, $resultDate, $resultDate],
            );
            $reportId = $this->lastInsertId();

            // 4) procedure_result — `units` and `range` are declared NOT NULL
            //     in the OpenEMR schema. The extractor can return null for
            //     either, so coerce to empty string here (matches Maria G.
            //     seed shape; non-null was an unexpected hard constraint).
            QueryUtils::sqlStatementThrowException(
                'INSERT INTO `' . self::TABLE_RESULT . '`
                    (procedure_report_id, result_data_type, result_code,
                     result_text, result, units, `range`, abnormal,
                     `comments`, date, result_status, document_id)
                 VALUES (?, "N", ?, ?, ?, ?, ?, ?, ?, ?, "final", ?)',
                [
                    $reportId,
                    $loinc,
                    $displayName,
                    $value !== null ? (string) $value : '',
                    is_string($units) ? $units : '',
                    is_string($range) ? $range : '',
                    is_string($abnormal) ? $abnormal : 'no',
                    $provenanceComment,
                    $resultDate,
                    $documentId > 0 ? $documentId : null,
                ],
            );
            $resultId = $this->lastInsertId();

            // 5) Mint UUIDs via the same path the FHIR read uses.
            UuidRegistry::createMissingUuidsForTables([
                self::TABLE_ORDER,
                self::TABLE_REPORT,
                self::TABLE_RESULT,
            ]);

            // 6) Fetch the freshly-minted procedure_result.uuid for the map.
            $resultUuidBin = QueryUtils::fetchSingleValue(
                'SELECT uuid FROM `' . self::TABLE_RESULT . '` WHERE procedure_result_id = ?',
                'uuid',
                [$resultId],
            );
            if (!is_string($resultUuidBin) || strlen($resultUuidBin) !== 16) {
                throw new \RuntimeException('procedure_result.uuid was not minted');
            }

            // 7) Map.  UNIQUE on copilot_document_fact_id — concurrent writer
            //     would hit the unique constraint, INSERT IGNORE handles that.
            QueryUtils::sqlStatementThrowException(
                'INSERT IGNORE INTO `' . self::MAP_TABLE . '`
                    (copilot_document_fact_id, procedure_order_id,
                     procedure_report_id, procedure_result_id,
                     procedure_result_uuid)
                 VALUES (?, ?, ?, ?, ?)',
                [(int) $fact['id'], $orderId, $reportId, $resultId, $resultUuidBin],
            );

            QueryUtils::sqlStatementThrowException('COMMIT');
            return $resultId;
        } catch (\Throwable $exc) {
            try {
                QueryUtils::sqlStatementThrowException('ROLLBACK');
            } catch (\Throwable $rollbackExc) {
                $this->logger->error(
                    'LabResultWriter: rollback also failed',
                    ['exception' => $rollbackExc],
                );
            }
            throw $exc;
        }
    }

    private function lastInsertId(): int
    {
        /** @var int|string|null $id */
        $id = QueryUtils::fetchSingleValue('SELECT LAST_INSERT_ID() AS lid', 'lid', []);
        return (int) $id;
    }

    /**
     * Resolve a LOINC code from a field path tail. Returns null if no match.
     */
    private function loincFromFieldPath(string $fieldPath): ?string
    {
        $path = strtolower(trim($fieldPath));
        if ($path === '') {
            return null;
        }
        $segments = explode('.', $path);
        $tail = end($segments);
        if (!is_string($tail) || $tail === '') {
            return null;
        }
        return self::FIELD_PATH_TO_LOINC[$tail] ?? null;
    }

    /**
     * Map the sidecar's abnormal flag onto OpenEMR's list_options
     * lo_abnormal codes — "no", "yes", "high", "low".
     */
    private function normalizeAbnormalFlag(mixed $flag): string
    {
        if (!is_string($flag) || $flag === '') {
            return 'no';
        }
        $f = strtolower(trim($flag));
        return match ($f) {
            'h', 'high', 'high_abnormal', 'hh' => 'high',
            'l', 'low', 'low_abnormal', 'll' => 'low',
            'a', 'abn', 'abnormal', 'yes' => 'yes',
            'n', 'normal', 'no', '' => 'no',
            default => 'no',
        };
    }

    /**
     * Normalize a reference range into OpenEMR's "low-high" string shape.
     * Accepts strings already in "low-high" form, structured dicts with
     * low/high keys, or nulls.
     */
    private function normalizeReferenceRange(mixed $range): ?string
    {
        if (is_string($range) && $range !== '') {
            return $range;
        }
        if (is_array($range)) {
            $low = $range['low'] ?? null;
            $high = $range['high'] ?? null;
            if ($low !== null && $high !== null) {
                return sprintf('%s-%s', (string) $low, (string) $high);
            }
            if (isset($range['text']) && is_string($range['text'])) {
                return $range['text'];
            }
        }
        return null;
    }

    /**
     * Coerce the extracted-at timestamp to "Y-m-d H:i:s" — the shape
     * procedure_report.date_report and procedure_result.date use.
     */
    private function normalizeResultDate(mixed $extractedAt): string
    {
        if (is_string($extractedAt) && $extractedAt !== '') {
            // Strip a trailing 'Z' or '+00:00' if present.
            $candidate = preg_replace('/(Z|[+\-]\d{2}:?\d{2})$/', '', $extractedAt);
            if (is_string($candidate)) {
                try {
                    $dt = new \DateTimeImmutable($candidate);
                    return $dt->format('Y-m-d H:i:s');
                } catch (\Exception) {
                    // fall through
                }
            }
        }
        return date('Y-m-d H:i:s');
    }

    /**
     * Build a display name for the procedure_order_code.procedure_name and
     * procedure_result.result_text columns. Prefer a short title derived
     * from the field_path; fall back to the LOINC code.
     */
    private function resolveDisplayName(string $fieldPath, string $loinc): string
    {
        $path = trim($fieldPath);
        if ($path !== '') {
            $segments = explode('.', $path);
            $last = end($segments);
            if (is_string($last) && $last !== '') {
                return str_replace('_', ' ', $last);
            }
        }
        return 'LOINC ' . $loinc;
    }

    /**
     * Apply the map-table migration on demand (mirrors DocumentFactsRepository's
     * ensureSchema pattern). Idempotent — uses CREATE TABLE IF NOT EXISTS.
     */
    public function ensureMapSchema(): void
    {
        $migration = dirname(__DIR__, 2) . '/sql/migrations/2026_05_10_copilot_fact_to_result_map.sql';
        $sql = is_file($migration) ? file_get_contents($migration) : false;
        if (!is_string($sql) || trim($sql) === '') {
            $this->logger->error('LabResultWriter: map-table migration file missing');
            return;
        }
        try {
            QueryUtils::sqlStatementThrowException($sql);
        } catch (\Throwable $exc) {
            $this->logger->error(
                'LabResultWriter: map-table schema bootstrap failed',
                ['exception' => $exc],
            );
            throw $exc;
        }
    }
}
