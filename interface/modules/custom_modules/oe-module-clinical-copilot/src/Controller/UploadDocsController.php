<?php

/**
 * Clinical Co-Pilot — Upload Documents Card
 *
 * Renders a standalone "Upload documents" card at the very top of the
 * patient chart, above the Clinical Co-Pilot card. The card carries the
 * same upload form fields the Co-Pilot card uses; both forms share the
 * `copilot.js` handler (wired via `form.copilot-upload-form`) and the
 * same four backend endpoints (upload_lab.php / upload_intake.php /
 * upload_medication_list.php / create_patient_from_intake.php).
 *
 * Per Plan_wk2_Claude_Next06 — this card was split out from PanelController
 * after the user judged that bundling "upload a document" with the AI brief
 * harmed discoverability. The form inside the Co-Pilot card is intentionally
 * preserved (user direction: "keep it in there").
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Controller;

use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Modules\ClinicalCopilot\Bootstrap;

class UploadDocsController
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
        $apiUploadMedicationListUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/upload_medication_list.php';
        $apiMedicationReconciliationUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/medication_reconciliation.php';
        $apiCreatePatientUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/create_patient_from_intake.php';

        $demoModeEnabled = getenv('COPILOT_DEMO_MODE') === '1';

        ob_start();
        ?>
        <link rel="stylesheet" href="<?php echo attr($assetBase); ?>/css/copilot.css">
        <div class="card mb-3 copilot-card copilot-upload-docs-card" id="copilot-upload-docs-card" data-pid="<?php echo attr((string)$pid); ?>">
            <div class="card-header copilot-header">
                <i class="fa fa-file-upload mr-2"></i>
                <strong><?php echo xlt('Upload documents'); ?></strong>
                <span class="copilot-badge ml-2"><?php echo xlt('lab PDF · intake form · medication list'); ?></span>
            </div>
            <div class="card-body">
                <form class="copilot-upload-form mb-0" id="copilot-upload-form-top" enctype="multipart/form-data">
                    <div class="form-row align-items-center">
                        <div class="col-auto">
                            <select class="form-control form-control-sm" id="copilot-upload-doc-type-top" name="doc_type" aria-label="<?php echo attr(xl('Document type')); ?>">
                                <option value="lab_pdf"><?php echo xlt('Upload Labs'); ?></option>
                                <option value="intake_form"><?php echo xlt('Intake form'); ?></option>
                                <option value="medication_list"><?php echo xlt('Upload Medications'); ?></option>
                                <?php if ($demoModeEnabled) : ?>
                                <option value="intake_form_create_patient"><?php echo xlt('Intake form — CREATE NEW DEMO PATIENT'); ?></option>
                                <?php endif; ?>
                            </select>
                        </div>
                        <div class="col">
                            <input
                                type="file"
                                class="form-control-file form-control-sm"
                                id="copilot-upload-file-top"
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
                    <div class="copilot-upload-status text-muted small mt-1" id="copilot-upload-status-top"></div>
                </form>
            </div>
        </div>
        <script>
            // Seed OE_COPILOT_CONFIG with the upload URLs and csrfToken so this card
            // is functional even on the (improbable) code path where the Co-Pilot
            // card below fails to render. The Co-Pilot card overlays a richer
            // config (briefUrl, feedbackUrl, pdfWorkerSrc, etc.) when it loads —
            // the merge below preserves any keys already present, so the order of
            // rendering is non-load-bearing.
            window.OE_COPILOT_CONFIG = Object.assign({
                briefUrl: <?php echo js_escape($apiBriefUrl); ?>,
                feedbackUrl: <?php echo js_escape($apiFeedbackUrl); ?>,
                uploadLabUrl: <?php echo js_escape($apiUploadLabUrl); ?>,
                uploadIntakeUrl: <?php echo js_escape($apiUploadIntakeUrl); ?>,
                uploadMedicationListUrl: <?php echo js_escape($apiUploadMedicationListUrl); ?>,
                medicationReconciliationUrl: <?php echo js_escape($apiMedicationReconciliationUrl); ?>,
                createPatientUrl: <?php echo js_escape($apiCreatePatientUrl); ?>,
                demoMode: <?php echo $demoModeEnabled ? 'true' : 'false'; ?>,
                csrfToken: <?php echo js_escape($csrfToken); ?>,
                pid: <?php echo $pid; ?>
            }, window.OE_COPILOT_CONFIG || {});
        </script>
        <?php
        return (string)ob_get_clean();
    }
}
