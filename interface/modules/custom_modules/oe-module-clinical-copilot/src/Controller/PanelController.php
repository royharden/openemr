<?php

/**
 * Clinical Co-Pilot Panel Controller
 *
 * Renders the in-chart Co-Pilot card. The card contains a placeholder; the
 * client-side JS calls the gateway endpoint and progressively fills it.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Controller;

use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Modules\ClinicalCopilot\Bootstrap;

class PanelController
{
    public function renderPanel(int $pid): string
    {
        $session = SessionWrapperFactory::getInstance()->getActiveSession();
        $csrfToken = CsrfUtils::collectCsrfToken(subject: 'ClinicalCopilot', session: $session);
        $webRoot = OEGlobalsBag::getInstance()->getWebRoot();
        $assetBase = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/assets';
        $apiBriefUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/brief.php';

        ob_start();
        ?>
        <link rel="stylesheet" href="<?php echo attr($assetBase); ?>/css/copilot.css">
        <div class="card mb-3 copilot-card" id="copilot-card" data-pid="<?php echo attr($pid); ?>">
            <div class="card-header copilot-header">
                <i class="fa fa-robot mr-2"></i>
                <strong><?php echo xlt('Clinical Co-Pilot'); ?></strong>
                <span class="copilot-badge ml-2">read-only &middot; source-cited</span>
                <span class="copilot-trace-id float-right" id="copilot-trace-id"></span>
            </div>
            <div class="card-body" id="copilot-body">
                <div class="copilot-status" id="copilot-status">
                    <i class="fa fa-spinner fa-spin"></i>
                    <?php echo xlt('Co-Pilot loading…'); ?>
                </div>
                <div class="copilot-claims" id="copilot-claims" style="display:none"></div>
                <div class="copilot-missing" id="copilot-missing" style="display:none"></div>
                <div class="copilot-followups mt-2" id="copilot-followups" style="display:none">
                    <button type="button" class="btn btn-sm btn-outline-primary copilot-followup-btn" data-followup="what-changed">
                        <?php echo xlt('What changed?'); ?>
                    </button>
                </div>
                <div class="copilot-error" id="copilot-error" style="display:none"></div>
            </div>
            <div class="card-footer text-muted small copilot-footer">
                <?php echo xlt('AI assistant. Verifier-gated. Always confirm in chart.'); ?>
            </div>
        </div>
        <script>
            window.OE_COPILOT_CONFIG = {
                briefUrl: <?php echo js_escape($apiBriefUrl); ?>,
                csrfToken: <?php echo js_escape($csrfToken); ?>,
                pid: <?php echo (int)$pid; ?>
            };
        </script>
        <script src="<?php echo attr($assetBase); ?>/js/copilot.js"></script>
        <?php
        return (string)ob_get_clean();
    }
}
