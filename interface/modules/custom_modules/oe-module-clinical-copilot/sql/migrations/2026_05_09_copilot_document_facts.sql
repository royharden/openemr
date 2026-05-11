-- Wk2 Workstream 0.5 — contract-freeze migration
-- Plan §3 #11 (originally AgDR-0037, superseded by AgDR-0065 on 2026-05-10)
--
-- Module-owned table for derived facts extracted from lab PDFs and intake
-- forms by the Clinical Co-Pilot sidecar. Lab-PDF rows now ALSO get
-- written to OpenEMR's native lab chain (procedure_order /
-- procedure_order_code / procedure_report / procedure_result) via
-- LabResultWriter — see migration 2026_05_10_copilot_fact_to_result_map.sql
-- and AgDR-0065. copilot_document_facts remains the authoritative source
-- for non-lab fields (intake demographics, allergies, etc.) and for fact-
-- level metadata (page index, bbox, quote, extraction confidence) that the
-- native lab tables do not carry. The map table makes the relationship
-- explicit and exactly-once.
--
-- The Wk1 Co-Pilot module already established the convention that the PHP
-- gateway is the only writer to module-owned tables. The sidecar returns the
-- structured ExtractedDocument; DocumentFactsRepository persists rows here.
--
-- Idempotency key: SHA-256(patient_uuid || document_sha256 || field_path).
-- Re-uploading the same PDF for the same patient never duplicates rows.

CREATE TABLE IF NOT EXISTS `copilot_document_facts` (
    `id`                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    -- Idempotency key — SHA-256 hex (64 chars).
    `idempotency_key`      CHAR(64)        NOT NULL,
    -- Patient + document identity.
    `patient_uuid_hash`    CHAR(64)        NOT NULL COMMENT 'SHA-256 of patient.uuid; never store raw uuid here',
    `document_uuid`        VARBINARY(16)   NOT NULL COMMENT 'OpenEMR documents.uuid (binary 16)',
    `document_sha256`      CHAR(64)        NOT NULL COMMENT 'SHA-256 of document body for dedup',
    `doc_type`             VARCHAR(32)     NOT NULL COMMENT 'lab_pdf | intake_form',
    -- The extracted field.
    `field_path`           VARCHAR(255)    NOT NULL COMMENT 'e.g. lipid.ldl, vitals.bp_systolic',
    `field_value_json`     JSON            NOT NULL COMMENT 'value/unit/reference_range/flag/loinc_code',
    `confidence`           DECIMAL(4,3)    DEFAULT NULL COMMENT '0.000-1.000; null = exact',
    -- Citation packet bits (for the verifier and the UI bbox overlay).
    `quote_or_value`       TEXT            DEFAULT NULL COMMENT 'verbatim quote from PDF text layer',
    `page_index`           INT UNSIGNED    DEFAULT NULL COMMENT '0-based',
    `page_or_section`      VARCHAR(255)    DEFAULT NULL COMMENT 'header path or page label',
    `bbox_json`            JSON            DEFAULT NULL COMMENT '[x0,y0,x1,y1] normalized 0..1',
    `bbox_unit`            VARCHAR(16)     DEFAULT NULL COMMENT 'exact | approximate',
    -- Provenance / audit.
    `extracted_by_model`   VARCHAR(64)     NOT NULL COMMENT 'e.g. claude-sonnet-4-6',
    `extracted_at`         DATETIME        NOT NULL,
    `created_at`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `created_by`           VARCHAR(64)     DEFAULT NULL COMMENT 'OpenEMR user id of uploader',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uniq_idempotency_key` (`idempotency_key`),
    KEY `ix_patient_doc` (`patient_uuid_hash`, `document_uuid`),
    KEY `ix_doc_sha` (`document_sha256`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Clinical Co-Pilot Wk2 — extracted facts from lab PDFs / intake forms (AgDR-0037)';

-- Reverse:
--   DROP TABLE IF EXISTS `copilot_document_facts`;
