-- Wk2 Next04 §6 — Map extracted document facts to native OpenEMR lab rows.
-- AgDR-0065 (this migration) supersedes AgDR-0037's "defer to Wk3" scoping.
--
-- One row per (copilot_document_fact, procedure_result) pair so that the
-- native lab write-back is exactly-once even under retries. The unique key
-- on `copilot_document_fact_id` prevents double-writes from any code path:
-- if the same extracted fact is processed twice, the second LabResultWriter
-- run will skip it via INSERT IGNORE and the (order, report, result) rows
-- it would have created are never inserted.
--
-- This map plus the SHA-256 dedup index from AgDR-0063 give us the full
-- "round-trip without creating duplicate or untraceable records" contract:
--   * Raw document SHA dedup (AgDR-0063)  → only one `documents` row per file.
--   * Extracted fact idempotency key      → only one `copilot_document_facts` row per (patient, doc, field).
--   * Fact-to-result map (this AgDR)      → only one `procedure_result` row per fact.
--
-- Why store both procedure_result_id AND procedure_order_id:
--   * `procedure_result_id` is what the FHIR Observation read path returns
--     as `Observation.id`. Source chips link to it via /fhir/r4/Observation/{uuid}.
--   * `procedure_order_id` lets the reset script delete the order, report,
--     and order_code rows in a single sweep keyed on the orders we created
--     (vs. having to navigate through procedure_report and order_code first).
--
-- procedure_result_uuid is stored as VARBINARY(16) — same shape OpenEMR uses
-- in procedure_result.uuid. The FHIR /Observation/{id} URL uses the string
-- form via UuidRegistry::uuidToString().

CREATE TABLE IF NOT EXISTS `copilot_fact_to_result_map` (
    `id`                          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `copilot_document_fact_id`    BIGINT UNSIGNED NOT NULL COMMENT 'FK -> copilot_document_facts.id',
    `procedure_order_id`          BIGINT UNSIGNED NOT NULL COMMENT 'FK -> procedure_order.procedure_order_id',
    `procedure_report_id`         BIGINT UNSIGNED NOT NULL COMMENT 'FK -> procedure_report.procedure_report_id',
    `procedure_result_id`         BIGINT UNSIGNED NOT NULL COMMENT 'FK -> procedure_result.procedure_result_id',
    `procedure_result_uuid`       VARBINARY(16)   NOT NULL COMMENT 'mirror of procedure_result.uuid for fast FHIR URL building',
    `created_at`                  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uniq_fact` (`copilot_document_fact_id`),
    KEY `idx_procedure_result_id` (`procedure_result_id`),
    KEY `idx_procedure_order_id` (`procedure_order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Clinical Co-Pilot Wk2 — bridge from copilot_document_facts to OpenEMR procedure_result (AgDR-0065)';

-- Reverse:
--   DROP TABLE IF EXISTS `copilot_fact_to_result_map`;
