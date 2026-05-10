<?php

/**
 * Source packet value object.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\SourcePackets;

final class PacketDto
{
    /**
     * @param array<string, mixed> $extra
     */
    public function __construct(
        public readonly string $sourceId,
        public readonly string $patientUuid,
        public readonly string $resourceType,
        public readonly string $sourceTable,
        public readonly ?string $sourceUuid,
        public readonly string $field,
        public readonly string $label,
        public readonly mixed $value,
        public readonly ?string $unit = null,
        public readonly ?string $observedAt = null,
        public readonly ?string $lastUpdated = null,
        public readonly string $freshness = 'unknown',
        public readonly ?string $status = null,
        public readonly array $extra = [],
    ) {
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        $base = [
            'source_id' => $this->sourceId,
            'patient_uuid' => $this->patientUuid,
            'resource_type' => $this->resourceType,
            'source_table' => $this->sourceTable,
            'source_uuid' => $this->sourceUuid,
            'field' => $this->field,
            'label' => $this->label,
            'value' => $this->value,
            'unit' => $this->unit,
            'observed_at' => $this->observedAt,
            'last_updated' => $this->lastUpdated,
            'freshness' => $this->freshness,
            'status' => $this->status,
        ];

        return array_merge($base, $this->extra);
    }
}
