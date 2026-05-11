<?php

/**
 * Builds allergy / intolerance source packets from the lists table.
 *
 * Returns explicit packets for both populated allergies AND a synthetic NKDA
 * marker when the patient has been actively recorded as having no known
 * drug allergies, so the verifier's blank-vs-negative rule can distinguish
 * "no record retrieved" from "explicit negative".
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\SourcePackets;

final class AllergiesPacketBuilder implements PacketBuilder
{
    private const STALE_DAYS = 365;

    public function build(int $pid, string $patientUuid): array
    {
        $sql = "SELECT id, title, comments, severity_al, reaction, begdate, enddate, modifydate, activity, outcome
                FROM lists
                WHERE pid = ?
                  AND type = 'allergy'
                ORDER BY activity DESC, begdate DESC, id DESC
                LIMIT 25";
        $rs = sqlStatement($sql, [$pid]);

        $packets = [];
        $sawActive = false;
        $sawExplicitNkda = false;
        while ($row = sqlFetchArray($rs)) {
            $title = trim((string)($row['title'] ?? ''));
            $observed = $row['begdate'] ?? null;
            $isActive = ((int)($row['activity'] ?? 0)) === 1
                && (empty($row['enddate']) || $row['enddate'] === '0000-00-00');

            $isNkda = $title !== ''
                && preg_match('/\b(nkda|no\s+known(\s+drug)?\s+allergies?)\b/i', $title) === 1;

            if ($isNkda) {
                $sawExplicitNkda = true;
                $packets[] = new PacketDto(
                    sourceId: 'allergy:lists:' . (int)$row['id'],
                    patientUuid: $patientUuid,
                    resourceType: 'AllergyIntolerance',
                    sourceTable: 'lists',
                    sourceUuid: (string)$row['id'],
                    field: 'title',
                    label: 'Allergy (no known)',
                    value: 'NKDA',
                    observedAt: $observed,
                    lastUpdated: $row['modifydate'] ?? null,
                    freshness: $this->freshnessFor($observed),
                    status: $isActive ? 'active' : 'inactive',
                );
                continue;
            }

            $reaction = trim((string)($row['reaction'] ?? ''));
            $severity = trim((string)($row['severity_al'] ?? ''));
            $valueParts = array_filter([
                $title,
                $reaction !== '' ? "reaction: {$reaction}" : '',
                $severity !== '' ? "severity: {$severity}" : '',
            ], static fn ($s) => $s !== '');

            if ($isActive) {
                $sawActive = true;
            }

            $packets[] = new PacketDto(
                sourceId: 'allergy:lists:' . (int)$row['id'],
                patientUuid: $patientUuid,
                resourceType: 'AllergyIntolerance',
                sourceTable: 'lists',
                sourceUuid: (string)$row['id'],
                field: 'title',
                label: 'Allergy',
                value: implode('; ', $valueParts),
                observedAt: $observed,
                lastUpdated: $row['modifydate'] ?? null,
                freshness: $this->freshnessFor($observed),
                status: $isActive ? 'active' : 'inactive',
            );
        }

        // No rows at all = absence of *retrieved data*. Don't synthesize NKDA —
        // the verifier's blank_vs_negative rule will (correctly) drop any
        // "no allergies" claim made against zero packets.
        if (!$sawActive && !$sawExplicitNkda && $packets === []) {
            return [];
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
