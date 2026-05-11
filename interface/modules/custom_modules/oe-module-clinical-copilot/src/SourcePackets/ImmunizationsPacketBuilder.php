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
        $sql = "SELECT i.id, i.uuid, i.administered_date, i.immunization_id,
                       i.cvx_code, i.manufacturer, i.note, i.completion_status,
                       i.added_erroneously,
                       c.code_text AS cvx_text,
                       c.code_text_short AS cvx_text_short,
                       lo.title AS custom_title
                FROM immunizations AS i
                LEFT JOIN code_types AS ct
                       ON ct.ct_key = 'CVX'
                LEFT JOIN codes AS c
                       ON c.code_type = ct.ct_id
                      AND c.code = i.cvx_code
                LEFT JOIN list_options AS lo
                       ON lo.list_id = 'immunizations'
                      AND lo.option_id = i.immunization_id
                WHERE i.patient_id = ?
                  AND (i.added_erroneously IS NULL OR i.added_erroneously = 0)
                ORDER BY i.administered_date DESC, i.id DESC
                LIMIT 20";
        $rs = sqlStatement($sql, [$pid]);

        $packets = [];
        while ($row = sqlFetchArray($rs)) {
            $observed = $row['administered_date'] ?? null;
            $title = $this->titleFor($row);
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

    /**
     * Resolve the display name the same way OpenEMR's immunization card does:
     * CVX code text comes from `codes`, while `list_options('immunizations')`
     * is the legacy custom immunization list keyed by `immunization_id`.
     *
     * @param array<string, mixed> $row
     */
    private function titleFor(array $row): string
    {
        foreach (['cvx_text', 'cvx_text_short', 'custom_title', 'note'] as $key) {
            $title = trim((string)($row[$key] ?? ''));
            if ($title !== '') {
                return $title;
            }
        }

        $cvx = trim((string)($row['cvx_code'] ?? ''));
        return $cvx !== '' ? 'CVX ' . $cvx : 'Immunization';
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
        } catch (\DateMalformedStringException) {
            // Plan §4.2 / AgDR-0082 — enumerated catch.
            return 'unknown';
        }
    }
}
