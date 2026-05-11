-- Wk2 Next04 (Plan §7) — raw-document SHA dedup index
-- AgDR-0063 (this migration), closes the second half of the PRD's
-- "without creating duplicate or untraceable records" obligation.
--
-- Before this table existed, uploading the same lab PDF twice for the same
-- patient created two rows in OpenEMR's `documents` table (addNewDocument
-- has no SHA check). The user saw two copies in the patient Documents tab.
-- copilot_document_facts already deduplicated derived facts via its
-- idempotency_key, but the raw document row was not protected.
--
-- This module-owned index sits in front of addNewDocument(). On upload,
-- public/api/upload_common.php computes sha256 of the file, looks up
-- (patient_id, sha256) here, and if a hit is found reuses the existing
-- documents.id instead of inserting a new row. The lookup also surfaces
-- "duplicate: true" in the API response so the UI can show
-- "Document already on file — using existing copy."
--
-- Key choices:
--   * Keyed on (patient_id, sha256) — same SHA across different patients
--     is intentionally independent (different chart, different visibility).
--   * patient_id is the integer pid (matches addNewDocument's foreign_id
--     contract). We do NOT store patient_uuid here because the dedup
--     happens at upload time when only pid is in the session.
--   * document_id is the BIGINT documents.id (not uuid) — addNewDocument
--     returns id, so storing id keeps the lookup path cheap.

CREATE TABLE IF NOT EXISTS `copilot_document_sha_index` (
    `id`           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `patient_id`   BIGINT UNSIGNED NOT NULL COMMENT 'patient_data.pid (matches documents.foreign_id)',
    `sha256`       CHAR(64)        NOT NULL COMMENT 'SHA-256 hex of raw uploaded file body',
    `document_id`  BIGINT UNSIGNED NOT NULL COMMENT 'documents.id of the row that holds this content',
    `created_at`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uniq_patient_sha` (`patient_id`, `sha256`),
    KEY `idx_document_id` (`document_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Clinical Co-Pilot Wk2 — raw-document SHA dedup index (AgDR-0063)';

-- Reverse:
--   DROP TABLE IF EXISTS `copilot_document_sha_index`;
