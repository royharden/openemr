<?php

/**
 * Source packet builder interface.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\SourcePackets;

interface PacketBuilder
{
    /**
     * @param int $pid OpenEMR internal patient id (server-side only)
     * @param string $patientUuid Resolved patient UUID for this request
     * @return PacketDto[]
     */
    public function build(int $pid, string $patientUuid): array;
}
