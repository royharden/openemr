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
        ?string $extra = null,
    ): void {
        // `$extra` carries either a denial reason (acl_denied) or a router_family
        // tag for free-text turns. Question text is intentionally never included.
        $comment = sprintf(
            'agent_turn trace_id=%s use_case=%s verifier=%s sources=%d%s',
            $traceId,
            $useCase,
            $verifierStatus,
            $sourceCount,
            $extra ? (' tag=' . $extra) : ''
        );
        $isDenial = $extra === 'acl_denied' || $verifierStatus === 'denied';
        try {
            EventAuditLogger::getInstance()->newEvent(
                'agent_turn',
                (string)$userId,
                'Default',
                $isDenial ? 0 : 1,
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
