-- Week-2 Clinical Co-Pilot demo patient seed (SYNTHETIC DATA — not real patients).
--
-- Loads four demo patients matching the fixture personas at
-- openemr/agent/copilot-api/evals/fixtures/documents/ so the Wk2 upload
-- demos (Chen / Whitaker / Reyes / Kowalski) have a chart to bind to.
--
-- Idempotent:
--   * pid values 9101-9104 are reserved for this seed (Maria G. uses 9001).
--   * patient_data.pid is UNIQUE, so INSERT IGNORE makes re-runs no-ops.
--   * uuid_registry inserts also use INSERT IGNORE (uuid is the PK).
--
-- Reset path: openemr/agent/copilot-api/scripts/reset_demo_state.sh removes
-- these rows (filtered on pubpid LIKE 'WK2-DEMO-%').
--
-- DO NOT run on production. Development/demo stack only.
--
-- Usage (from repo root):
--   docker compose -f docker/development-easy/docker-compose.yml exec mysql \
--     mariadb -uroot -proot openemr < agent/copilot-api/scripts/seed_demo_patients.sql
--
-- Plan reference: openemr/planning/Plan_wk2_Claude_Next04_2026-05-10_demo-and-fhir-closure.md §4.2

-- ---------------------------------------------------------------------------
-- Schema notes (verified against openemr/sql/database.sql lines 8334-8472):
--   * patient_data has no `external_id` column. The plan's external_id values
--     are stored in usertext1 (a free-text column reserved for site-specific
--     tagging) so the reset script can find rows by either pubpid OR usertext1
--     pattern. The plan's `external_id LIKE 'wk2-demo-intake-%'` filter in
--     the reset script likewise matches against usertext1.
--   * patient_data.pid is NOT auto_increment (default 0); callers set it.
--   * pubpid is NOT UNIQUE — idempotency is enforced via the UNIQUE pid key.
--   * uuid is binary(16) and UNIQUE. We use fixed deterministic UUIDs so
--     re-running produces the same uuid_registry rows.
-- ---------------------------------------------------------------------------

-- Patient 01: Anne Chen
SET @p01_pid   := 9101;
SET @p01_uuid  := UNHEX(REPLACE('a1c2e301-0000-4000-8000-000000000001', '-', ''));

INSERT IGNORE INTO patient_data
    (pid, pubpid, uuid, fname, lname, DOB, sex,
     street, city, state, postal_code, date, usertext1)
VALUES
    (@p01_pid, 'WK2-DEMO-P01', @p01_uuid,
     'Anne', 'Chen', '1962-04-14', 'Female',
     '1 Synthetic Way', 'Austin', 'TX', '78701',
     NOW(), 'wk2-demo-p01');

INSERT IGNORE INTO uuid_registry (uuid, table_name, table_id, mapped, created)
VALUES (@p01_uuid, 'patient_data', @p01_pid, 1, NOW());

-- Patient 02: Marcus Whitaker
SET @p02_pid   := 9102;
SET @p02_uuid  := UNHEX(REPLACE('a1c2e302-0000-4000-8000-000000000002', '-', ''));

INSERT IGNORE INTO patient_data
    (pid, pubpid, uuid, fname, lname, DOB, sex,
     street, city, state, postal_code, date, usertext1)
VALUES
    (@p02_pid, 'WK2-DEMO-P02', @p02_uuid,
     'Marcus', 'Whitaker', '1971-09-02', 'Male',
     '2 Synthetic Way', 'Austin', 'TX', '78701',
     NOW(), 'wk2-demo-p02');

INSERT IGNORE INTO uuid_registry (uuid, table_name, table_id, mapped, created)
VALUES (@p02_uuid, 'patient_data', @p02_pid, 1, NOW());

-- Patient 03: Sofia Reyes
SET @p03_pid   := 9103;
SET @p03_uuid  := UNHEX(REPLACE('a1c2e303-0000-4000-8000-000000000003', '-', ''));

INSERT IGNORE INTO patient_data
    (pid, pubpid, uuid, fname, lname, DOB, sex,
     street, city, state, postal_code, date, usertext1)
VALUES
    (@p03_pid, 'WK2-DEMO-P03', @p03_uuid,
     'Sofia', 'Reyes', '1955-12-21', 'Female',
     '3 Synthetic Way', 'Austin', 'TX', '78701',
     NOW(), 'wk2-demo-p03');

INSERT IGNORE INTO uuid_registry (uuid, table_name, table_id, mapped, created)
VALUES (@p03_uuid, 'patient_data', @p03_pid, 1, NOW());

-- Patient 04: Tomas Kowalski
SET @p04_pid   := 9104;
SET @p04_uuid  := UNHEX(REPLACE('a1c2e304-0000-4000-8000-000000000004', '-', ''));

INSERT IGNORE INTO patient_data
    (pid, pubpid, uuid, fname, lname, DOB, sex,
     street, city, state, postal_code, date, usertext1)
VALUES
    (@p04_pid, 'WK2-DEMO-P04', @p04_uuid,
     'Tomas', 'Kowalski', '1948-07-30', 'Male',
     '4 Synthetic Way', 'Austin', 'TX', '78701',
     NOW(), 'wk2-demo-p04');

INSERT IGNORE INTO uuid_registry (uuid, table_name, table_id, mapped, created)
VALUES (@p04_uuid, 'patient_data', @p04_pid, 1, NOW());

-- Confirmation: show seeded demo patients.
SELECT pubpid, fname, lname FROM patient_data WHERE pubpid LIKE 'WK2-DEMO-%';
