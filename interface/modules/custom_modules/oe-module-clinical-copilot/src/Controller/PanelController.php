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
        $apiFeedbackUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/feedback.php';

        ob_start();
        ?>
        <link rel="stylesheet" href="<?php echo attr($assetBase); ?>/css/copilot.css">
        <div class="card mb-3 copilot-card" id="copilot-card" data-pid="<?php echo attr((string)$pid); ?>">
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
                    <button type="button" class="btn btn-sm btn-outline-primary copilot-followup-btn" data-followup="medication_check">
                        <?php echo xlt('Medication check'); ?>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-primary copilot-followup-btn" data-followup="allergy_check">
                        <?php echo xlt('Allergy check'); ?>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-primary copilot-followup-btn" data-followup="recent_abnormal_labs">
                        <?php echo xlt('Recent abnormal labs'); ?>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-primary copilot-followup-btn" data-followup="immunization_history">
                        <?php echo xlt('Immunizations'); ?>
                    </button>
                </div>
                <div class="copilot-ask mt-2" id="copilot-ask" style="display:none">
                    <form class="form-inline copilot-ask-form" id="copilot-ask-form" autocomplete="off">
                        <textarea
                            class="form-control form-control-sm copilot-ask-input"
                            id="copilot-ask-input"
                            rows="1"
                            maxlength="500"
                            placeholder="<?php echo attr(xl("Ask about this patient's chart...")); ?>"
                            aria-label="<?php echo attr(xl('Ask a question about the current patient')); ?>"></textarea>
                        <button type="submit" class="btn btn-sm btn-primary ml-2 copilot-ask-btn" id="copilot-ask-btn">
                            <?php echo xlt('Ask'); ?>
                        </button>
                    </form>
                    <div class="copilot-ask-help text-muted small mt-1">
                        <?php echo xlt('Current patient only. Source-cited answers. Press Enter to submit, Shift+Enter for newline.'); ?>
                    </div>
                </div>
                <div class="copilot-feedback mt-2" id="copilot-feedback" style="display:none">
                    <span class="text-muted small mr-2"><?php echo xlt('How was this brief?'); ?></span>
                    <button type="button" class="btn btn-sm btn-outline-success copilot-feedback-btn" data-verdict="helpful">
                        <?php echo xlt('Helpful'); ?>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-warning copilot-feedback-btn" data-verdict="missing_data">
                        <?php echo xlt('Missing data'); ?>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-danger copilot-feedback-btn" data-verdict="incorrect">
                        <?php echo xlt('Incorrect'); ?>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-secondary copilot-feedback-btn" data-verdict="too_slow">
                        <?php echo xlt('Too slow'); ?>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-secondary copilot-feedback-btn" data-verdict="source_unclear">
                        <?php echo xlt('Source unclear'); ?>
                    </button>
                    <span class="copilot-feedback-status text-muted small ml-2" id="copilot-feedback-status"></span>
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
                feedbackUrl: <?php echo js_escape($apiFeedbackUrl); ?>,
                csrfToken: <?php echo js_escape($csrfToken); ?>,
                pid: <?php echo $pid; ?>
            };
        </script>
        <script src="<?php echo attr($assetBase); ?>/js/copilot.js"></script>
        <?php
        return (string)ob_get_clean();
    }
}
