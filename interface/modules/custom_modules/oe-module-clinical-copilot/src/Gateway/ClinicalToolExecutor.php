<?php

/**
 * Executes LLM-selected clinical data tools inside the OpenEMR trust boundary.
 *
 * The sidecar may plan tool names, but it never receives database credentials
 * and it never supplies a patient identifier. This executor binds every call to
 * the current OpenEMR session patient and allowlisted read-only builders.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Gateway;

use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ActiveMedicationsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ActiveProblemsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\AllergiesPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\IdentityPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\ImmunizationsPacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\PacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\RecentLabsPacketBuilder;

final class ClinicalToolExecutor
{
    private const PACKET_CAP = 50;
    private const FORBIDDEN_ARGUMENTS = [
        'pid',
        'patient_id',
        'patient_uuid',
        'patient_uuid_hash',
        'sql',
        'query',
        'table',
        'table_name',
        'source_id',
    ];

    /** @var array<string, PacketBuilder> */
    private array $builders;

    public function __construct()
    {
        $this->builders = [
            'get_patient_identity' => new IdentityPacketBuilder(),
            'get_active_problems' => new ActiveProblemsPacketBuilder(),
            'get_active_medications' => new ActiveMedicationsPacketBuilder(),
            'get_allergy_list' => new AllergiesPacketBuilder(),
            'get_recent_labs' => new RecentLabsPacketBuilder(),
            'get_immunization_history' => new ImmunizationsPacketBuilder(),
        ];
    }

    /**
     * @return array{tool_calls: list<array{name: string, arguments: array<string, mixed>}>}
     */
    public function fallbackToolCalls(string $useCase, ?string $routerFamily = null): array
    {
        $key = ($routerFamily !== null && $routerFamily !== '') ? $routerFamily : $useCase;
        $names = match ($key) {
            'medication_check', 'medication' => ['get_patient_identity', 'get_active_medications', 'get_allergy_list'],
            'allergy_check', 'allergy' => ['get_patient_identity', 'get_allergy_list', 'get_active_medications'],
            'recent_abnormal_labs', 'labs' => ['get_patient_identity', 'get_active_problems', 'get_recent_labs'],
            'immunization_history', 'immunization' => ['get_patient_identity', 'get_immunization_history'],
            'identity' => ['get_patient_identity'],
            default => array_keys($this->builders),
        };

        return [
            'tool_calls' => array_map(
                static fn(string $name): array => ['name' => $name, 'arguments' => []],
                $names,
            ),
        ];
    }

    /**
     * @param array<int, mixed> $toolCalls
     * @return array{packets: list<array<string, mixed>>, selected_tools: list<string>, summary: list<array<string, mixed>>, rejected_tools: list<string>}
     */
    public function execute(int $pid, string $patientUuid, array $toolCalls): array
    {
        /** @var list<array<string, mixed>> $packets */
        $packets = [];
        /** @var list<string> $selected */
        $selected = [];
        /** @var list<array<string, mixed>> $summary */
        $summary = [];
        /** @var list<string> $rejected */
        $rejected = [];

        foreach ($toolCalls as $call) {
            if (!is_array($call)) {
                continue;
            }
            $rawName = $call['name'] ?? '';
            $name = is_string($rawName) ? $rawName : '';
            $arguments = $this->normalizeArguments($call['arguments'] ?? []);

            if (!isset($this->builders[$name])) {
                if ($name !== '') {
                    $rejected[] = $name;
                }
                continue;
            }
            if ($this->hasForbiddenArguments($arguments)) {
                $rejected[] = $name . ':forbidden_args';
                continue;
            }
            $safeArguments = $this->clampArguments($name, $arguments);

            $before = count($packets);
            $built = $this->builders[$name]->build($pid, $patientUuid);
            foreach ($built as $packet) {
                /** @var array<string, mixed> $packetArray */
                $packetArray = $packet->toArray();
                $packets[] = $packetArray;
                if (count($packets) >= self::PACKET_CAP) {
                    break;
                }
            }

            $selected[] = $name;
            $summary[] = [
                'tool' => $name,
                'packet_count' => count($packets) - $before,
                'status' => 'ok',
                'arguments' => $safeArguments,
            ];

            if (count($packets) >= self::PACKET_CAP) {
                break;
            }
        }

        return [
            'packets' => $packets,
            'selected_tools' => array_values(array_unique($selected)),
            'summary' => $summary,
            'rejected_tools' => $rejected,
        ];
    }

    /**
     * @param array<string, mixed> $arguments
     */
    private function hasForbiddenArguments(array $arguments): bool
    {
        foreach (array_keys($arguments) as $key) {
            if (in_array($key, self::FORBIDDEN_ARGUMENTS, true)) {
                return true;
            }
        }
        return false;
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeArguments(mixed $arguments): array
    {
        if (!is_array($arguments)) {
            return [];
        }

        $normalized = [];
        foreach ($arguments as $key => $value) {
            if (is_string($key)) {
                $normalized[$key] = $value;
            }
        }
        return $normalized;
    }

    /**
     * @param array<string, mixed> $arguments
     * @return array<string, int>
     */
    private function clampArguments(string $toolName, array $arguments): array
    {
        if ($toolName !== 'get_recent_labs') {
            return [];
        }

        $months = $this->intArgument($arguments['months'] ?? null, 6);
        $limit = $this->intArgument($arguments['limit'] ?? null, 20);

        return [
            'months' => max(1, min(24, $months)),
            'limit' => max(1, min(20, $limit)),
        ];
    }

    private function intArgument(mixed $value, int $default): int
    {
        if (is_int($value)) {
            return $value;
        }
        if (is_float($value) || is_numeric($value)) {
            return (int)$value;
        }
        return $default;
    }
}
