<?php

/**
 * Writes one audit_master row per agent turn so security teams can pivot
 * from a Langfuse trace_id to an OpenEMR audit row in one query.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Audit;

use OpenEMR\Common\Logging\EventAuditLogger;

final class AgentTurnAuditor
{
    public static function record(
        int $userId,
        int $pid,
        string $traceId,
        string $useCase,
        string $verifierStatus,
        int $sourceCount,
        ?string $denialReason = null,
    ): void {
        $comment = sprintf(
            'agent_turn trace_id=%s use_case=%s verifier=%s sources=%d%s',
            $traceId,
            $useCase,
            $verifierStatus,
            $sourceCount,
            $denialReason ? (' denial=' . $denialReason) : ''
        );
        try {
            EventAuditLogger::instance()->newEvent(
                'agent_turn',
                (string)$userId,
                'Default',
                empty($denialReason) ? 1 : 0,
                $comment,
                $pid,
                'clinical-copilot',
                'agent',
            );
        } catch (\Throwable $e) {
            error_log('ClinicalCopilot AgentTurnAuditor failed: ' . $e->getMessage());
        }
    }
}
