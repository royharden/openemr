-- Validates that seed_demo_patient.sql produced rows that the Clinical Co-Pilot
-- module's source-packet builders can actually find. Run AFTER seed.
--
-- Expected output (rows whose first column ends with 'OK'):
--   patient_count=1
--   problem_count=3
--   allergy_count=1
--   prescription_count=3   (Metformin, Lisinopril, Atorvastatin)
--   list_med_count=1       (Lisinopril duplicate for the lists-vs-rx conflict rule)
--   lab_result_count=3     (joined through procedure_report — proves schema fix)
--   abnormal_lab_count=2   (recent A1c + LDL)
--   immunization_count=1
--   immunization_pneumococcal_count=1
--
-- If any count is wrong, the seed script did not run cleanly.

SET @demo_pid := 9001;

SELECT 'patient_count' AS metric, COUNT(*) AS value
  FROM patient_data
  WHERE pid = @demo_pid;

SELECT 'problem_count' AS metric, COUNT(*) AS value
  FROM lists
  WHERE pid = @demo_pid AND type = 'medical_problem' AND activity = 1;

SELECT 'allergy_count' AS metric, COUNT(*) AS value
  FROM lists
  WHERE pid = @demo_pid AND type = 'allergy' AND activity = 1;

SELECT 'prescription_count' AS metric, COUNT(*) AS value
  FROM prescriptions
  WHERE patient_id = @demo_pid AND active = 1;

SELECT 'list_med_count' AS metric, COUNT(*) AS value
  FROM lists
  WHERE pid = @demo_pid AND type = 'medication' AND activity = 1;

-- Critical: the join below is identical in shape to RecentLabsPacketBuilder.
-- If this returns 0, the lab seed did not run through procedure_report and
-- the demo will produce zero lab packets at runtime.
SELECT 'lab_result_count' AS metric, COUNT(*) AS value
  FROM procedure_result AS pr
  INNER JOIN procedure_report AS prep
          ON prep.procedure_report_id = pr.procedure_report_id
  INNER JOIN procedure_order AS po
          ON po.procedure_order_id = prep.procedure_order_id
  WHERE po.patient_id = @demo_pid;

SELECT 'abnormal_lab_count' AS metric, COUNT(*) AS value
  FROM procedure_result AS pr
  INNER JOIN procedure_report AS prep
          ON prep.procedure_report_id = pr.procedure_report_id
  INNER JOIN procedure_order AS po
          ON po.procedure_order_id = prep.procedure_order_id
  WHERE po.patient_id = @demo_pid
    AND pr.abnormal IN ('yes', 'high', 'low');

SELECT 'immunization_count' AS metric, COUNT(*) AS value
  FROM immunizations
  WHERE patient_id = @demo_pid;

-- Critical: the Co-Pilot packet builder must resolve CVX codes through the
-- OpenEMR `codes` table, not through list_options('immunizations'). In stock
-- OpenEMR list_options option_id=33 is "Hepatitis A 1", while CVX code 33 is
-- Pneumococcal PPSV23.
SELECT 'immunization_pneumococcal_count' AS metric, COUNT(*) AS value
  FROM immunizations AS i
  LEFT JOIN code_types AS ct
         ON ct.ct_key = 'CVX'
  LEFT JOIN codes AS c
         ON c.code_type = ct.ct_id
        AND c.code = i.cvx_code
  WHERE i.patient_id = @demo_pid
    AND i.cvx_code = '33'
    AND (
      c.code_text LIKE '%pneumococcal%'
      OR c.code_text_short LIKE '%pneumococcal%'
    );

-- Detail: list each lab so a human can eyeball values match the seed.
SELECT pr.result_code, pr.result_text, pr.result, pr.units, pr.`range`,
       pr.abnormal, DATE(pr.date) AS result_date
  FROM procedure_result AS pr
  INNER JOIN procedure_report AS prep
          ON prep.procedure_report_id = pr.procedure_report_id
  INNER JOIN procedure_order AS po
          ON po.procedure_order_id = prep.procedure_order_id
  WHERE po.patient_id = @demo_pid
  ORDER BY pr.date DESC;
