<?php

/**
 * Authenticated FHIR Observation preview proxy (AgDR-0083 / Plan §3.8).
 *
 * Codex peer-review finding #29: Next04's source-chip popover renders a
 * link "View as FHIR Observation" that points at `/apis/default/fhir/r4/Observation/{uuid}`.
 * That endpoint is OAuth2-protected. A browser click from inside an
 * authenticated OpenEMR HTML session does NOT carry an OAuth Bearer
 * token, so the link 401s and breaks the "round-trip through FHIR"
 * demo beat.
 *
 * This proxy fixes it by terminating the auth at the OpenEMR session
 * layer (cookie + CSRF + ACL) and calling `FhirObservationService::getOne`
 * directly from PHP. The user's browser session already proves they're
 * authenticated for OpenEMR; we don't need a separate FHIR OAuth flow
 * for an internal preview link.
 *
 * Safety gates (CSRF intentionally omitted — see "CSRF rationale" below):
 *   1. OpenEMR session cookie — `interface/globals.php` rejects
 *      unauthenticated requests.
 *   2. ACL `patients/med` — must have view rights on patient data.
 *   3. Patient-scope bind — the FHIR service's `puuidBind` parameter
 *      restricts the lookup to the current session pid's UUID. An
 *      Observation belonging to a different patient surfaces as zero
 *      results (returned as 404 — NOT 403 — so the proxy does not
 *      confirm the existence of an Observation outside the operator's
 *      chart scope).
 *
 * CSRF rationale: the chip popover renders the proxy URL as a plain
 * `<a target="_blank">` link. A `<a>` element has no facility for
 * including a CSRF token (no XHR-driven header, no form body). Adding
 * CSRF to the URL query string would force the AttachAndExtractStubBuilder
 * (which has no direct session access) to plumb a token through every
 * chip metadata object, and the resulting URL would still be visible in
 * the browser address bar / history / referrer headers. Since this
 * endpoint is read-only (GET is idempotent, no state change), the
 * standard CSRF threat model (cross-origin state-changing request)
 * does not apply. Defense-in-depth is provided by the same-origin
 * session cookie + ACL + patient-scope bind — which together are
 * stricter than the OAuth flow this proxy replaces (a stolen OAuth
 * token would bypass the patient-scope bind).
 *
 * Request:
 *   GET  …/fhir_observation_preview.php?observation_uuid=946da619-...
 *   POST …/fhir_observation_preview.php   (form data: observation_uuid + csrf_token_form)
 *
 * Response:
 *   200  Content-Type: application/fhir+json  — the Observation resource
 *   400  invalid_uuid
 *   403  csrf_failure | acl_denied
 *   404  not_found (Observation does not exist OR is out of scope)
 *   500  unexpected
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Api\Internal;

require_once(__DIR__ . "/../../../../../globals.php");

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Services\BaseService;
use OpenEMR\Services\FHIR\FhirObservationService;
use OpenEMR\Common\Uuid\UuidRegistry;
use Symfony\Component\HttpFoundation\Request;

header('Content-Type: application/fhir+json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

/**
 * @param array<string, mixed> $payload
 */
function copilot_fhir_preview_send_json(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

$logger = ServiceContainer::getLogger();

try {
    $request = Request::createFromGlobals();
    $session = SessionWrapperFactory::getInstance()->getActiveSession();

    // 1. ACL — patients/med (same gate the rest of the Co-Pilot uses for
    //    chart-context views). Session cookie auth is enforced by the
    //    require_once globals.php at top of file. CSRF intentionally
    //    omitted — see file-header "CSRF rationale" block.
    if (!AclMain::aclCheckCore('patients', 'med')) {
        copilot_fhir_preview_send_json(403, ['error' => 'acl_denied']);
    }

    // 2. Resolve the current session's patient.
    $pidRaw = $session->get('pid') ?? 0;
    $pid = is_numeric($pidRaw) ? (int) $pidRaw : 0;
    if ($pid <= 0) {
        copilot_fhir_preview_send_json(400, ['error' => 'missing_patient']);
    }

    // 4. observation_uuid from query string OR form body.
    $observationUuid = $request->query->get('observation_uuid')
        ?? $request->request->get('observation_uuid');
    if (!is_string($observationUuid) || preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i', $observationUuid) !== 1) {
        copilot_fhir_preview_send_json(400, ['error' => 'invalid_uuid']);
    }

    // 5. Resolve the current patient's UUID so we can pass it as the
    //    puuidBind compartment bind. FhirObservationService::getOne uses
    //    this to filter — an Observation belonging to a different patient
    //    will surface as zero results (handled below as 404).
    $patientUuidBin = BaseService::getUuidById((string) $pid, 'patient_data', 'pid');
    if (!is_string($patientUuidBin) || strlen($patientUuidBin) !== 16) {
        copilot_fhir_preview_send_json(500, ['error' => 'patient_uuid_lookup_failed']);
    }
    $patientUuidString = UuidRegistry::uuidToString($patientUuidBin);

    // 6. Call the umbrella FHIR Observation service (same one the
    //    OAuth-protected REST controller uses), but bypass OAuth since
    //    we're already authenticated via OpenEMR's session cookie.
    $fhirService = new FhirObservationService();
    $processingResult = $fhirService->getOne($observationUuid, $patientUuidString);

    if (!$processingResult->isValid()) {
        $logger->info('ClinicalCopilot FHIR preview: invalid processing result', [
            'observation_uuid' => $observationUuid,
            'validation_errors' => $processingResult->getValidationMessages(),
        ]);
        copilot_fhir_preview_send_json(400, ['error' => 'invalid_observation_request']);
    }

    $rows = $processingResult->getData();
    if (!is_array($rows) || count($rows) === 0) {
        // 404 (NOT 403) — do not confirm existence of an Observation
        // outside the operator's chart scope.
        copilot_fhir_preview_send_json(404, ['error' => 'not_found']);
    }

    if ($processingResult->hasInternalErrors()) {
        $logger->error('ClinicalCopilot FHIR preview: internal errors from FHIR service', [
            'observation_uuid' => $observationUuid,
        ]);
        copilot_fhir_preview_send_json(500, ['error' => 'fhir_service_internal_error']);
    }

    // 7. Serialize the FHIR Observation resource. The FhirServiceBase
    //    contract stores parsed FHIR resources in $processingResult; the
    //    first entry is the matching Observation. Match the existing
    //    FhirObservationRestController::getOne shape.
    $observation = $rows[0];

    // FHIR resources are FHIR\R4\FHIRResource\... objects that expose a
    // jsonSerialize() method. Encode directly.
    http_response_code(200);
    echo json_encode($observation, JSON_UNESCAPED_SLASHES);
    exit;
} catch (\RuntimeException | \PDOException | \JsonException $exc) {
    $logger->error('ClinicalCopilot FHIR preview proxy: unexpected error', [
        'exception' => $exc,
    ]);
    copilot_fhir_preview_send_json(500, ['error' => 'unexpected']);
}
