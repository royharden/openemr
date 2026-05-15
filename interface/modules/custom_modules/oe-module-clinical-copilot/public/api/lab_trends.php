<?php

/**
 * Lab Trends endpoint (Plan §7.1, AgDR-0088).
 *
 * GET-only, session-authenticated, ACL-gated. Returns a time-series of
 * Co-Pilot-extracted lab observations grouped by LOINC code for the
 * patient currently scoped in the OpenEMR session (pid). The Co-Pilot's
 * chart sidebar widget consumes this payload to render one mini-chart
 * per analyte.
 *
 * Why this instead of the FHIR Observation R4 endpoint:
 *   The OAuth-protected FHIR REST endpoint
 *   `/apis/default/fhir/r4/Observation?subject=…&category=laboratory`
 *   would force the browser-side widget to obtain + carry a Bearer
 *   token, which the same-origin OpenEMR session does not provide.
 *   Phase 3.8 / AgDR-0083 solved this for the single-Observation
 *   preview chip via a session-cookie proxy; this endpoint is the
 *   trend-list analogue. Both proxies terminate auth at the OpenEMR
 *   session layer (cookie + ACL `patients/med` + patient-scope bind),
 *   matching the existing chart-context view authorization model.
 *
 * Why filter to copilot-extracted rows:
 *   The Co-Pilot's LabResultWriter (AgDR-0067 / AgDR-0081) writes a
 *   canonical row to `copilot_fact_to_result_map` for every extracted
 *   lab fact promoted into OpenEMR's native procedure_* chain. Non-Co-Pilot
 *   lab rows on the same chart should NOT appear in this trend (they're
 *   already visible in the native Lab Review screen). Limiting the widget
 *   through that map keeps the trend story scoped to documents the agent
 *   has actually extracted, and avoids surfacing data the demo audience
 *   didn't see uploaded.
 *
 * Request:
 *   GET …/lab_trends.php
 *   GET …/lab_trends.php?loinc=13457-7        — restrict to a single LOINC
 *   GET …/lab_trends.php?min_observations=3   — only return LOINCs with
 *                                                ≥N data points (default 1;
 *                                                Plan §7.1 says ≥3 to render)
 *
 * Response:
 *   200 application/json
 *     {
 *       "patient_uuid": "<full-uuid>",
 *       "series": [
 *         {
 *           "loinc": "13457-7",
 *           "label": "LDL Cholesterol, Calculated",
 *           "unit": "mg/dL",
 *           "reference_range": "Optimal <100",
 *           "observations": [
 *             {"date": "2025-07-18", "value": 195.0, "abnormal": "H",
 *              "result_status": "prelim",
 *              "procedure_result_uuid": "..."},
 *             ...
 *           ]
 *         },
 *         ...
 *       ]
 *     }
 *   400 missing_patient | invalid_loinc
 *   403 acl_denied
 *   500 unexpected
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

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Acl\AclMain;
use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Common\Uuid\UuidRegistry;
use OpenEMR\Services\BaseService;
use Symfony\Component\HttpFoundation\Request;

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');

/**
 * @param array<string, mixed> $payload
 */
