<?php

/**
 * Demo-mode endpoint: create a new OpenEMR patient from an uploaded intake form.
 *
 * AgDR-0066 — closes plan item 3 ("demonstrate an upload creates a new patient")
 * of Plan_wk2_Claude_Next04_2026-05-10_demo-and-fhir-closure.md §4.5.
 * AgDR-0068 — closes audit finding #4 of Plan_wk2_Claude_Next05_*: re-uploading
 * the same intake fixture must return the existing pid + `duplicate_intake: true`
 * rather than colliding on patient_data.pubpid UNIQUE.
 *
 * Triple safety gate:
 *   1. COPILOT_DEMO_MODE=1 must be set in the API container's environment.
 *      Production deployments leave it unset, and the endpoint returns HTTP 403.
 *   2. CSRF subject "ClinicalCopilot" (same as upload_lab.php / upload_intake.php).
 *   3. OpenEMR ACL: admin/super. We chose admin/super (Administrators only by
 *      default) rather than introducing a new "patients/demo" ACL, because
 *      registering a new ACL category requires a gacl_setup migration; the env
 *      var is the primary safety control and admin-only is a belt-and-suspenders
 *      backstop. A future sprint can promote this to a dedicated ACL category.
 *
 * Flow:
 *   POST /modules/custom_modules/oe-module-clinical-copilot/public/api/create_patient_from_intake.php
 *      └─> extract intake form via sidecar /v1/extract/intake-form (no DB writes)
 *           └─> parse demographics from result.fields[]
 *                └─> validate minimum: fname, lname, DOB
 *                     └─> PatientService::insert() — creates patient row
 *                          └─> store raw document under the new pid (addNewDocument + SHA dedup)
 *                               └─> DocumentFactsRepository::persistExtractedDocument()
 *                                    └─> response: { pid, patient_uuid, redirect_url, extracted_field_count }
 *
 * Tagging convention (per agent_lessons 2026-05-10T20:20Z):
 *   patient_data.usertext1 = 'wk2-demo-intake-<short-sha>'
 *   patient_data.pubpid    = 'WK2-DEMO-INTAKE-<short-sha-uppercased>'
 * The reset script (scripts/reset_demo_state.sh) finds these via
 *   pubpid LIKE 'WK2-DEMO-%' OR usertext1 LIKE 'wk2-demo-intake-%'.
 *
 * Lab uploads are NEVER auto-created via this endpoint — lab_pdf has no
 * demographic fields to drive patient creation. Only intake forms.
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
require_once(\OpenEMR\Core\OEGlobalsBag::getInstance()->getProjectDir() . "/library/documents.php");
require_once(__DIR__ . "/upload_common.php");

// AgDR-0071 (Phase 2.6 smoke #2): pure-function helpers + AmbiguousDobException
// live in a separate file so the smoke test can require them without firing
// this file's top-level request handler (which calls exit via
// copilot_create_send_json after the demo-mode gate check).
require_once(__DIR__ . "/create_patient_from_intake_helpers.php");

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Modules\ClinicalCopilot\Controller\DocumentUploadController;
use OpenEMR\Modules\ClinicalCopilot\Repository\DocumentFactsRepository;
use OpenEMR\Services\PatientService;
use Symfony\Component\HttpFoundation\File\UploadedFile;
use Symfony\Component\HttpFoundation\Request;

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

// ---------------------------------------------------------------------------
// Endpoint entry
// ---------------------------------------------------------------------------

$logger = ServiceContainer::getLogger();
try {
    // 1. Demo-mode gate — primary safety control. Production has this unset.
    //
    //    Plan §3.5 (audit finding #15): when the env var is off, the endpoint
    //    is INVISIBLE to attackers. Return a generic 404 rather than a 403
    //    that leaks the existence + env-var name of a privileged demo flow.
    //    The gating rationale (env var + CSRF + admin ACL) is preserved in
    //    the file-header docblock and AgDR-0066 — the response body is
    //    generic by design.
    if (getenv('COPILOT_DEMO_MODE') !== '1') {
        copilot_create_send_json(404, ['error' => 'not_found']);
    }

    $request = Request::createFromGlobals();
    $session = SessionWrapperFactory::getInstance()->getActiveSession();

    // 2. CSRF — same subject as the upload endpoints.
    $csrf = $request->request->get('csrf_token_form') ?? $request->server->get('HTTP_APICSRFTOKEN');
    if (!is_string($csrf) || !CsrfUtils::verifyCsrfToken($csrf, $session, 'ClinicalCopilot')) {
        copilot_create_send_json(403, ['error' => 'csrf_failure']);
    }

    // 3. ACL — admin/super (Administrators by default). AgDR-0066 records the
    //    deviation from the plan's "patients/demo" ACL spec.
    if (!AclMain::aclCheckCore('admin', 'super')) {
        copilot_create_send_json(403, ['error' => 'acl_denied']);
    }

    // 4. File upload guard.
    $uploadedFile = $request->files->get('file');
    if (!$uploadedFile instanceof UploadedFile) {
        copilot_create_send_json(400, ['error' => 'missing_file']);
    }
    if (!$uploadedFile->isValid()) {
        copilot_create_send_json(400, ['error' => 'upload_error', 'code' => $uploadedFile->getError()]);
    }

    $tmpName = $uploadedFile->getPathname();
    $originalName = basename($uploadedFile->getClientOriginalName() ?: 'intake.bin');
    if ($tmpName === '' || !is_uploaded_file($tmpName)) {
        copilot_create_send_json(400, ['error' => 'invalid_upload']);
    }

    $scratch = tempnam(sys_get_temp_dir(), 'copilot-create-');
    if (!is_string($scratch) || !copy($tmpName, $scratch)) {
        copilot_create_send_json(500, ['error' => 'upload_copy_failed']);
    }

    try {
        $mimeType = copilot_upload_detect_mime(
            $scratch,
            $uploadedFile->getClientMimeType() ?: 'application/octet-stream',
        );

        // AgDR-0084 / Plan §3.7 — strip PHI from the upload filename
        // BEFORE the sidecar receives it (multipart Content-Disposition
        // header), before addNewDocument stores it (documents.name), and
        // before any log line interpolates it. Same shape as the matching
        // redaction in upload_common.php: deterministic "upload-{sha8}.{ext}".
        // The SHA we compute here is from the scratch file's body; if the
        // sidecar later returns its own `document_sha256` it must match.
        $preExtractSha = hash_file('sha256', $scratch);
        if (!is_string($preExtractSha) || strlen($preExtractSha) !== 64) {
            throw new \RuntimeException('sha256_compute_failed');
        }
        $originalName = copilot_upload_redact_filename($originalName, $preExtractSha);

        // 5. Sidecar extraction — no DB writes yet. extractIntakeFormForCreateEndpoint()
        //    is the @internal, this-endpoint-only extraction sibling of uploadIntakeForm()
        //    (DocumentUploadController). Plan §3.6 renamed it to make accidental misuse
        //    visible at every call site.
        $sidecarBaseUrl = getenv('COPILOT_API_BASE_URL');
        $sidecarSecret = getenv('COPILOT_OPENEMR_GATEWAY_SHARED_SECRET');
        if (!is_string($sidecarBaseUrl) || $sidecarBaseUrl === '' || !is_string($sidecarSecret) || $sidecarSecret === '') {
            throw new \RuntimeException('sidecar_not_configured');
        }

        $controller = new DocumentUploadController(
            $sidecarBaseUrl,
            $sidecarSecret,
            new DocumentFactsRepository($logger),
            $logger,
        );

        $payload = $controller->extractIntakeFormForCreateEndpoint($scratch, $originalName, $mimeType);

        // 6. Parse + validate demographics. Without name + DOB we cannot create
        //    a patient — return 422 so the caller can decide what to do.
        //    Plan §4.1 (audit finding #16): a DOB that parses as both m/d/Y
        //    and d/m/Y with distinct results surfaces as `ambiguous_dob`
        //    with both candidates so the operator can clarify.
        $demographics = copilot_create_demographics_from_extract($payload);
        $fname = $demographics['fname'] ?? null;
        $lname = $demographics['lname'] ?? null;
        try {
            $dob = copilot_create_normalize_dob($demographics['DOB'] ?? null);
        } catch (AmbiguousDobException $ambiguous) {
            copilot_create_send_json(422, [
                'error' => 'ambiguous_dob',
                'detail' => 'Intake DOB parsed as both US (m/d/Y) and European (d/m/Y) with distinct dates. Please clarify.',
                'raw' => $demographics['DOB'] ?? null,
                'candidates' => $ambiguous->candidates,
            ]);
        }

        if ($fname === null || $lname === null || $dob === null) {
            copilot_create_send_json(422, [
                'error' => 'insufficient_demographics',
                'detail' => 'Intake extraction did not yield first name, last name, and DOB.',
                'extracted' => [
                    'fname' => $fname,
                    'lname' => $lname,
                    'DOB' => $demographics['DOB'] ?? null,
                ],
            ]);
        }

        // 7. Build tagging fields tied to the file SHA so re-running the same
        //    file produces a recognizable, traceable pubpid suffix. The
        //    deterministic `usertext1` also doubles as our idempotency key
        //    for the duplicate-upload pre-check in step 8.
        $docShaRaw = $payload['document_sha256'] ?? null;
        if (is_string($docShaRaw) && $docShaRaw !== '') {
            $docSha = $docShaRaw;
        } else {
            // hash_file('sha256', ...) returns non-falsy-string per phpstan
            // stub; only the length is interesting (defensive against a
            // future stub change or unusual fs error).
            $computed = hash_file('sha256', $scratch);
            if (strlen($computed) !== 64) {
                throw new \RuntimeException('sha256_compute_failed');
            }
            $docSha = $computed;
        }
        $shortSha = strtoupper(substr($docSha, 0, 8));
        $pubpid = sprintf('WK2-DEMO-INTAKE-%s', $shortSha);
        $usertext1 = sprintf('wk2-demo-intake-%s', strtolower($shortSha));

        // 8. Duplicate-intake pre-check (AgDR-0068, audit finding #4).
        //    Re-uploading the same intake file must NOT collide on
        //    `patient_data.pubpid UNIQUE` and bubble up a 500. Look up the
        //    existing demo-intake patient by its deterministic-from-SHA
        //    `usertext1` value and reuse its pid/uuid if present. Facts +
        //    raw-document storage below are already SHA-idempotent, so the
        //    rest of the flow degrades cleanly into a "re-extract under
        //    existing pid" no-op for second uploads.
        $duplicateIntake = false;
        $existingPatient = copilot_create_lookup_existing_patient_by_usertext1($usertext1);
        if ($existingPatient !== null) {
            [$newPid, $newPatientUuid] = $existingPatient;
            $duplicateIntake = true;
        } else {
            // 8a. PatientService::insert. We keep the data array minimal and
            //     deterministic; missing optional fields are left null.
            $patientService = new PatientService();
            $insertResult = $patientService->insert([
                'fname' => $fname,
                'lname' => $lname,
                'DOB' => $dob,
                'sex' => copilot_create_normalize_sex($demographics['sex'] ?? null),
                'pubpid' => $pubpid,
                'usertext1' => $usertext1,
                'street' => $demographics['street'] ?? null,
                'city' => $demographics['city'] ?? null,
                'state' => $demographics['state'] ?? null,
                'postal_code' => $demographics['postal_code'] ?? null,
                'phone_home' => $demographics['phone_home'] ?? null,
                'email' => $demographics['email'] ?? null,
            ]);

            if (!$insertResult->isValid()) {
                copilot_create_send_json(422, [
                    'error' => 'patient_validation_failed',
                    'validation' => $insertResult->getValidationMessages(),
                ]);
            }
            $rows = $insertResult->getData();
            $newPid = null;
            $newPatientUuid = null;
            if (is_array($rows) && isset($rows[0]) && is_array($rows[0])) {
                $pidRow = $rows[0]['pid'] ?? null;
                if (is_numeric($pidRow)) {
                    $newPid = (int) $pidRow;
                }
                $rawUuid = $rows[0]['uuid'] ?? null;
                if (is_string($rawUuid) && strlen($rawUuid) === 16) {
                    $newPatientUuid = UuidRegistry::uuidToString($rawUuid);
                } elseif (is_string($rawUuid) && $rawUuid !== '') {
                    $newPatientUuid = $rawUuid;
                }
            }

            if ($newPid === null || $newPatientUuid === null) {
                throw new \RuntimeException('patient_insert_did_not_return_pid_uuid');
            }
        }

        // 9. Store raw document under the new patient. We reuse the SHA dedup
        //    layer from AgDR-0063 — same file uploaded twice across two
        //    create-from-intake calls would still dedup (different patients).
        $userIdRaw = $session->get('authUserID') ?? 0;
        $userId = is_numeric($userIdRaw) ? (int) $userIdRaw : 0;
        [$documentId, $documentUuidBin] = copilot_upload_store_document(
            $tmpName,
            $originalName,
            $mimeType,
            $newPid,
            $userId,
        );
        copilot_upload_record_sha($newPid, $docSha, $documentId);

        // 10. Persist extracted facts now that the patient exists.
        $repository = new DocumentFactsRepository($logger);
        $inserted = $repository->persistExtractedDocument(
            $payload,
            $newPatientUuid,
            $documentUuidBin,
            (string) $userId,
        );

        // 11. Response shape — small and explicit so the UI can navigate.
        $webRoot = \OpenEMR\Core\OEGlobalsBag::getInstance()->getWebRoot();
        $extractedCount = $payload['extracted_field_count'] ?? null;
        // Plan_wk2_Claude_Next08 §W1 — pass the sidecar trace_id through so
        // the UI can render a clickable Langfuse chip on the create-patient
        // success status. Defensive: defaults to empty string if the
        // sidecar response is malformed (the UI guards against empty).
        $traceId = is_string($payload['trace_id'] ?? null) ? $payload['trace_id'] : '';
        copilot_create_send_json(200, [
            'pid' => $newPid,
            'patient_uuid' => $newPatientUuid,
            'pubpid' => $pubpid,
            'usertext1' => $usertext1,
            'duplicate_intake' => $duplicateIntake,
            'document_id' => $documentId,
            'document_sha256' => $docSha,
            'extracted_field_count' => is_int($extractedCount) ? $extractedCount : 0,
            'persisted_facts' => $inserted,
            'trace_id' => $traceId,
            'demographics' => [
                'fname' => $fname,
                'lname' => $lname,
                'DOB' => $dob,
            ],
            'redirect_url' => $webRoot . '/interface/patient_file/summary/demographics.php?set_pid=' . $newPid,
        ]);
    } catch (\RuntimeException | \PDOException | \JsonException $e) {
        $logger->error('ClinicalCopilot: create_patient_from_intake failed', [
            'exception' => $e,
        ]);
        copilot_create_send_json(500, [
            'error' => 'create_patient_from_intake_failed',
            'detail' => 'Demo-mode patient creation failed. Check sidecar status + Langfuse trace.',
        ]);
    } finally {
        if (is_file($scratch)) {
            unlink($scratch);
        }
    }
} catch (\RuntimeException | \PDOException | \JsonException $e) {
    $logger->error('ClinicalCopilot: create_patient_from_intake outer-fail', [
        'exception' => $e,
    ]);
    copilot_create_send_json(500, ['error' => 'unexpected']);
}
