<?php

/**
 * Shared document-upload gateway for Week 2 extraction endpoints.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Api\Internal;

require_once(__DIR__ . "/../../../../../globals.php");
require_once(\OpenEMR\Core\OEGlobalsBag::getInstance()->getProjectDir() . "/library/documents.php");

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Modules\ClinicalCopilot\Controller\DocumentUploadController;
use OpenEMR\Modules\ClinicalCopilot\Repository\DocumentFactsRepository;
use OpenEMR\Modules\ClinicalCopilot\Service\LabResultWriter;
use OpenEMR\Services\BaseService;
use Symfony\Component\HttpFoundation\File\UploadedFile;
use Symfony\Component\HttpFoundation\Request;

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

/**
 * @param array<string, mixed> $payload
 */
function copilot_upload_send_json(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

function copilot_upload_string(mixed $value, string $default = ''): string
{
    return is_string($value) ? $value : $default;
}

function copilot_upload_detect_mime(string $tmpPath, string $fallback): string
{
    if (class_exists(\finfo::class)) {
        $finfo = new \finfo(FILEINFO_MIME_TYPE);
        $mime = $finfo->file($tmpPath);
        if (is_string($mime) && $mime !== '') {
            return $mime;
        }
    }

    return $fallback;
}

/**
 * Look up an existing document for (patient_id, sha256). Returns null on miss.
 *
 * AgDR-0063: closes the raw-document duplicate hole in the PRD's "without
 * creating duplicate or untraceable records" obligation. Same SHA across
 * different patients is intentionally independent (different chart visibility);
 * the unique index is on (patient_id, sha256).
 *
 * The lookup is best-effort: if the index table does not exist yet
 * (migration not applied) or any other DB error occurs, return null and
 * let the caller fall through to the normal addNewDocument() path. The
 * exception is logged so the missing-migration case is visible without
 * breaking uploads.
 *
 * @return array{0: string, 1: string}|null  [document_id, document_uuid_bin] or null on miss
 */
function copilot_upload_lookup_existing_document(int $pid, string $sha256): ?array
{
    try {
        $documentId = QueryUtils::fetchSingleValue(
            'SELECT document_id FROM copilot_document_sha_index WHERE patient_id = ? AND sha256 = ?',
            'document_id',
            [$pid, $sha256],
        );
        if ($documentId === null || $documentId === false) {
            return null;
        }
        $documentIdStr = is_scalar($documentId) ? (string) $documentId : '';
        if ($documentIdStr === '') {
            return null;
        }
        $documentUuidBin = QueryUtils::fetchSingleValue(
            'SELECT uuid FROM documents WHERE id = ?',
            'uuid',
            [$documentIdStr],
        );
        if (!is_string($documentUuidBin) || strlen($documentUuidBin) !== 16) {
            // Index points at a missing document — treat as a miss so we
            // re-store. A janitor task could reconcile orphans later.
            return null;
        }
        return [$documentIdStr, $documentUuidBin];
    } catch (\RuntimeException | \PDOException $exc) {
        ServiceContainer::getLogger()->warning(
            'ClinicalCopilot: SHA dedup lookup failed (treating as miss)',
            ['exception' => $exc],
        );
        return null;
    }
}

/**
 * Record a (patient_id, sha256) → document_id mapping for future dedup.
 *
 * INSERT IGNORE so a concurrent upload of the same SHA cannot fail the
 * second writer. If the index table does not exist (migration not applied),
 * log and continue — the upload still succeeded, only future dedup is
 * temporarily disabled until the migration runs.
 */
function copilot_upload_record_sha(int $pid, string $sha256, string $documentId): void
{
    try {
        QueryUtils::sqlStatementThrowException(
            'INSERT IGNORE INTO copilot_document_sha_index (patient_id, sha256, document_id) VALUES (?, ?, ?)',
            [$pid, $sha256, $documentId],
        );
    } catch (\RuntimeException $exc) {
        ServiceContainer::getLogger()->warning(
            'ClinicalCopilot: SHA dedup index write failed (upload still succeeded)',
            ['exception' => $exc],
        );
    }
}

/**
 * @return array{0: string, 1: string}
 */
function copilot_upload_store_document(
    string $tmpPath,
    string $originalName,
    string $mimeType,
    int $pid,
    int $userId,
): array {
    $categoryId = document_category_to_id('Clinical Notes');
    if (!is_numeric($categoryId)) {
        $categoryId = 1;
    }

    $size = filesize($tmpPath);
    $stored = addNewDocument(
        $originalName,
        $mimeType,
        $tmpPath,
        '0',
        $size === false ? '0' : (string) $size,
        $userId,
        (string) $pid,
        (int) $categoryId,
    );

    if (!is_array($stored) || !isset($stored['doc_id'])) {
        throw new \RuntimeException('openemr_document_store_failed');
    }

    $docIdRaw = $stored['doc_id'];
    $documentId = is_scalar($docIdRaw) ? (string) $docIdRaw : '';
    if ($documentId === '') {
        throw new \RuntimeException('openemr_document_store_failed');
    }
    $documentUuidBin = QueryUtils::fetchSingleValue(
        'SELECT uuid FROM documents WHERE id = ?',
        'uuid',
        [$documentId],
    );
    if (!is_string($documentUuidBin) || strlen($documentUuidBin) !== 16) {
        throw new \RuntimeException('openemr_document_uuid_missing');
    }

    return [$documentId, $documentUuidBin];
}

function copilot_upload_doc_url(int $pid, string $documentId): string
{
    $webRoot = OEGlobalsBag::getInstance()->getWebRoot();
    return $webRoot . '/controller.php?document&retrieve&patient_id='
        . rawurlencode((string) $pid)
        . '&document_id=' . rawurlencode($documentId)
        . '&as_file=false&original_file=true&disable_exit=false&show_original=true';
}

function copilot_upload_handle(string $docType): void
{
    $request = Request::createFromGlobals();
    $session = SessionWrapperFactory::getInstance()->getActiveSession();
    $csrf = $request->request->get('csrf_token_form') ?? $request->server->get('HTTP_APICSRFTOKEN');
    if (!is_string($csrf) || !CsrfUtils::verifyCsrfToken($csrf, $session, 'ClinicalCopilot')) {
        copilot_upload_send_json(403, ['error' => 'csrf_failure']);
    }

    if (!AclMain::aclCheckCore('patients', 'med')) {
        copilot_upload_send_json(403, ['error' => 'acl_denied']);
    }

    $pidRaw = $session->get('pid') ?? 0;
    $pid = is_numeric($pidRaw) ? (int) $pidRaw : 0;
    if ($pid <= 0) {
        copilot_upload_send_json(400, ['error' => 'missing_patient']);
    }

    $uploadedFile = $request->files->get('file');
    if (!$uploadedFile instanceof UploadedFile) {
        copilot_upload_send_json(400, ['error' => 'missing_file']);
    }
    if (!$uploadedFile->isValid()) {
        copilot_upload_send_json(400, ['error' => 'upload_error', 'code' => $uploadedFile->getError()]);
    }

    $tmpName = $uploadedFile->getPathname();
    $originalName = basename($uploadedFile->getClientOriginalName());
    if ($tmpName === '' || !is_uploaded_file($tmpName)) {
        copilot_upload_send_json(400, ['error' => 'invalid_upload']);
    }

    $scratch = tempnam(sys_get_temp_dir(), 'copilot-upload-');
    if (!is_string($scratch) || !copy($tmpName, $scratch)) {
        copilot_upload_send_json(500, ['error' => 'upload_copy_failed']);
    }

    $logger = ServiceContainer::getLogger();
    try {
        $patientUuidBin = BaseService::getUuidById((string) $pid, 'patient_data', 'pid');
        if (!is_string($patientUuidBin) || strlen($patientUuidBin) !== 16) {
            throw new \RuntimeException('patient_uuid_missing');
        }
        $patientUuid = UuidRegistry::uuidToString($patientUuidBin);
        $userIdRaw = $session->get('authUserID') ?? 0;
        $userId = is_numeric($userIdRaw) ? (int) $userIdRaw : 0;
        $mimeType = copilot_upload_detect_mime(
            $scratch,
            $uploadedFile->getClientMimeType() ?: 'application/octet-stream',
        );

        // AgDR-0063 — raw-document SHA dedup. Compute the file SHA before
        // storage and look up an existing documents.id for this
        // (patient_id, sha256). On hit, skip addNewDocument() and reuse the
        // existing document; the sidecar extraction still runs because
        // copilot_document_facts has its own idempotency key — any new facts
        // are added, repeats are silent no-ops. The "duplicate" flag goes
        // back to the UI so the panel can show "Document already on file".
        $sha256 = hash_file('sha256', $scratch);
        if (!is_string($sha256) || strlen($sha256) !== 64) {
            throw new \RuntimeException('sha256_compute_failed');
        }
        $duplicate = false;
        $existing = copilot_upload_lookup_existing_document($pid, $sha256);
        if ($existing !== null) {
            [$documentId, $documentUuidBin] = $existing;
            $duplicate = true;
        } else {
            [$documentId, $documentUuidBin] = copilot_upload_store_document(
                $tmpName,
                $originalName,
                $mimeType,
                $pid,
                $userId,
            );
            copilot_upload_record_sha($pid, $sha256, $documentId);
        }

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

        if ($docType === 'intake_form') {
            $payload = $controller->uploadIntakeForm($scratch, $originalName, $mimeType, $patientUuid, $documentUuidBin, (string) $userId);
        } else {
            $payload = $controller->uploadLabPdf($scratch, $originalName, $mimeType, $patientUuid, $documentUuidBin, (string) $userId);
        }

        // AgDR-0065 — for lab uploads, project newly-persisted facts onto
        // OpenEMR's native lab chain so FhirObservationLaboratoryService
        // surfaces them. Best-effort: if the writer throws, the upload still
        // succeeds with the extracted facts intact in copilot_document_facts.
        $labWriteSummary = ['written' => 0, 'skipped' => 0];
        if ($docType === 'lab_pdf') {
            try {
                $writer = new LabResultWriter($logger);
                $documentUuidStr = UuidRegistry::uuidToString($documentUuidBin);
                $summary = $writer->writeLabFactsForDocument(
                    $pid,
                    $patientUuid,
                    (int) $documentId,
                    $documentUuidStr,
                    $sha256,
                    $userId,
                );
                $labWriteSummary = [
                    'written' => $summary['written'],
                    'skipped' => $summary['skipped'],
                ];
            } catch (\RuntimeException | \PDOException $exc) {
                $logger->error(
                    'ClinicalCopilot: native lab chain write-back failed (upload still succeeded)',
                    ['exception' => $exc],
                );
            }
        }

        $payload['document_id'] = $documentId;
        $payload['document_uuid'] = UuidRegistry::uuidToString($documentUuidBin);
        $payload['doc_url'] = copilot_upload_doc_url($pid, $documentId);
        $payload['duplicate'] = $duplicate;
        $payload['document_sha256'] = $sha256;
        $payload['native_lab_writeback'] = $labWriteSummary;
        copilot_upload_send_json(200, $payload);
    } catch (\RuntimeException | \PDOException | \JsonException $e) {
        $logger->error('ClinicalCopilot: document upload failed', [
            'exception' => $e,
        ]);
        copilot_upload_send_json(500, [
            'error' => 'document_upload_failed',
            'detail' => 'Document upload failed. Please retry or contact support.',
        ]);
    } finally {
        if (is_file($scratch)) {
            unlink($scratch);
        }
    }
}
