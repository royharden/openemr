-- Clinical Co-Pilot demo seed (SYNTHETIC DATA — not a real patient).
--
-- Loads one demo patient (pid=9001, "Maria G.") with the chart shape required
-- by the Week-1 demo script:
--   * 2 A1c values 90 days apart with one abnormal flag
--   * 1 abnormal LDL
--   * 2 active meds (Metformin, Lisinopril) — Lisinopril deliberately appears in
--     BOTH `prescriptions` and `lists` so the lists-vs-rx duplicate verifier rule fires
--   * 1 allergy (Penicillin / rash)
--   * 1 immunization (Pneumococcal, 2019) — older than 5 years to demonstrate
--     stale-data labeling
--   * 1 stale medication (Atorvastatin) dated >180d ago
--
-- Idempotent: every INSERT uses ON DUPLICATE KEY UPDATE keyed off business
-- columns so re-running the script is safe. dev-reset-install-demodata
-- truncates these tables, so re-run after a reset.
--
-- DO NOT run on a production database. This is for the docker development-easy
-- stack only.
--
-- Usage (from repo root, with the development-easy compose stack running):
--   docker compose -f docker/development-easy/docker-compose.yml exec mysql \
--     mariadb -uroot -proot openemr < agent/copilot-api/demo/seed_demo_patient.sql

SET @demo_pid := 9001;
SET @demo_pubpid := 'COPILOT-DEMO-9001';
SET @demo_uuid := UNHEX(REPLACE('11111111-1111-4111-8111-111111111111', '-', ''));

-- 1. Patient demographics
INSERT INTO patient_data (pid, pubpid, uuid, fname, lname, DOB, sex, date)
VALUES (@demo_pid, @demo_pubpid, @demo_uuid, 'Maria', 'G.', '1968-03-04', 'Female', NOW())
ON DUPLICATE KEY UPDATE fname = VALUES(fname), lname = VALUES(lname),
                        DOB = VALUES(DOB), sex = VALUES(sex), uuid = VALUES(uuid);

-- 2. Active problems (lists)
DELETE FROM lists WHERE pid = @demo_pid AND title IN
    ('Type 2 Diabetes', 'Hypertension', 'Hyperlipidemia', 'Penicillin');

INSERT INTO lists (pid, type, title, activity, date, begdate)
VALUES
    (@demo_pid, 'medical_problem', 'Type 2 Diabetes', 1, NOW(), '2018-01-15'),
    (@demo_pid, 'medical_problem', 'Hypertension',    1, NOW(), '2020-09-01'),
    (@demo_pid, 'medical_problem', 'Hyperlipidemia',  1, NOW(), '2022-03-20');

-- 3. Allergies (lists with type='allergy') — idempotent.
DELETE FROM lists WHERE pid = @demo_pid AND type = 'allergy' AND title = 'Penicillin';

INSERT INTO lists (pid, type, title, activity, date, begdate, comments)
VALUES (@demo_pid, 'allergy', 'Penicillin', 1, NOW(), '2010-06-01', 'Reaction: rash');

-- 4. Active medications (prescriptions)
--    NOTE: prescriptions has three NOT NULL columns without defaults — txDate,
--    usage_category_title, request_intent_title. They MUST be set on insert
--    or MariaDB will reject with "Field X doesn't have a default value".
--    `unit` is INT (option_id reference), not a free-text string — leave NULL
--    rather than inserting "mg". Dosage already carries the human label.
DELETE FROM prescriptions WHERE patient_id = @demo_pid;

INSERT INTO prescriptions
    (patient_id, drug, dosage, quantity, size, route,
     start_date, date_added, active, date_modified, txDate,
     usage_category_title, request_intent_title)
VALUES
    (@demo_pid, 'Metformin',    '500 mg BID',    '60', '500', 'PO',
        DATE_SUB(CURDATE(), INTERVAL 60 DAY),
        DATE_SUB(NOW(),     INTERVAL 60 DAY), 1, NOW(),
        DATE_SUB(CURDATE(), INTERVAL 60 DAY), '', ''),
    (@demo_pid, 'Lisinopril',   '10 mg PO daily', '30', '10', 'PO',
        DATE_SUB(CURDATE(), INTERVAL 45 DAY),
        DATE_SUB(NOW(),     INTERVAL 45 DAY), 1, NOW(),
        DATE_SUB(CURDATE(), INTERVAL 45 DAY), '', ''),
    (@demo_pid, 'Atorvastatin', '20 mg PO daily', '30', '20', 'PO',
        DATE_SUB(CURDATE(), INTERVAL 200 DAY),
        DATE_SUB(NOW(),     INTERVAL 200 DAY), 1, NOW(),
        DATE_SUB(CURDATE(), INTERVAL 200 DAY), '', '');

-- 4b. Lisinopril ALSO appears on the active problem/medication list — this
--     duplicate is intentional and exercises the lists-vs-prescriptions
--     conflict-surfacing verifier rule. Idempotent.
DELETE FROM lists WHERE pid = @demo_pid AND type = 'medication' AND title = 'Lisinopril 10 mg PO daily';

INSERT INTO lists (pid, type, title, activity, date, begdate, comments)
VALUES (@demo_pid, 'medication', 'Lisinopril 10 mg PO daily', 1, NOW(),
        DATE_SUB(CURDATE(), INTERVAL 45 DAY), 'Duplicate of prescriptions row — intentional for demo');

