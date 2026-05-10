<?php

/**
 * Shared document-upload gateway for Week 2 extraction endpoints.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

require_once(__DIR__ . "/../../../../../globals.php");
require_once(\OpenEMR\Core\OEGlobalsBag::getInstance()->getProjectDir() . "/library/documents.php");

use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Logging\SystemLogger;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Modules\ClinicalCopilot\Controller\DocumentUploadController;
use OpenEMR\Modules\ClinicalCopilot\Repository\DocumentFactsRepository;
use OpenEMR\Services\BaseService;

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

    $documentId = (string) $stored['doc_id'];
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
    $session = SessionWrapperFactory::getInstance()->getActiveSession();
    $csrf = $_POST['csrf_token_form'] ?? $_SERVER['HTTP_APICSRFTOKEN'] ?? null;
    if (!is_string($csrf) || !CsrfUtils::verifyCsrfToken($csrf, $session, 'ClinicalCopilot')) {
        copilot_upload_send_json(403, ['error' => 'csrf_failure']);
    }

    if (!AclMain::aclCheckCore('patients', 'med')) {
        copilot_upload_send_json(403, ['error' => 'acl_denied']);
    }

    $pid = (int) ($session->get('pid') ?? 0);
    if ($pid <= 0) {
        copilot_upload_send_json(400, ['error' => 'missing_patient']);
    }

    $upload = $_FILES['file'] ?? null;
    if (!is_array($upload) || !isset($upload['tmp_name'], $upload['name'], $upload['error'])) {
        copilot_upload_send_json(400, ['error' => 'missing_file']);
    }
    if ((int) $upload['error'] !== UPLOAD_ERR_OK) {
        copilot_upload_send_json(400, ['error' => 'upload_error', 'code' => (int) $upload['error']]);
    }

    $tmpName = copilot_upload_string($upload['tmp_name'] ?? null);
    $originalName = basename(copilot_upload_string($upload['name'] ?? null, 'upload.bin'));
    if ($tmpName === '' || !is_uploaded_file($tmpName)) {
        copilot_upload_send_json(400, ['error' => 'invalid_upload']);
    }

    $scratch = tempnam(sys_get_temp_dir(), 'copilot-upload-');
    if (!is_string($scratch) || !copy($tmpName, $scratch)) {
        copilot_upload_send_json(500, ['error' => 'upload_copy_failed']);
    }

    try {
        $patientUuidBin = BaseService::getUuidById((string) $pid, 'patient_data', 'pid');
        if (!is_string($patientUuidBin) || strlen($patientUuidBin) !== 16) {
            throw new \RuntimeException('patient_uuid_missing');
        }
        $patientUuid = UuidRegistry::uuidToString($patientUuidBin);
        $userId = (int) ($session->get('authUserID') ?? 0);
        $mimeType = copilot_upload_detect_mime($scratch, copilot_upload_string($upload['type'] ?? null, 'application/octet-stream'));

        [$documentId, $documentUuidBin] = copilot_upload_store_document(
            $tmpName,
            $originalName,
            $mimeType,
            $pid,
            $userId,
        );

        $sidecarBaseUrl = getenv('COPILOT_API_BASE_URL');
        $sidecarSecret = getenv('COPILOT_OPENEMR_GATEWAY_SHARED_SECRET');
        if (!is_string($sidecarBaseUrl) || $sidecarBaseUrl === '' || !is_string($sidecarSecret) || $sidecarSecret === '') {
            throw new \RuntimeException('sidecar_not_configured');
        }

        $logger = new SystemLogger();
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

        $payload['document_id'] = $documentId;
        $payload['document_uuid'] = UuidRegistry::uuidToString($documentUuidBin);
        $payload['doc_url'] = copilot_upload_doc_url($pid, $documentId);
        copilot_upload_send_json(200, $payload);
    } catch (\Exception $e) {
        (new SystemLogger())->error('ClinicalCopilot: document upload failed', [
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
