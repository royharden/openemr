<?php

/**
 * Builds immunization source packets from the immunizations table.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\SourcePackets;

final class ImmunizationsPacketBuilder implements PacketBuilder
{
    private const STALE_DAYS = 1825;

    public function build(int $pid, string $patientUuid): array
    {
        $sql = "SELECT i.id, i.uuid, i.administered_date, i.cvx_code, i.manufacturer,
                       lo.title AS code_title, i.note, i.completion_status, i.added_erroneously
                FROM immunizations AS i
                LEFT JOIN list_options AS lo
                       ON lo.list_id = 'immunizations'
                      AND lo.option_id = i.cvx_code
                WHERE i.patient_id = ?
                  AND (i.added_erroneously IS NULL OR i.added_erroneously = 0)
                ORDER BY i.administered_date DESC, i.id DESC
                LIMIT 20";
        $rs = sqlStatement($sql, [$pid]);

        $packets = [];
        while ($row = sqlFetchArray($rs)) {
            $observed = $row['administered_date'] ?? null;
            $title = trim((string)($row['code_title'] ?? ''));
            if ($title === '') {
                $title = 'CVX ' . (string)($row['cvx_code'] ?? '');
            }
            $completion = strtolower((string)($row['completion_status'] ?? ''));
            $status = match ($completion) {
                'completed' => 'completed',
                'partially administered' => 'partial',
                'refused' => 'refused',
                'not administered' => 'inactive',
                '' => 'completed',
                default => $completion,
            };

            $packets[] = new PacketDto(
                sourceId: 'immunization:immunizations:' . (int)$row['id'],
                patientUuid: $patientUuid,
                resourceType: 'Immunization',
                sourceTable: 'immunizations',
                sourceUuid: (string)$row['id'],
                field: 'cvx_code',
                label: 'Immunization',
                value: $title,
                observedAt: $observed,
                lastUpdated: $observed,
                freshness: $this->freshnessFor($observed),
                status: $status,
            );
        }

        return $packets;
    }

    private function freshnessFor(?string $observed): string
    {
        if (empty($observed) || str_starts_with((string)$observed, '0000')) {
            return 'unknown';
        }
        try {
            $when = new \DateTimeImmutable((string)$observed);
            $diff = (new \DateTimeImmutable('now'))->diff($when)->days;
            return ($diff !== false && $diff > self::STALE_DAYS) ? 'stale' : 'recent';
        } catch (\Throwable $e) {
            return 'unknown';
        }
    }
}
