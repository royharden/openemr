<?php

/**
 * Builds recent lab-result source packets, preferring abnormal flags first.
 *
 * Joins procedure_order → procedure_report → procedure_result so that every
 * cited lab carries its own datestamp and abnormality flag. Caps at 20 rows
 * per turn; older than 180 days is labeled `freshness=stale` so the
 * stale_data_uncaveat verifier rule can fire.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\SourcePackets;

final class RecentLabsPacketBuilder implements PacketBuilder
{
    private const STALE_DAYS = 180;

    public function build(int $pid, string $patientUuid): array
    {
        $sql = "SELECT pr.procedure_result_id AS id,
                       pr.result_code,
                       pr.result_text,
                       pr.result,
                       pr.units,
                       pr.range,
                       pr.abnormal,
                       pr.result_status,
                       pr.date AS result_date,
                       prep.date_report,
                       prep.date_collected
                FROM procedure_result AS pr
                INNER JOIN procedure_report AS prep
                        ON prep.procedure_report_id = pr.procedure_report_id
                INNER JOIN procedure_order AS po
                        ON po.procedure_order_id = prep.procedure_order_id
                WHERE po.patient_id = ?
                ORDER BY (pr.abnormal IN ('yes','high','low')) DESC,
                         COALESCE(pr.date, prep.date_report, prep.date_collected) DESC,
                         pr.procedure_result_id DESC
                LIMIT 20";
        $rs = sqlStatement($sql, [$pid]);

        $packets = [];
        while ($row = sqlFetchArray($rs)) {
            $observed = $row['result_date']
                ?: ($row['date_report'] ?: $row['date_collected']);
            $resultStatus = strtolower((string)($row['result_status'] ?? ''));
            $abnormalRaw = strtolower((string)($row['abnormal'] ?? ''));
            $isAbnormal = in_array($abnormalRaw, ['yes', 'high', 'low'], true);
            $label = $row['result_text'] !== '' ? (string)$row['result_text'] : (string)$row['result_code'];
            $value = trim((string)$row['result']);
            if ($isAbnormal) {
                $value .= " (abnormal: {$abnormalRaw})";
            }

            $status = match (true) {
                in_array($resultStatus, ['final', 'corrected', 'complete'], true) => 'final',
                $resultStatus === 'preliminary' => 'preliminary',
                $resultStatus === '' => 'unknown',
                default => $resultStatus,
            };

            $packets[] = new PacketDto(
                sourceId: 'lab:procedure_result:' . (int)$row['id'],
                patientUuid: $patientUuid,
                resourceType: 'Observation',
                sourceTable: 'procedure_result',
                sourceUuid: (string)$row['id'],
                field: 'result',
                label: $label !== '' ? $label : 'Lab result',
                value: $value !== '' ? $value : null,
                unit: $row['units'] ?: null,
                observedAt: $observed,
                lastUpdated: $row['date_report'] ?? $observed,
                freshness: $this->freshnessFor($observed),
                status: $status,
            );
        }

        return $packets;
    }

    private function freshnessFor(?string $observed): string
    {
        if (empty($observed) || $observed === '0000-00-00') {
            return 'unknown';
        }
        try {
            $when = new \DateTimeImmutable($observed);
            $diff = (new \DateTimeImmutable('now'))->diff($when)->days;
            return ($diff !== false && $diff > self::STALE_DAYS) ? 'stale' : 'recent';
        } catch (\DateMalformedStringException) {
            // Plan §4.2 / AgDR-0082 — enumerated catch.
            return 'unknown';
        }
    }
}