-- 5. Recent labs — two A1c values + one abnormal LDL.
--    OpenEMR's lab chain is:  procedure_order -> procedure_report -> procedure_result
--    The custom module's RecentLabsPacketBuilder requires the join through
--    procedure_report; insert one report per order, then results referencing
--    the report. Idempotent: cascade deletes by order_diagnosis tag.

DELETE pr
    FROM procedure_result AS pr
    INNER JOIN procedure_report  AS prep ON prep.procedure_report_id = pr.procedure_report_id
    INNER JOIN procedure_order   AS po   ON po.procedure_order_id    = prep.procedure_order_id
    WHERE po.patient_id = @demo_pid
      AND po.order_diagnosis IN ('demo-a1c', 'demo-ldl');

DELETE prep
    FROM procedure_report AS prep
    INNER JOIN procedure_order AS po ON po.procedure_order_id = prep.procedure_order_id
    WHERE po.patient_id = @demo_pid
      AND po.order_diagnosis IN ('demo-a1c', 'demo-ldl');

DELETE FROM procedure_order
    WHERE patient_id = @demo_pid
      AND order_diagnosis IN ('demo-a1c', 'demo-ldl');

-- 5a. Old A1c (95 days ago, 7.2%, normal)
INSERT INTO procedure_order (patient_id, date_ordered, order_status, order_diagnosis)
VALUES (@demo_pid, DATE_SUB(CURDATE(), INTERVAL 95 DAY), 'complete', 'demo-a1c');
SET @demo_order_a1c_old := LAST_INSERT_ID();

INSERT INTO procedure_report (procedure_order_id, date_collected, date_report,
                              report_status, review_status)
VALUES (@demo_order_a1c_old,
        DATE_SUB(CURDATE(), INTERVAL 95 DAY),
        DATE_SUB(CURDATE(), INTERVAL 95 DAY),
        'complete', 'reviewed');
SET @demo_report_a1c_old := LAST_INSERT_ID();

INSERT INTO procedure_result (procedure_report_id, result_data_type, result_code,
                              result_text, result, units, `range`, abnormal,
                              date, result_status)
VALUES (@demo_report_a1c_old, 'N', 'A1C', 'Hemoglobin A1c',
        '7.2', '%', '4.0-5.6', 'no',
        DATE_SUB(CURDATE(), INTERVAL 95 DAY), 'final');

-- 5b. Recent A1c (5 days ago, 8.4%, abnormal high)
INSERT INTO procedure_order (patient_id, date_ordered, order_status, order_diagnosis)
VALUES (@demo_pid, DATE_SUB(CURDATE(), INTERVAL 5 DAY), 'complete', 'demo-a1c');
SET @demo_order_a1c_new := LAST_INSERT_ID();

INSERT INTO procedure_report (procedure_order_id, date_collected, date_report,
                              report_status, review_status)
VALUES (@demo_order_a1c_new,
        DATE_SUB(CURDATE(), INTERVAL 5 DAY),
        DATE_SUB(CURDATE(), INTERVAL 5 DAY),
        'complete', 'reviewed');
SET @demo_report_a1c_new := LAST_INSERT_ID();

INSERT INTO procedure_result (procedure_report_id, result_data_type, result_code,
                              result_text, result, units, `range`, abnormal,
                              date, result_status)
VALUES (@demo_report_a1c_new, 'N', 'A1C', 'Hemoglobin A1c',
        '8.4', '%', '4.0-5.6', 'high',
        DATE_SUB(CURDATE(), INTERVAL 5 DAY), 'final');

-- 5c. Recent LDL (8 days ago, 186 mg/dL, abnormal high)
INSERT INTO procedure_order (patient_id, date_ordered, order_status, order_diagnosis)
VALUES (@demo_pid, DATE_SUB(CURDATE(), INTERVAL 8 DAY), 'complete', 'demo-ldl');
SET @demo_order_ldl := LAST_INSERT_ID();

INSERT INTO procedure_report (procedure_order_id, date_collected, date_report,
                              report_status, review_status)
VALUES (@demo_order_ldl,
        DATE_SUB(CURDATE(), INTERVAL 8 DAY),
        DATE_SUB(CURDATE(), INTERVAL 8 DAY),
        'complete', 'reviewed');
SET @demo_report_ldl := LAST_INSERT_ID();

INSERT INTO procedure_result (procedure_report_id, result_data_type, result_code,
                              result_text, result, units, `range`, abnormal,
                              date, result_status)
VALUES (@demo_report_ldl, 'N', 'LDL', 'LDL Cholesterol',
        '186', 'mg/dL', '0-99', 'high',
        DATE_SUB(CURDATE(), INTERVAL 8 DAY), 'final');

-- 6. Immunization (older — exercises stale-data labeling for vaccines)
DELETE FROM immunizations WHERE patient_id = @demo_pid AND cvx_code IN ('33', '133');

INSERT INTO immunizations (patient_id, administered_date, cvx_code, immunization_id, note)
VALUES
    (@demo_pid, '2019-10-12', '33', 0, 'Pneumococcal polysaccharide PPSV23 (synthetic demo)');

-- Done.
SELECT CONCAT('Demo patient seeded: pid=', @demo_pid,
              ' name=Maria G. — open in chart and run the Co-Pilot.') AS status;
