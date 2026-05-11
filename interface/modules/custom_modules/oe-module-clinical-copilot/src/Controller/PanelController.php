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
        $apiUploadLabUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/upload_lab.php';
        $apiUploadIntakeUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/upload_intake.php';
        $apiCreatePatientUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/create_patient_from_intake.php';

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
                <?php $demoModeEnabled = getenv('COPILOT_DEMO_MODE') === '1'; ?>
                <form class="copilot-upload-form mb-3" id="copilot-upload-form" enctype="multipart/form-data">
                    <div class="form-row align-items-center">
                        <div class="col-auto">
                            <select class="form-control form-control-sm" id="copilot-upload-doc-type" name="doc_type" aria-label="<?php echo attr(xl('Document type')); ?>">
                                <option value="lab_pdf"><?php echo xlt('Lab PDF'); ?></option>
                                <option value="intake_form"><?php echo xlt('Intake form'); ?></option>
                                <?php if ($demoModeEnabled) : ?>
                                <option value="intake_form_create_patient"><?php echo xlt('Intake form — CREATE NEW DEMO PATIENT'); ?></option>
                                <?php endif; ?>
                            </select>
                        </div>
                        <div class="col">
                            <input
                                type="file"
                                class="form-control-file form-control-sm"
                                id="copilot-upload-file"
                                name="document_file"
                                accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                                aria-label="<?php echo attr(xl('Upload clinical document')); ?>">
                        </div>
                        <div class="col-auto">
                            <button type="submit" class="btn btn-sm btn-outline-primary">
                                <i class="fa fa-upload mr-1"></i><?php echo xlt('Upload'); ?>
                            </button>
                        </div>
                    </div>
                    <div class="copilot-upload-status text-muted small mt-1" id="copilot-upload-status"></div>
                </form>
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
                uploadLabUrl: <?php echo js_escape($apiUploadLabUrl); ?>,
                uploadIntakeUrl: <?php echo js_escape($apiUploadIntakeUrl); ?>,
                createPatientUrl: <?php echo js_escape($apiCreatePatientUrl); ?>,
                demoMode: <?php echo $demoModeEnabled ? 'true' : 'false'; ?>,
                csrfToken: <?php echo js_escape($csrfToken); ?>,
                pid: <?php echo $pid; ?>,
                pdfWorkerSrc: <?php echo js_escape($assetBase . '/vendor/pdfjs/pdf.worker.min.js'); ?>
            };
        </script>
        <!-- AgDR-0062: PDF.js required for the source-chip bbox overlay in copilot.js;
             without this include window.pdfjsLib is undefined and the overlay
             silently returns from showBboxOverlay(). Version pinned to match
             the API surface copilot.js targets (getDocument, GlobalWorkerOptions).
             AgDR-0072: pdf.min.js + pdf.worker.min.js@3.11.174 are vendored under
             public/assets/vendor/pdfjs/ — eliminates the cdnjs supply-chain vector
             that the prior CDN-only load posed. Subresource Integrity (SRI) hash
             stays as defense-in-depth — if the vendored file is ever swapped for
             a tampered copy, the browser refuses to execute it. See LICENSE-NOTICE
             alongside the vendored files for Apache-2.0 attribution. -->
        <script src="<?php echo attr($assetBase); ?>/vendor/pdfjs/pdf.min.js"
                integrity="sha384-/1qUCSGwTur9vjf/z9lmu/eCUYbpOTgSjmpbMQZ1/CtX2v/WcAIKqRv+U1DUCG6e"
                crossorigin="anonymous"
                referrerpolicy="no-referrer"></script>
        <script src="<?php echo attr($assetBase); ?>/js/copilot.js"></script>
        <?php
        return (string)ob_get_clean();
    }
}
