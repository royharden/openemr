<?php

/**
 * Clinical Co-Pilot — Pre-patient Intake Upload Page
 *
 * Renders the demo-only "Upload an intake form to create a new patient"
 * page. The page is reached through:
 *   * the Patient menu entry "Clinical Intake Upload" (Bootstrap
 *     MenuEvent::MENU_UPDATE listener, AgDR-0090);
 *   * the Patient Finder PageHeading button (Bootstrap
 *     PageHeadingRenderEvent listener, AgDR-0091).
 *
 * Both surfaces, plus the public route at
 * `public/intake_upload.php`, are gated by `COPILOT_DEMO_MODE=1`. With
 * the env unset the menu entry is omitted, the Finder button is omitted,
 * and the route returns 404 (AgDR-0066 "invisible to attackers"
 * rationale, mirrored across all three surfaces).
 *
 * The form posts to `create_patient_from_intake.php` (AgDR-0066), which
 * extracts demographics from the intake PDF, calls
 * `PatientService::insert()`, stores the raw document under the new pid
 * (AgDR-0063 SHA dedup), and returns a `redirect_url` to the new
 * patient's demographics page. Re-upload of the same SHA returns
 * `duplicate_intake: true` and the existing pid (AgDR-0068).
 *
 * Plan reference: Plan_wk2_Claude_Next07_v2 §B.1.
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

class IntakeUploadController
{
    public function render(): string
    {
        $session = SessionWrapperFactory::getInstance()->getActiveSession();
        $csrfToken = CsrfUtils::collectCsrfToken(subject: 'ClinicalCopilot', session: $session);
        $webRoot = OEGlobalsBag::getInstance()->getWebRoot();
        $assetBase = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/assets';
        $apiCreatePatientUrl = $webRoot . Bootstrap::MODULE_INSTALLATION_PATH . '/public/api/create_patient_from_intake.php';

        ob_start();
        ?>
        <link rel="stylesheet" href="<?php echo attr($assetBase); ?>/css/copilot.css">
        <div class="container mt-3 copilot-intake-upload-page" id="copilot-intake-upload-page">
            <div class="card copilot-card copilot-intake-upload-card" id="copilot-intake-upload-card">
                <div class="card-header copilot-header">
                    <i class="fa fa-user-plus mr-2"></i>
                    <strong><?php echo xlt('Upload an intake form to create a new patient'); ?></strong>
                    <span class="copilot-badge ml-2"><?php echo xlt('demo only'); ?></span>
                </div>
                <div class="card-body">
                    <p class="text-muted">
                        <?php echo xlt('Pick an intake PDF. The Clinical Co-Pilot extracts the demographics, creates the chart, and stores the document under the new patient — no manual form fill required.'); ?>
                    </p>
                    <form class="copilot-upload-form" id="copilot-upload-form-intake" enctype="multipart/form-data">
                        <!--
                            Plan_wk2_Claude_Next07_v2 §B.1 / B.3 — the form
                            reuses copilot.js's multi-form handler from
                            Next06. The handler reads `select[name="doc_type"]`
                            (copilot.js:788), so this surface emits a
                            single-option select hidden via .d-none with the
                            doc_type locked to `intake_form_create_patient`.
                            No hidden input — the select itself carries the
                            value.
                        -->
                        <select class="form-control form-control-sm d-none" id="copilot-upload-doc-type-intake" name="doc_type" aria-label="<?php echo attr(xl('Document type')); ?>">
                            <option value="intake_form_create_patient" selected><?php echo xlt('Intake form — create new demo patient'); ?></option>
                        </select>
                        <div class="form-group">
                            <label for="copilot-upload-file-intake"><?php echo xlt('Intake form (PDF, PNG, or JPG)'); ?></label>
                            <input
                                type="file"
                                class="form-control-file"
                                id="copilot-upload-file-intake"
                                name="document_file"
                                accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                                aria-label="<?php echo attr(xl('Upload intake form')); ?>"
                                required>
                        </div>
                        <div class="form-group">
                            <button type="submit" class="btn btn-primary">
                                <i class="fa fa-upload mr-1"></i><?php echo xlt('Upload and create patient'); ?>
                            </button>
                        </div>
                        <div class="copilot-upload-status text-muted" id="copilot-upload-status-intake"></div>
                    </form>
                </div>
            </div>
        </div>
        <script>
            // OE_COPILOT_CONFIG seed for the pre-patient surface. pid:0
            // signals "no chart context" to copilot.js — the handler
            // routes intake_form_create_patient uploads to
            // cfg.createPatientUrl regardless. csrfToken and demoMode
            // mirror the in-chart card's seed shape.
            window.OE_COPILOT_CONFIG = Object.assign({
                createPatientUrl: <?php echo js_escape($apiCreatePatientUrl); ?>,
                csrfToken: <?php echo js_escape($csrfToken); ?>,
                demoMode: true,
                pid: 0
            }, window.OE_COPILOT_CONFIG || {});
        </script>
        <script src="<?php echo attr($assetBase); ?>/js/copilot.js"></script>
        <?php
        return (string)ob_get_clean();
    }
}
