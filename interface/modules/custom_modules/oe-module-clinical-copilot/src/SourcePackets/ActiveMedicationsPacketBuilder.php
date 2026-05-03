<?php

/**
 * Builds active medication source packets, preferring the modern lists table
 * (type = 'medication') and supplementing with the prescriptions table.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\SourcePackets;

final class ActiveMedicationsPacketBuilder implements PacketBuilder
{
    private const STALE_DAYS_MED = 90;

    public function build(int $pid, string $patientUuid): array
    {
        $packets = [];

        $listsSql = "SELECT id, title, comments, begdate, enddate, modifydate, activity
                     FROM lists
                     WHERE pid = ?
                       AND type = 'medication'
                       AND activity = 1
                       AND (enddate IS NULL OR enddate = '0000-00-00' OR enddate = '')
                     ORDER BY begdate DESC, id DESC
                     LIMIT 25";
        $rs = sqlStatement($listsSql, [$pid]);
        while ($row = sqlFetchArray($rs)) {
            $observed = $row['begdate'] ?? null;
            $packets[] = new PacketDto(
                sourceId: 'med:lists:' . (int)$row['id'],
                patientUuid: $patientUuid,
                resourceType: 'MedicationStatement',
                sourceTable: 'lists',
                sourceUuid: (string)$row['id'],
                field: 'title',
                label: 'Active medication (problem list)',
                value: $row['title'],
                observedAt: $observed,
                lastUpdated: $row['modifydate'] ?? null,
                freshness: $this->freshnessFor($observed, self::STALE_DAYS_MED),
                status: 'active',
            );
        }

        // `date_added` is the row-creation timestamp and is what we'd prefer,
        // but it's nullable and frequently absent on rows imported from
        // external sources or seeded by fixtures. Fall back to `start_date`
        // (the prescribing date) and finally `date_modified` so freshness
        // calculation is correct against real-world data shapes.
        $rxSql = "SELECT id, drug, size, unit, dosage, quantity, date_added,
                         start_date, date_modified, active
                  FROM prescriptions
                  WHERE patient_id = ?
                    AND active = 1
                  ORDER BY COALESCE(date_added, start_date, date_modified) DESC, id DESC
                  LIMIT 25";
        $rs = sqlStatement($rxSql, [$pid]);
        while ($row = sqlFetchArray($rs)) {
            $observed = $row['date_added']
                ?: ($row['start_date']
                    ?: $row['date_modified']);
            $packets[] = new PacketDto(
                sourceId: 'rx:prescriptions:' . (int)$row['id'],
                patientUuid: $patientUuid,
                resourceType: 'MedicationRequest',
                sourceTable: 'prescriptions',
                sourceUuid: (string)$row['id'],
                field: 'drug',
                label: 'Active prescription',
                value: $row['drug'],
                unit: $row['unit'] ?? null,
                observedAt: $observed,
                lastUpdated: $observed,
                freshness: $this->freshnessFor($observed, self::STALE_DAYS_MED),
                status: 'active',
            );
        }

        return $packets;
    }

    private function freshnessFor(?string $observed, int $staleDays): string
    {
        if (empty($observed) || str_starts_with($observed, '0000')) {
            return 'unknown';
        }
        try {
            $when = new \DateTimeImmutable($observed);
            $diff = (new \DateTimeImmutable('now'))->diff($when)->days;
            return ($diff !== false && $diff > $staleDays) ? 'stale' : 'recent';
        } catch (\Throwable $e) {
            return 'unknown';
        }
    }
}
