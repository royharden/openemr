<?php

/**
 * Builds an identity source packet for the active patient.
 *
 * Reads patient_data via the bound legacy SQL API. Direct SQL is acceptable
 * inside the gateway because the gateway is the trust boundary; the sidecar
 * never sees SQL credentials.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\SourcePackets;

final class IdentityPacketBuilder implements PacketBuilder
{
    public function build(int $pid, string $patientUuid): array
    {
        $row = sqlQuery(
            "SELECT pid, fname, mname, lname, DOB, sex, language, status FROM patient_data WHERE pid = ?",
            [$pid]
        );
        if (empty($row)) {
            return [];
        }

        $name = trim(($row['fname'] ?? '') . ' ' . ($row['lname'] ?? ''));
        $age = null;
        if (!empty($row['DOB']) && $row['DOB'] !== '0000-00-00') {
            try {
                $dob = new \DateTimeImmutable((string)$row['DOB']);
                $now = new \DateTimeImmutable('now');
                $age = (int)$dob->diff($now)->y;
            } catch (\DateMalformedStringException) {
                // Plan §4.2 / AgDR-0082 — enumerated catch. DOB string can be
                // malformed for legacy patient_data rows (e.g. '0000-00-00'
                // was filtered above but other corrupt forms remain). Return
                // null age rather than treating the bad date as a clinical
                // signal.
                $age = null;
            }
        }

        $now = (new \DateTimeImmutable('now'))->format(\DateTimeInterface::ATOM);

        return [
            new PacketDto(
                sourceId: 'identity:patient_data:' . $pid,
                patientUuid: $patientUuid,
                resourceType: 'Patient',
                sourceTable: 'patient_data',
                sourceUuid: null,
                field: 'name',
                label: 'Patient name',
                value: $name !== '' ? $name : '(unknown)',
                lastUpdated: $now,
                freshness: 'recent',
                status: 'active',
            ),
            new PacketDto(
                sourceId: 'identity:patient_data:' . $pid . ':age',
                patientUuid: $patientUuid,
                resourceType: 'Patient',
                sourceTable: 'patient_data',
                sourceUuid: null,
                field: 'age',
                label: 'Age',
                value: $age,
                unit: 'years',
                observedAt: $row['DOB'] ?? null,
                lastUpdated: $now,
                freshness: 'recent',
                status: 'active',
            ),
            new PacketDto(
                sourceId: 'identity:patient_data:' . $pid . ':sex',
                patientUuid: $patientUuid,
                resourceType: 'Patient',
                sourceTable: 'patient_data',
                sourceUuid: null,
                field: 'sex',
                label: 'Sex at birth',
                value: $row['sex'] ?? null,
                lastUpdated: $now,
                freshness: 'recent',
                status: 'active',
            ),
        ];
    }
}
