<?php

/**
 * Medication Reconciliation endpoint (Plan §6.3, AgDR-0077).
 *
 * GET-only, session-authenticated, ACL-gated. Reconciles the most recent
 * Co-Pilot extracted medication-list facts for the currently-scoped patient
 * (`session.pid`) against the patient's active OpenEMR `prescriptions` rows,
 * and returns a side-by-side diff classified as confirmed / newly_listed /
 * possibly_discontinued.
 *
 * Auth: same posture as the lab_trends endpoint (AgDR-0083 precedent):
 *   - session cookie present (Active session via SessionWrapperFactory)
 *   - ACL `patients/med`
 *   - patient scope bound to the session pid (no patient_id in the query)
 * No CSRF — read-only GET; session + ACL + scope-bind is stricter than
 * adding CSRF for a same-origin read.
 *
 * Response:
 *   200 application/json
 *     {
 *       "patient_uuid": "<full-uuid>",
 *       "rows": [
 *         {
 *           "drug_name": "Lisinopril",
 *           "extracted_dose": "20 mg",
 *           "extracted_route": "PO",
 *           "extracted_frequency": "Daily",
 *           "prescription_dose": "20 mg",
 *           "prescription_route": "PO",
 *           "prescription_active": 1,
 *           "status": "confirmed"
 *         },
 *         ...
 *       ],
 *       "summary": {
 *         "confirmed": 5, "newly_listed": 2, "possibly_discontinued": 1, "total": 8
 *       },
 *       "extracted_count": 7,
 *       "prescription_count": 6
 *     }
 *   400 missing_patient
 *   403 acl_denied
 *   500 unexpected
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Api\Internal;

require_once(__DIR__ . "/../../../../../globals.php");

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Modules\ClinicalCopilot\Service\MedicationReconciliation;
use OpenEMR\Services\BaseService;

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');

/**
 * @param array<string, mixed> $payload
 */
function copilot_medication_reconciliation_send_json(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

$logger = ServiceContainer::getLogger();

try {
    $session = SessionWrapperFactory::getInstance()->getActiveSession();

    if (!AclMain::aclCheckCore('patients', 'med')) {
        copilot_medication_reconciliation_send_json(403, ['error' => 'acl_denied']);
    }

    $pidRaw = $session->get('pid') ?? 0;
    $pid = is_numeric($pidRaw) ? (int) $pidRaw : 0;
    if ($pid <= 0) {
        copilot_medication_reconciliation_send_json(400, ['error' => 'missing_patient']);
    }

    $patientUuidBin = BaseService::getUuidById((string) $pid, 'patient_data', 'pid');
    if (!is_string($patientUuidBin) || strlen($patientUuidBin) !== 16) {
        copilot_medication_reconciliation_send_json(500, ['error' => 'patient_uuid_lookup_failed']);
    }
    $patientUuidString = UuidRegistry::uuidToString($patientUuidBin);

    $service = new MedicationReconciliation($logger);
    $result = $service->reconcileForPatient($pid);

    copilot_medication_reconciliation_send_json(200, [
        'patient_uuid'       => $patientUuidString,
        'rows'               => $result['rows'],
        'summary'            => $result['summary'],
        'extracted_count'    => $result['extracted_count'],
        'prescription_count' => $result['prescription_count'],
    ]);
} catch (\RuntimeException | \PDOException | \JsonException $exc) {
    $logger->error('ClinicalCopilot medication_reconciliation: unexpected error', [
        'exception' => $exc,
    ]);
    copilot_medication_reconciliation_send_json(500, ['error' => 'unexpected']);
}
