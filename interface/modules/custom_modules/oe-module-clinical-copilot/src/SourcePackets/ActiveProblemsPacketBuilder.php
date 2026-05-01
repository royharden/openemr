<?php

/**
 * Builds active problem source packets from the lists table.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\SourcePackets;

final class ActiveProblemsPacketBuilder implements PacketBuilder
{
    private const STALE_DAYS = 365;

    public function build(int $pid, string $patientUuid): array
    {
        $sql = "SELECT id, title, diagnosis, begdate, enddate, date, modifydate, activity, outcome
                FROM lists
                WHERE pid = ?
                  AND type = 'medical_problem'
                  AND activity = 1
                  AND (enddate IS NULL OR enddate = '0000-00-00' OR enddate = '')
                ORDER BY begdate DESC, id DESC
                LIMIT 25";
        $rs = sqlStatement($sql, [$pid]);

        $packets = [];
        while ($row = sqlFetchArray($rs)) {
            $observed = $row['begdate'] ?? null;
            $freshness = $this->freshnessFor($observed);
            $packets[] = new PacketDto(
                sourceId: 'problem:lists:' . (int)$row['id'],
                patientUuid: $patientUuid,
                resourceType: 'Condition',
                sourceTable: 'lists',
                sourceUuid: (string)$row['id'],
                field: 'title',
                label: 'Active problem',
                value: $row['title'] ?: ($row['diagnosis'] ?? null),
                observedAt: $observed,
                lastUpdated: $row['modifydate'] ?? $row['date'] ?? null,
                freshness: $freshness,
                status: 'active',
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
        } catch (\Throwable $e) {
            return 'unknown';
        }
    }
}
