<?php

/**
 * Clinical Co-Pilot — pre-patient intake upload page (demo only).
 *
 * Public route reached from:
 *   * Patient menu → Clinical Intake Upload  (Bootstrap MenuEvent listener,
 *     AgDR-0090); and
 *   * Patient Finder → "Upload intake to create new patient (demo only)"
 *     button (Bootstrap PageHeadingRenderEvent listener, AgDR-0091).
 *
 * Triple safety gate (same shape as AgDR-0066 create_patient_from_intake.php):
 *   1. `COPILOT_DEMO_MODE=1` env var. Unset → HTTP 404 + generic body
 *      (NOT 403 — we do not want to leak the existence of a privileged demo
 *      page to attackers; AgDR-0066 rationale mirrored here).
 *   2. The page is wrapped in the standard OpenEMR session via globals.php
 *      (authentication enforced by the session bootstrap).
 *   3. ACL `admin/super` — Administrators-only by default.
 *
 * This page does NOT itself perform the upload. The form posts to
 * `create_patient_from_intake.php` (AgDR-0066), which is the actual gated
 * endpoint that calls PatientService::insert + storeDocument + persist
 * facts. The page is just the UI shell.
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

namespace OpenEMR\Modules\ClinicalCopilot\Page;

require_once(__DIR__ . "/../../../../globals.php");

use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Modules\ClinicalCopilot\Controller\IntakeUploadController;

// Gate 1: demo-mode env var. Off → 404 + generic body. See AgDR-0066 §3.5.
if (getenv('COPILOT_DEMO_MODE') !== '1') {
    http_response_code(404);
    header('Content-Type: text/html; charset=utf-8');
    echo '<!doctype html><title>Not found</title><h1>Not found</h1>';
    exit;
}

// Gate 3: ACL admin/super. (Gate 2 is implicit via globals.php session
// bootstrap — unauthenticated requests are redirected before reaching here.)
if (!AclMain::aclCheckCore('admin', 'super')) {
    http_response_code(403);
    header('Content-Type: text/html; charset=utf-8');
    echo '<!doctype html><title>Forbidden</title><h1>Forbidden</h1>';
    exit;
}

?><!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title><?php echo xlt('Clinical Intake Upload'); ?></title>
    <?php
    // Pull in OpenEMR's standard stylesheet bundle so Bootstrap classes
    // and Font Awesome icons render correctly outside the chart shell.
    // Use OEGlobalsBag for the webroot (CLAUDE.md "No direct superglobal
    // access in application code; in legacy code confine superglobal
    // reads to the outermost entry point and parse into typed objects
    // immediately" — and the typed getter is also what PHPStan level 10
    // requires; bare $GLOBALS['webroot'] trips openemr.forbiddenGlobalsAccess).
    $webRoot = OEGlobalsBag::getInstance()->getWebRoot();
    ?>
    <link rel="stylesheet" href="<?php echo attr($webRoot); ?>/public/themes/style_light.css">
    <link rel="stylesheet" href="<?php echo attr($webRoot); ?>/public/assets/font-awesome/css/font-awesome.min.css">
</head>
<body>
<?php
echo (new IntakeUploadController())->render();
?>
</body>
</html>
