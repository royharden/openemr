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

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Modules\ClinicalCopilot\Controller\DocumentUploadController;
use OpenEMR\Modules\ClinicalCopilot\Repository\DocumentFactsRepository;
use OpenEMR\Services\PatientService;
use Symfony\Component\HttpFoundation\File\UploadedFile;
use Symfony\Component\HttpFoundation\Request;

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

/**
 * @param array<string, mixed> $payload
 */
function copilot_create_send_json(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

/**
 * Pluck the first matching demographic value from a sidecar fields list.
 *
 * Intake extractors emit field_path under various conventions: bare names
 * ("first_name"), "intake."-prefixed, "demographics."-prefixed, or
 * "intake.demographics."-prefixed. We try all of them in order.
 *
 * @param list<array<string, mixed>> $fields
 * @param list<string> $candidatePaths
 */
function copilot_create_pluck_field(array $fields, array $candidatePaths): ?string
{
    foreach ($candidatePaths as $candidate) {
        foreach ($fields as $field) {
            $name = $field['name'] ?? null;
            if (!is_string($name) || strtolower($name) !== strtolower($candidate)) {
                continue;
            }
            $value = $field['value'] ?? null;
            if (is_string($value) && $value !== '') {
                return trim($value);
            }
            if (is_int($value) || is_float($value)) {
                return (string) $value;
            }
        }
    }
    return null;
}

/**
 * Extract a {fname, lname, DOB, sex, address...} array from a sidecar
 * intake-form ExtractedDocument payload.
 *
 * Returns the partial demographics — caller validates completeness.
 *
 * @param array<string, mixed> $payload
 * @return array<string, string|null>
 */
function copilot_create_demographics_from_extract(array $payload): array
{
    $result = $payload['result'] ?? [];
    $rawFields = is_array($result) ? ($result['fields'] ?? []) : [];
    /** @var list<array<string, mixed>> $fields */
    $fields = [];
    if (is_array($rawFields)) {
        foreach ($rawFields as $f) {
            if (!is_array($f)) {
                continue;
            }
            $entry = [];
            foreach ($f as $k => $v) {
                if (is_string($k)) {
                    $entry[$k] = $v;
                }
            }
            $fields[] = $entry;
        }
    }

    return [
        'fname' => copilot_create_pluck_field($fields, [
            'first_name', 'fname',
            'demographics.first_name', 'demographics.fname',
            'intake.first_name', 'intake.fname',
            'intake.demographics.first_name', 'intake.demographics.fname',
        ]),
        'lname' => copilot_create_pluck_field($fields, [
            'last_name', 'lname',
            'demographics.last_name', 'demographics.lname',
            'intake.last_name', 'intake.lname',
            'intake.demographics.last_name', 'intake.demographics.lname',
        ]),
        'DOB' => copilot_create_pluck_field($fields, [
            'date_of_birth', 'dob', 'DOB', 'birthdate',
            'demographics.date_of_birth', 'demographics.dob',
            'intake.date_of_birth', 'intake.dob',
            'intake.demographics.date_of_birth', 'intake.demographics.dob',
        ]),
        'sex' => copilot_create_pluck_field($fields, [
            'sex', 'gender',
            'demographics.sex', 'demographics.gender',
            'intake.sex', 'intake.gender',
            'intake.demographics.sex', 'intake.demographics.gender',
        ]),
        'phone_home' => copilot_create_pluck_field($fields, [
            'phone', 'phone_home', 'home_phone',
            'demographics.phone', 'demographics.phone_home',
            'intake.phone', 'intake.demographics.phone',
        ]),
        'email' => copilot_create_pluck_field($fields, [
            'email', 'demographics.email',
            'intake.email', 'intake.demographics.email',
        ]),
        'street' => copilot_create_pluck_field($fields, [
            'street', 'address',
            'demographics.street', 'demographics.address',
            'intake.street', 'intake.demographics.street',
        ]),
        'city' => copilot_create_pluck_field($fields, [
            'city',
            'demographics.city', 'intake.city', 'intake.demographics.city',
        ]),
        'state' => copilot_create_pluck_field($fields, [
            'state', 'state_code',
            'demographics.state', 'intake.state', 'intake.demographics.state',
        ]),
        'postal_code' => copilot_create_pluck_field($fields, [
            'postal_code', 'zip', 'zipcode',
            'demographics.postal_code', 'demographics.zip',
            'intake.postal_code', 'intake.demographics.postal_code',
        ]),
    ];
}

/**
 * Thrown by copilot_create_normalize_dob when the raw DOB parses validly
 * as BOTH m/d/Y and d/m/Y AND the two interpretations yield different
 * dates. Caller surfaces a 422 with both candidates so the operator can
 * clarify rather than the parser silently picking one (Plan §4.1, audit
 * finding #16).
 */
final class AmbiguousDobException extends \RuntimeException
{
    /**
     * @param list<string> $candidates ISO YYYY-MM-DD strings, one per
     *                                 valid interpretation.
     */
    public function __construct(public readonly array $candidates)
    {
        parent::__construct('ambiguous_dob');
    }
}

/**
 * Coerce a raw DOB string to OpenEMR's "Y-m-d" shape. Accepts ISO,
 * unambiguous wordy formats, and (strict-mode) numeric formats.
 *
 * Plan §4.1 (audit finding #16): the previous implementation tried
 * m/d/Y before d/m/Y in a fall-through loop, silently coercing
 * "05/03/1962" to May 3 even when a European-handwritten intake meant
 * March 5. The permissive \DateTimeImmutable fallback compounded the
 * silent-coercion risk. Replaced with an explicit ambiguity check:
 *
 *   1. Y-m-d ISO first — unambiguous.
 *   2. Wordy English ("Aug 14, 1962" / "August 14, 1962") — unambiguous.
 *   3. d-m-Y (dash-separated European) — strict (must round-trip).
 *   4. Numeric slash forms: try BOTH m/d/Y AND d/m/Y; if both parse and
 *      yield distinct dates, throw AmbiguousDobException so the caller
 *      can 422 with both candidates.
 *
 * Returns null when no parser matches — caller surfaces "insufficient
 * demographics" so the operator can correct the form rather than
 * accepting a silently wrong date.
 *
 * @throws AmbiguousDobException when the raw value parses as both
 *                                m/d/Y AND d/m/Y with different results.
 */
function copilot_create_normalize_dob(?string $raw): ?string
{
    if ($raw === null || trim($raw) === '') {
        return null;
    }
    $trimmed = trim($raw);

    // 1. ISO Y-m-d first — unambiguous.
    $iso = \DateTime::createFromFormat('Y-m-d', $trimmed);
    if ($iso instanceof \DateTime && $iso->format('Y-m-d') === $trimmed) {
        return $iso->format('Y-m-d');
    }

    // 2. Wordy English ("Aug 14, 1962" / "August 14, 1962") — unambiguous.
    foreach (['M j, Y', 'F j, Y'] as $wordyFormat) {
        $dt = \DateTime::createFromFormat($wordyFormat, $trimmed);
        if ($dt instanceof \DateTime && $dt->format($wordyFormat) === $trimmed) {
            return $dt->format('Y-m-d');
        }
    }

    // 3. d-m-Y (dash-separated European) — explicit enough to accept.
    $dashEu = \DateTime::createFromFormat('d-m-Y', $trimmed);
    if ($dashEu instanceof \DateTime && $dashEu->format('d-m-Y') === $trimmed) {
        return $dashEu->format('Y-m-d');
    }

    // 4. Numeric slash forms — try BOTH conventions and surface ambiguity.
    //    A value like "05/03/1962" is May 3 (US) or March 5 (EU); we cannot
    //    pick safely without operator input.
    $usDt = \DateTime::createFromFormat('m/d/Y', $trimmed);
    $usValid = $usDt instanceof \DateTime && $usDt->format('m/d/Y') === $trimmed;
    $euDt = \DateTime::createFromFormat('d/m/Y', $trimmed);
    $euValid = $euDt instanceof \DateTime && $euDt->format('d/m/Y') === $trimmed;

    if ($usValid && $euValid) {
        $usIso = $usDt->format('Y-m-d');
        $euIso = $euDt->format('Y-m-d');
        if ($usIso !== $euIso) {
            throw new AmbiguousDobException([$usIso, $euIso]);
        }
        return $usIso; // Both conventions agree (e.g. "12/12/1962").
    }
    if ($usValid) {
        return $usDt->format('Y-m-d');
    }
    if ($euValid) {
        return $euDt->format('Y-m-d');
    }

    // Permissive \DateTimeImmutable fallback intentionally REMOVED per
    //    Plan §4.1 audit finding #16. A handwritten intake form whose DOB
    //    none of the strict parsers handle should surface as
    //    "insufficient_demographics" so the operator can correct it,
    //    rather than silently coercing into a probable-wrong date.
    return null;
}

/**
 * Look up an existing demo-intake patient by its deterministic-from-SHA
 * usertext1 tag. Returns [pid, patient_uuid_string] on hit, null on miss.
 *
 * AgDR-0068: closes audit finding #4 — the demo-intake patient row's
 * usertext1 is computed deterministically from the intake document SHA
 * (`wk2-demo-intake-<8-char-SHA>`), so two uploads of the same fixture
 * always resolve to the same usertext1 value. A pre-insert SELECT on
 * that value lets us return the existing pid + uuid on the second
 * upload rather than colliding on `patient_data.pubpid UNIQUE` and
 * surfacing a 500. Best-effort: any DB error is logged at WARNING and
 * treated as a miss so the caller falls through to the normal insert
 * path (which will then surface the real DB error from PatientService).
 *
 * @return array{0: int, 1: string}|null  [pid, patient_uuid_string] or null on miss
 */
function copilot_create_lookup_existing_patient_by_usertext1(string $usertext1): ?array
{
    try {
        $rows = QueryUtils::fetchRecords(
            'SELECT pid, uuid FROM patient_data WHERE usertext1 = ? LIMIT 1',
            [$usertext1],
        );
        if (count($rows) === 0) {
            return null;
        }
        $row = $rows[0];
        if (!is_array($row)) {
            return null;
        }
        $pidRaw = $row['pid'] ?? null;
        $uuidBin = $row['uuid'] ?? null;
        if (!is_numeric($pidRaw)) {
            return null;
        }
        if (!is_string($uuidBin) || strlen($uuidBin) !== 16) {
            return null;
        }
        return [(int) $pidRaw, UuidRegistry::uuidToString($uuidBin)];
    } catch (\RuntimeException | \PDOException $exc) {
        ServiceContainer::getLogger()->warning(
            'ClinicalCopilot: duplicate-intake usertext1 lookup failed (treating as miss)',
            ['exception' => $exc],
        );
        return null;
    }
}

/**
 * Normalize a sex/gender string into a single token PatientService accepts.
 */
function copilot_create_normalize_sex(?string $raw): string
{
    if ($raw === null || trim($raw) === '') {
        return 'Unknown';
    }
    $t = strtolower(trim($raw));
    return match (true) {
        $t === 'm' || str_starts_with($t, 'mal') => 'Male',
        $t === 'f' || str_starts_with($t, 'fem') => 'Female',
        default => 'Unknown',
    };
}

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
            $computed = hash_file('sha256', $scratch);
            if ($computed === false) {
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
