<?php

/**
 * PacketBuilder for persisted document extraction facts (Wk2 Workstream A).
 *
 * DocumentUploadController stores source documents and extracted fields before
 * the graph turn starts. This builder rehydrates the current patient's latest
 * document facts into SourcePackets so attach_and_extract contributes evidence.
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Gateway;

use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\PacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\PacketDto;

final class AttachAndExtractStubBuilder implements PacketBuilder
{
    /**
     * @return list<PacketDto>
     */
    public function build(int $pid, string $patientUuid): array
    {
        $patientHash = hash('sha256', $patientUuid);

        try {
            // AgDR-0065 — LEFT JOIN copilot_fact_to_result_map so DocumentFact
            // packets can surface the FHIR Observation URL and OpenEMR Lab Review
            // URL on the source chip. The join is nullable: intake facts (and
            // any lab fact whose LabResultWriter run failed) will simply have
            // procedure_result_uuid_bin = NULL and the chip falls back to the
            // bbox overlay only.
            /** @var list<array<string, mixed>> $rows */
            $rows = QueryUtils::fetchRecords(
                'SELECT f.*, d.id AS document_id, d.uuid AS source_uuid_bin,
                        d.url AS document_url, d.name AS document_name,
                        m.procedure_result_id, m.procedure_result_uuid AS procedure_result_uuid_bin,
                        m.procedure_order_id, m.procedure_report_id
                   FROM `copilot_document_facts` f
              LEFT JOIN `documents` d ON d.uuid = f.document_uuid
              LEFT JOIN `copilot_fact_to_result_map` m ON m.copilot_document_fact_id = f.id
                  WHERE f.patient_uuid_hash = ?
               ORDER BY f.extracted_at DESC, f.id DESC
                  LIMIT 40',
                [$patientHash],
            );
        } catch (\PDOException | \RuntimeException) {
            return [];
        }

        $packets = [];
        foreach ($rows as $row) {
            $fieldPath = self::stringOrEmpty($row['field_path'] ?? null);
            if ($fieldPath === '') {
                continue;
            }

            $fieldValue = self::decodeJsonObject($row['field_value_json'] ?? null);
            $bbox = self::decodeJsonList($row['bbox_json'] ?? null);
            $docType = self::stringOrEmpty($row['doc_type'] ?? null);
            $value = $fieldValue['value'] ?? null;
            $label = self::fieldLabel($fieldPath, $docType);
            $resourceType = $docType === 'intake_form' ? 'QuestionnaireResponse' : 'Observation';

            $sourceUuid = null;
            $sourceUuidBin = $row['source_uuid_bin'] ?? null;
            if (is_string($sourceUuidBin) && strlen($sourceUuidBin) === 16) {
                $sourceUuid = UuidRegistry::uuidToString($sourceUuidBin);
            }

            // AgDR-0065 — if this fact has been written to the native lab chain,
            // surface its FHIR Observation UUID and Lab Review URL so the chip
            // popover can render the dual "View in OpenEMR Lab Review" /
            // "View as FHIR Observation" links.
            $procedureResultUuid = null;
            $procedureResultUuidBin = $row['procedure_result_uuid_bin'] ?? null;
            if (is_string($procedureResultUuidBin) && strlen($procedureResultUuidBin) === 16) {
                $procedureResultUuid = UuidRegistry::uuidToString($procedureResultUuidBin);
            }
            $webRoot = OEGlobalsBag::getInstance()->getWebRoot();
            $fhirObservationUrl = $procedureResultUuid !== null
                ? $webRoot . '/apis/default/fhir/Observation/' . rawurlencode($procedureResultUuid)
                : null;
            $procedureOrderId = self::idStringOrNull($row['procedure_order_id'] ?? null);
            $labReviewUrl = $procedureOrderId !== null
                ? $webRoot . '/interface/orders/orders_results.php?procedure_order_id=' . rawurlencode($procedureOrderId)
                : null;

            $extra = [
                'source_type' => 'document_extract',
                'field_or_chunk_id' => $fieldPath,
                'quote_or_value' => self::stringOrNull($row['quote_or_value'] ?? null),
                'bbox' => $bbox,
                'bbox_unit' => self::stringOrNull($row['bbox_unit'] ?? null),
                'page_index' => self::intOrNull($row['page_index'] ?? null),
                'page_or_section' => self::stringOrNull($row['page_or_section'] ?? null),
                'confidence' => self::floatOrNull($row['confidence'] ?? null),
                'document_sha256' => self::stringOrNull($row['document_sha256'] ?? null),
                'document_name' => self::stringOrNull($row['document_name'] ?? null),
                'doc_url' => self::documentUrl($pid, self::idStringOrNull($row['document_id'] ?? null)),
                'procedure_result_uuid' => $procedureResultUuid,
                'fhir_observation_url' => $fhirObservationUrl,
                'openemr_lab_review_url' => $labReviewUrl,
            ];

            $rawRowId = $row['id'] ?? null;
            $rowIdString = is_scalar($rawRowId) ? (string) $rawRowId : md5($patientHash . $fieldPath);

            $packets[] = new PacketDto(
                sourceId: 'document_fact:' . $rowIdString,
                patientUuid: $patientUuid,
                resourceType: $resourceType,
                sourceTable: 'copilot_document_facts',
                sourceUuid: $sourceUuid,
                field: $fieldPath,
                label: $label,
                value: $value,
                unit: self::stringOrNull($fieldValue['unit'] ?? null),
                observedAt: self::stringOrNull($row['extracted_at'] ?? null),
                lastUpdated: self::stringOrNull($row['updated_at'] ?? null),
                freshness: 'recent',
                status: self::stringOrNull($fieldValue['flag'] ?? null),
                extra: array_filter($extra, static fn(mixed $v): bool => $v !== null),
            );
        }

        return $packets;
    }

    private static function fieldLabel(string $fieldPath, string $docType): string
    {
        $label = str_replace(['_', '.'], ' ', $fieldPath);
        $label = trim(preg_replace('/\s+/', ' ', $label) ?? $fieldPath);
        $label = ucwords($label);

        return $docType === 'intake_form' ? 'Intake ' . $label : 'Document ' . $label;
    }

    /**
     * @return array<string, mixed>
     */
    private static function decodeJsonObject(mixed $value): array
    {
        if (!is_string($value) || $value === '') {
            return [];
        }

        $decoded = json_decode($value, true);
        if (!is_array($decoded)) {
            return [];
        }
        $result = [];
        foreach ($decoded as $k => $v) {
            if (is_string($k)) {
                $result[$k] = $v;
            }
        }
        return $result;
    }

    /**
     * @return list<float>|null
     */
    private static function decodeJsonList(mixed $value): ?array
    {
        if (!is_string($value) || $value === '') {
            return null;
        }

        $decoded = json_decode($value, true);
        if (!is_array($decoded) || count($decoded) !== 4) {
            return null;
        }

        $bbox = [];
        foreach ($decoded as $coordinate) {
            if (!is_numeric($coordinate)) {
                return null;
            }
            $bbox[] = (float) $coordinate;
        }

        return $bbox;
    }

    private static function stringOrNull(mixed $value): ?string
    {
        return is_string($value) && $value !== '' ? $value : null;
    }

    private static function idStringOrNull(mixed $value): ?string
    {
        if (is_int($value)) {
            return (string) $value;
        }
        if (is_string($value) && $value !== '') {
            return $value;
        }

        return null;
    }

    private static function stringOrEmpty(mixed $value): string
    {
        return is_string($value) ? $value : '';
    }

    private static function documentUrl(int $pid, ?string $documentId): ?string
    {
        if ($documentId === null || $documentId === '') {
            return null;
        }

        $webRoot = OEGlobalsBag::getInstance()->getWebRoot();
        return $webRoot . '/controller.php?document&retrieve&patient_id='
            . rawurlencode((string) $pid)
            . '&document_id=' . rawurlencode($documentId)
            . '&as_file=false&original_file=true&disable_exit=false&show_original=true';
    }

    private static function intOrNull(mixed $value): ?int
    {
        if (is_int($value)) {
            return $value;
        }

        return is_numeric($value) ? (int) $value : null;
    }

    private static function floatOrNull(mixed $value): ?float
    {
        if (is_float($value)) {
            return $value;
        }
        if (is_int($value)) {
            return (float) $value;
        }

        return is_numeric($value) ? (float) $value : null;
    }
}
