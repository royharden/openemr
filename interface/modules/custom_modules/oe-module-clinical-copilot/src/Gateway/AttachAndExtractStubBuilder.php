<?php

/**
 * Stub PacketBuilder for the attach_and_extract tool (Wk2 Workstream A).
 *
 * The actual extraction is performed by DocumentUploadController calling the
 * sidecar /v1/extract/* endpoints. This stub allows the ClinicalToolExecutor
 * allowlist to accept the tool name without returning duplicate packets —
 * facts are persisted by DocumentFactsRepository before the graph turn starts.
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Gateway;

use OpenEMR\Modules\ClinicalCopilot\SourcePackets\PacketBuilder;
use OpenEMR\Modules\ClinicalCopilot\SourcePackets\PacketDto;

final class AttachAndExtractStubBuilder implements PacketBuilder
{
    /**
     * @return list<PacketDto>
     */
    public function build(int $pid, string $patientUuid): array
    {
        // Intentionally empty: document facts are pre-persisted by
        // DocumentUploadController → DocumentFactsRepository before the
        // sidecar graph turn. The executor allowlist entry is needed so the
        // sidecar planner may emit attach_and_extract without the executor
        // rejecting it as an unknown tool.
        return [];
    }
}
