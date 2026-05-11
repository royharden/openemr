<?php

/**
 * Pure-function helpers + AmbiguousDobException for the demo-mode
 * intake-create endpoint (AgDR-0066 + AgDR-0068).
 *
 * Extracted from create_patient_from_intake.php so the Phase 2.6
 * smoke can require this file without firing the endpoint's
 * request-handling code (which calls `exit` via copilot_create_send_json
 * after the demo-mode gate check). The endpoint file requires this
 * helpers file at top-of-file and uses the helpers below; no behavior
 * change.
 *
 * Same namespace as the endpoint (`OpenEMR\Modules\ClinicalCopilot\Api\Internal`)
 * so calls remain unqualified inside the endpoint.
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @author    Roy Harden <royhardenre@gmail.com>
 * @copyright Copyright (c) 2026 Roy Harden
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Api\Internal;

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Common\Database\QueryUtils;
use OpenEMR\Common\Uuid\UuidRegistry;

/**
 * @param array<string, mixed> $payload
 */
function copilot_create_send_json(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

/**
 * Pluck the first matching demographic value from a sidecar fields list.
 *
 * Intake extractors emit field_path under various conventions: bare names
 * ("first_name"), "intake."-prefixed, "demographics."-prefixed, or
 * "intake.demographics."-prefixed. We try all of them in order.
 *
 * @param list<array<string, mixed>> $fields
 * @param list<string> $candidatePaths
 */
function copilot_create_pluck_field(array $fields, array $candidatePaths): ?string
{
    foreach ($candidatePaths as $candidate) {
        foreach ($fields as $field) {
            $name = $field['name'] ?? null;
            if (!is_string($name) || strtolower($name) !== strtolower($candidate)) {
                continue;
            }
            $value = $field['value'] ?? null;
            if (is_string($value) && $value !== '') {
                return trim($value);
            }
            if (is_int($value) || is_float($value)) {
                return (string) $value;
            }
        }
    }
    return null;
}

/**
 * Extract a {fname, lname, DOB, sex, address...} array from a sidecar
 * intake-form ExtractedDocument payload.
 *
 * Returns the partial demographics — caller validates completeness.
 *
 * @param array<string, mixed> $payload
 * @return array<string, string|null>
 */
function copilot_create_demographics_from_extract(array $payload): array
{
    $result = $payload['result'] ?? [];
    $rawFields = is_array($result) ? ($result['fields'] ?? []) : [];
    /** @var list<array<string, mixed>> $fields */
    $fields = [];
    if (is_array($rawFields)) {
        foreach ($rawFields as $f) {
            if (!is_array($f)) {
                continue;
            }
            $entry = [];
            foreach ($f as $k => $v) {
                if (is_string($k)) {
                    $entry[$k] = $v;
                }
            }
            $fields[] = $entry;
        }
    }

    return [
        'fname' => copilot_create_pluck_field($fields, [
            'first_name', 'fname',
            'demographics.first_name', 'demographics.fname',
            'intake.first_name', 'intake.fname',
            'intake.demographics.first_name', 'intake.demographics.fname',
        ]),
        'lname' => copilot_create_pluck_field($fields, [
            'last_name', 'lname',
            'demographics.last_name', 'demographics.lname',
            'intake.last_name', 'intake.lname',
            'intake.demographics.last_name', 'intake.demographics.lname',
        ]),
        'DOB' => copilot_create_pluck_field($fields, [
            'date_of_birth', 'dob', 'DOB', 'birthdate',
            'demographics.date_of_birth', 'demographics.dob',
            'intake.date_of_birth', 'intake.dob',
            'intake.demographics.date_of_birth', 'intake.demographics.dob',
        ]),
        'sex' => copilot_create_pluck_field($fields, [
            'sex', 'gender',
            'demographics.sex', 'demographics.gender',
            'intake.sex', 'intake.gender',
            'intake.demographics.sex', 'intake.demographics.gender',
        ]),
        'phone_home' => copilot_create_pluck_field($fields, [
            'phone', 'phone_home', 'home_phone',
            'demographics.phone', 'demographics.phone_home',
            'intake.phone', 'intake.demographics.phone',
        ]),
        'email' => copilot_create_pluck_field($fields, [
            'email', 'demographics.email',
            'intake.email', 'intake.demographics.email',
        ]),
        'street' => copilot_create_pluck_field($fields, [
            'street', 'address',
            'demographics.street', 'demographics.address',
            'intake.street', 'intake.demographics.street',
        ]),
        'city' => copilot_create_pluck_field($fields, [
            'city',
            'demographics.city', 'intake.city', 'intake.demographics.city',
        ]),
        'state' => copilot_create_pluck_field($fields, [
            'state', 'state_code',
            'demographics.state', 'intake.state', 'intake.demographics.state',
        ]),
        'postal_code' => copilot_create_pluck_field($fields, [
            'postal_code', 'zip', 'zipcode',
            'demographics.postal_code', 'demographics.zip',
            'intake.postal_code', 'intake.demographics.postal_code',
        ]),
    ];
}

/**
 * Thrown by copilot_create_normalize_dob when the raw DOB parses validly
 * as BOTH m/d/Y and d/m/Y AND the two interpretations yield different
 * dates. Caller surfaces a 422 with both candidates so the operator can
 * clarify rather than the parser silently picking one (Plan §4.1, audit
 * finding #16).
 */
final class AmbiguousDobException extends \RuntimeException
{
    /**
     * @param list<string> $candidates ISO YYYY-MM-DD strings, one per
     *                                 valid interpretation.
     */
    public function __construct(public readonly array $candidates)
    {
        parent::__construct('ambiguous_dob');
    }
}

/**
 * Coerce a raw DOB string to OpenEMR's "Y-m-d" shape. Accepts ISO,
 * unambiguous wordy formats, and (strict-mode) numeric formats.
 *
 * Plan §4.1 (audit finding #16): the previous implementation tried
 * m/d/Y before d/m/Y in a fall-through loop, silently coercing
 * "05/03/1962" to May 3 even when a European-handwritten intake meant
 * March 5. The permissive \DateTimeImmutable fallback compounded the
 * silent-coercion risk. Replaced with an explicit ambiguity check:
 *
 *   1. Y-m-d ISO first — unambiguous.
 *   2. Wordy English ("Aug 14, 1962" / "August 14, 1962") — unambiguous.
 *   3. d-m-Y (dash-separated European) — strict (must round-trip).
 *   4. Numeric slash forms: try BOTH m/d/Y AND d/m/Y; if both parse and
 *      yield distinct dates, throw AmbiguousDobException so the caller
 *      can 422 with both candidates.
 *
 * Returns null when no parser matches — caller surfaces "insufficient
 * demographics" so the operator can correct the form rather than
 * accepting a silently wrong date.
 *
 * @throws AmbiguousDobException when the raw value parses as both
 *                                m/d/Y AND d/m/Y with different results.
 */
function copilot_create_normalize_dob(?string $raw): ?string
{
    if ($raw === null || trim($raw) === '') {
        return null;
    }
    $trimmed = trim($raw);

    // 1. ISO Y-m-d first — unambiguous.
    $iso = \DateTime::createFromFormat('Y-m-d', $trimmed);
    if ($iso instanceof \DateTime && $iso->format('Y-m-d') === $trimmed) {
        return $iso->format('Y-m-d');
    }

    // 2. Wordy English ("Aug 14, 1962" / "August 14, 1962") — unambiguous.
    foreach (['M j, Y', 'F j, Y'] as $wordyFormat) {
        $dt = \DateTime::createFromFormat($wordyFormat, $trimmed);
        if ($dt instanceof \DateTime && $dt->format($wordyFormat) === $trimmed) {
            return $dt->format('Y-m-d');
        }
    }

    // 3. d-m-Y (dash-separated European) — explicit enough to accept.
    $dashEu = \DateTime::createFromFormat('d-m-Y', $trimmed);
    if ($dashEu instanceof \DateTime && $dashEu->format('d-m-Y') === $trimmed) {
        return $dashEu->format('Y-m-d');
    }

    // 4. Numeric slash forms — try BOTH conventions and surface ambiguity.
    //    A value like "05/03/1962" is May 3 (US) or March 5 (EU); we cannot
    //    pick safely without operator input.
    $usDt = \DateTime::createFromFormat('m/d/Y', $trimmed);
    $usValid = $usDt instanceof \DateTime && $usDt->format('m/d/Y') === $trimmed;
    $euDt = \DateTime::createFromFormat('d/m/Y', $trimmed);
    $euValid = $euDt instanceof \DateTime && $euDt->format('d/m/Y') === $trimmed;

    if ($usValid && $euValid) {
        $usIso = $usDt->format('Y-m-d');
        $euIso = $euDt->format('Y-m-d');
        if ($usIso !== $euIso) {
            throw new AmbiguousDobException([$usIso, $euIso]);
        }
        return $usIso; // Both conventions agree (e.g. "12/12/1962").
    }
    if ($usValid) {
        return $usDt->format('Y-m-d');
    }
    if ($euValid) {
        return $euDt->format('Y-m-d');
    }

    // Permissive \DateTimeImmutable fallback intentionally REMOVED per
    //    Plan §4.1 audit finding #16. A handwritten intake form whose DOB
    //    none of the strict parsers handle should surface as
    //    "insufficient_demographics" so the operator can correct it,
    //    rather than silently coercing into a probable-wrong date.
    return null;
}

/**
 * Look up an existing demo-intake patient by its deterministic-from-SHA
 * usertext1 tag. Returns [pid, patient_uuid_string] on hit, null on miss.
 *
 * AgDR-0068: closes audit finding #4 — the demo-intake patient row's
 * usertext1 is computed deterministically from the intake document SHA
 * (`wk2-demo-intake-<8-char-SHA>`), so two uploads of the same fixture
 * always resolve to the same usertext1 value. A pre-insert SELECT on
 * that value lets us return the existing pid + uuid on the second
 * upload rather than colliding on `patient_data.pubpid UNIQUE` and
 * surfacing a 500. Best-effort: any DB error is logged at WARNING and
 * treated as a miss so the caller falls through to the normal insert
 * path (which will then surface the real DB error from PatientService).
 *
 * @return array{0: int, 1: string}|null  [pid, patient_uuid_string] or null on miss
 */
function copilot_create_lookup_existing_patient_by_usertext1(string $usertext1): ?array
{
    try {
        $rows = QueryUtils::fetchRecords(
            'SELECT pid, uuid FROM patient_data WHERE usertext1 = ? LIMIT 1',
            [$usertext1],
        );
        if (count($rows) === 0) {
            return null;
        }
        $row = $rows[0];
        $pidRaw = $row['pid'] ?? null;
        $uuidBin = $row['uuid'] ?? null;
        if (!is_numeric($pidRaw)) {
            return null;
        }
        if (!is_string($uuidBin) || strlen($uuidBin) !== 16) {
            return null;
        }
        return [(int) $pidRaw, UuidRegistry::uuidToString($uuidBin)];
    } catch (\RuntimeException | \PDOException $exc) {
        ServiceContainer::getLogger()->warning(
            'ClinicalCopilot: duplicate-intake usertext1 lookup failed (treating as miss)',
            ['exception' => $exc],
        );
        return null;
    }
}

/**
 * Normalize a sex/gender string into a single token PatientService accepts.
 */
function copilot_create_normalize_sex(?string $raw): string
{
    if ($raw === null || trim($raw) === '') {
        return 'Unknown';
    }
    $t = strtolower(trim($raw));
    return match (true) {
        $t === 'm' || str_starts_with($t, 'mal') => 'Male',
        $t === 'f' || str_starts_with($t, 'fem') => 'Female',
        default => 'Unknown',
    };
}
