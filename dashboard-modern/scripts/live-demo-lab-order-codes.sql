-- Bridges Maria G.'s Week 1 demo lab results into the order-code shape that
-- OpenEMR's FHIR Observation laboratory service expects.
--
-- The Week 1 demo seed creates:
--   procedure_order -> procedure_report -> procedure_result
-- but FHIR Observation search joins through procedure_order_code. This
-- idempotently inserts one order-code row per Maria G. lab report by copying
-- the result code/name already present in procedure_result.

INSERT INTO procedure_order_code (
  procedure_order_id,
  procedure_order_seq,
  procedure_code,
  procedure_name,
  procedure_order_title,
  procedure_type
)
SELECT
  po.procedure_order_id,
  pr.procedure_order_seq,
  prs.result_code,
  prs.result_text,
  prs.result_text,
  po.procedure_order_type
FROM procedure_order AS po
JOIN patient_data AS pd
  ON pd.pid = po.patient_id
JOIN procedure_report AS pr
  ON pr.procedure_order_id = po.procedure_order_id
JOIN procedure_result AS prs
  ON prs.procedure_report_id = pr.procedure_report_id
WHERE pd.pubpid = 'COPILOT-DEMO-9001'
  AND po.procedure_order_type = 'laboratory_test'
  AND prs.result_code IS NOT NULL
  AND prs.result_code != ''
  AND prs.result_text IS NOT NULL
  AND prs.result_text != ''
  AND NOT EXISTS (
    SELECT 1
    FROM procedure_order_code AS existing
    WHERE existing.procedure_order_id = po.procedure_order_id
      AND existing.procedure_order_seq = pr.procedure_order_seq
  );
