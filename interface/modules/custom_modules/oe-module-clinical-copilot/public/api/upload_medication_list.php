<?php

/**
 * Medication-list document upload endpoint (Plan §6.3, AgDR-0077).
 *
 * Thin dispatcher onto {@see copilot_upload_handle()} in upload_common.php.
 * Mirrors upload_lab.php / upload_intake.php — auth + CSRF + SHA-256 dedup +
 * sidecar /v1/extract/medication-list + persist to copilot_document_facts.
 *
 * PHI-redacts the upload filename per AgDR-0084 before storage or sidecar call.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Api\Internal;

require_once(__DIR__ . '/upload_common.php');

copilot_upload_handle('medication_list');