function copilot_lab_trends_send_json(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

/**
 * Parse a procedure_result row into a public observation dict.
 *
 * Accepts the loose `array<mixed>` shape that QueryUtils::fetchRecords
 * returns rather than a typed array shape — the SQL columns may legally
 * carry NULL or string values per the OpenEMR schema, and narrowing each
 * field at the call site is more defensive than requiring a typed shape
 * here.
 *
 * @param array<mixed> $row
 * @return array{date: string, value: float|null, value_text: string, abnormal: string|null, result_status: string|null, procedure_result_uuid: string|null}
 */
function copilot_lab_trends_parse_row(array $row): array
{
    $rawResult = $row['result'] ?? null;
    $resultText = is_scalar($rawResult) ? (string) $rawResult : '';
    $numeric = is_numeric($resultText) ? (float) $resultText : null;

    $date = is_string($row['date'] ?? null) ? $row['date'] : '';
    // Normalize the date to YYYY-MM-DD for chart x-axis consumption. Source
    // is `procedure_result.date` which the writer stores as YYYY-MM-DD HH:MM:SS;
    // older rows may be date-only. Slicing the first 10 chars is safe for
    // both shapes.
    $datePrefix = strlen($date) >= 10 ? substr($date, 0, 10) : $date;

    $abnormal = is_string($row['abnormal'] ?? null) && $row['abnormal'] !== ''
        ? $row['abnormal']
        : null;

    $rawUuid = $row['result_uuid'] ?? null;
    $resultUuid = null;
    if (is_string($rawUuid) && strlen($rawUuid) === 16) {
        $resultUuid = UuidRegistry::uuidToString($rawUuid);
    }

    return [
        'date' => $datePrefix,
        'value' => $numeric,
        'value_text' => $resultText,
        'abnormal' => $abnormal,
        'result_status' => is_string($row['result_status'] ?? null) ? $row['result_status'] : null,
        'procedure_result_uuid' => $resultUuid,
    ];
}

$logger = ServiceContainer::getLogger();

try {
    $request = Request::createFromGlobals();
    $session = SessionWrapperFactory::getInstance()->getActiveSession();

    // 1. ACL — same gate as fhir_observation_preview.php (AgDR-0083) and
    //    the rest of the Co-Pilot's chart-context surface.
    if (!AclMain::aclCheckCore('patients', 'med')) {
        copilot_lab_trends_send_json(403, ['error' => 'acl_denied']);
    }

    // 2. Resolve the current session's patient. The widget is rendered
    //    inside the chart, so pid is always the in-context patient.
    $pidRaw = $session->get('pid') ?? 0;
    $pid = is_numeric($pidRaw) ? (int) $pidRaw : 0;
    if ($pid <= 0) {
        copilot_lab_trends_send_json(400, ['error' => 'missing_patient']);
    }

    // 3. Optional LOINC filter — used by the future "View just LDL" drill-down.
    //    LOINC pattern: 1-7 digits, hyphen, 1 digit. Reject anything else
    //    to avoid SQL-injection vectors via the parameterized query later.
    $loincFilter = $request->query->get('loinc');
    if ($loincFilter !== null) {
        // Symfony's InputBag::get returns string|null; the !== null guard above
        // narrows to string for phpstan-level-10, so we don't re-test is_string().
        if (preg_match('/^[0-9]{1,7}-[0-9]$/', $loincFilter) !== 1) {
            copilot_lab_trends_send_json(400, ['error' => 'invalid_loinc']);
        }
    }

    // 4. min_observations — caller can request only series that meet a
    //    minimum count. Plan §7.1 specifies ≥3 to render; the widget will
    //    pass `min_observations=3` so the response only carries chartable
    //    series. Defaults to 1 so the eval-mock test path can assert on a
    //    single observation without tripping the filter.
    $minObsRaw = $request->query->get('min_observations');
    $minObservations = 1;
    if ($minObsRaw !== null) {
        if (!is_numeric($minObsRaw) || (int) $minObsRaw < 1 || (int) $minObsRaw > 100) {
            copilot_lab_trends_send_json(400, ['error' => 'invalid_min_observations']);
        }
        $minObservations = (int) $minObsRaw;
    }

    // 5. Resolve patient UUID for the response payload (display only — the
    //    SQL filter below uses the integer pid).
    $patientUuidBin = BaseService::getUuidById((string) $pid, 'patient_data', 'pid');
    if (!is_string($patientUuidBin) || strlen($patientUuidBin) !== 16) {
        copilot_lab_trends_send_json(500, ['error' => 'patient_uuid_lookup_failed']);
    }
    $patientUuidString = UuidRegistry::uuidToString($patientUuidBin);

    // 6. Pull all Co-Pilot-extracted procedure_result rows for this pid.
    //    JOIN chain mirrors the FHIR Observation read path:
    //      procedure_order (patient + provider)
    //      └─ procedure_order_code (LOINC at seq=1)
    //      └─ procedure_report (date_collected)
    //         └─ procedure_result (value, abnormal, status, units)
    //      └─ copilot_fact_to_result_map + copilot_document_facts
    //         (Co-Pilot provenance + extracted clinical collection date)
    //
    //    Filter through `copilot_fact_to_result_map` rather than a text
    //    provenance column. The OpenEMR `procedure_order` schema has no
    //    `notes` column, and the map is the exactly-once source of truth
    //    for rows created by LabResultWriter. The map also mirrors the
    //    procedure_result UUID for downstream FHIR-preview chip-click.
    $sql = '
        SELECT
            poc.procedure_code AS loinc,
            poc.procedure_name AS label,
            pres.result        AS result,
            pres.units         AS units,
            pres.`range`       AS reference_range,
            pres.abnormal      AS abnormal,
            pres.result_status AS result_status,
            COALESCE(
                NULLIF(JSON_UNQUOTE(JSON_EXTRACT(cdf.field_value_json, "$.collection_date")), "null"),
                prep.date_collected
            ) AS date,
            cfrm.procedure_result_uuid AS result_uuid
        FROM `procedure_order` po
        INNER JOIN `procedure_order_code` poc
                ON poc.procedure_order_id = po.procedure_order_id
               AND poc.procedure_order_seq = 1
        INNER JOIN `procedure_report` prep
                ON prep.procedure_order_id = po.procedure_order_id
               AND prep.procedure_order_seq = 1
        INNER JOIN `procedure_result` pres
                ON pres.procedure_report_id = prep.procedure_report_id
        INNER JOIN `copilot_fact_to_result_map` cfrm
                ON cfrm.procedure_order_id = po.procedure_order_id
               AND cfrm.procedure_report_id = prep.procedure_report_id
               AND cfrm.procedure_result_id = pres.procedure_result_id
        INNER JOIN `copilot_document_facts` cdf
                ON cdf.id = cfrm.copilot_document_fact_id
        WHERE po.patient_id = ?
    ';
    $params = [$pid];
    if ($loincFilter !== null) {
        $sql .= ' AND poc.procedure_code = ? ';
        $params[] = $loincFilter;
    }
    $sql .= ' ORDER BY poc.procedure_code ASC, date ASC, pres.procedure_result_id ASC';

    // QueryUtils::fetchRecords is PHPDoc-typed `list<array<mixed>>`, so an
    // is_array guard here would always be true (level-10 phpstan flags it).
    $rows = QueryUtils::fetchRecords($sql, $params);

    // 7. Group by LOINC. Use the FIRST row's label / units / range as the
    //    series-level metadata (they are stable across timepoints for a
    //    given analyte by definition — same LOINC means same canonical
    //    name + unit + reference band).
    $seriesByLoinc = [];
    foreach ($rows as $row) {
        // $row is `array<mixed>` from fetchRecords; values can be any
        // SQL-driver-returned scalar/null. Narrow individual fields below.
        $loinc = $row['loinc'] ?? null;
        if (!is_string($loinc) || $loinc === '') {
            continue;
        }
        if (!isset($seriesByLoinc[$loinc])) {
            $seriesByLoinc[$loinc] = [
                'loinc' => $loinc,
                'label' => is_string($row['label'] ?? null) ? $row['label'] : 'LOINC ' . $loinc,
                'unit' => is_string($row['units'] ?? null) ? $row['units'] : '',
                'reference_range' => is_string($row['reference_range'] ?? null) ? $row['reference_range'] : '',
                'observations' => [],
            ];
        }
        $seriesByLoinc[$loinc]['observations'][] = copilot_lab_trends_parse_row($row);
    }

    // 8. Drop series that don't meet the min_observations gate. Default
    //    is 1; the widget passes 3 so the chart-axis story always has at
    //    least three points to plot.
    $series = [];
    foreach ($seriesByLoinc as $entry) {
        if (count($entry['observations']) >= $minObservations) {
            $series[] = $entry;
        }
    }

    // Stable sort: by LOINC code so the response is deterministic for
    // tests + so the widget renders tiles in the same order each load.
    usort($series, fn($a, $b): int => strcmp($a['loinc'], $b['loinc']));

    copilot_lab_trends_send_json(200, [
        'patient_uuid' => $patientUuidString,
        'series' => $series,
        'min_observations' => $minObservations,
    ]);
} catch (\RuntimeException | \PDOException | \JsonException $exc) {
    $logger->error('ClinicalCopilot lab_trends: unexpected error', [
        'exception' => $exc,
    ]);
    copilot_lab_trends_send_json(500, ['error' => 'unexpected']);
}
