<?php

/**
 * Deterministic keyword router for free-text follow-up questions.
 *
 * Routes a normalized question string to (a) a router family, (b) the set
 * of packet builders to run, and (c) optionally a local refusal reason
 * that short-circuits the sidecar call.
 *
 * Letting the LLM pick which OpenEMR data to access is the dangerous path;
 * keyword-routed bundles is the safe Week-1 move. Precedence: refuse_*
 * families short-circuit first (cheaper than a sidecar round-trip and
 * removes the risk of the LLM ignoring its system prompt). After that,
 * topical families before the catch-all. See AgDR-0011.
 *
 * Pure function: no DB access, no I/O, no globals. Easy to unit test.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Gateway;

final class QuestionRouter
{
    public const FAMILY_MEDICATION = 'medication';
    public const FAMILY_ALLERGY = 'allergy';
    public const FAMILY_LABS = 'labs';
    public const FAMILY_IMMUNIZATION = 'immunization';
    public const FAMILY_WHAT_CHANGED = 'what_changed';
    public const FAMILY_IDENTITY = 'identity';
    public const FAMILY_FALLBACK = 'fallback_chart_question';
    public const FAMILY_REFUSE_CLINICAL_ACTION = 'refuse_clinical_action';
    public const FAMILY_REFUSE_OTHER_PATIENT = 'refuse_other_patient';

    public const BUILDERS_FULL = [
        'identity',
        'problems',
        'meds',
        'allergies',
        'labs',
        'immunizations',
    ];

    /**
     * Normalize a raw question:
     *  - trim
     *  - normalize whitespace runs
     *  - strip ASCII control characters (kept readable & loggable)
     *  - cap to 500 chars
     */
    public static function normalize(string $question): string
    {
        $q = (string)preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $question);
        $q = (string)preg_replace('/\s+/u', ' ', $q);
        $q = trim($q);
        if (function_exists('mb_substr')) {
            return (string)mb_substr($q, 0, 500);
        }
        return substr($q, 0, 500);
    }

    /**
     * Classify a normalized question.
     *
     * @return array{family: string, builders: array<int, string>, refusal_reason: string|null}
     */
    public static function classify(string $normalizedQuestion): array
    {
        $q = strtolower($normalizedQuestion);

        if ($q === '') {
            return [
                'family' => self::FAMILY_FALLBACK,
                'builders' => self::BUILDERS_FULL,
                'refusal_reason' => 'empty_question',
            ];
        }

        // 1. Other-patient guard (must precede topical families - "John Smith's meds"
        //    is a medication question, but we still refuse it).
        if (self::matches($q, [
            '/\b(other|another)\s+patient\b/',
            '/\bpatient\s+[a-z]+\s+[a-z]+\b/',
            '/\b(?:john|jane|mary|robert|maria)\s+(?:smith|doe|jones|garcia|brown)\b/',
        ])) {
            return [
                'family' => self::FAMILY_REFUSE_OTHER_PATIENT,
                'builders' => [],
                'refusal_reason' => 'other_patient_request',
            ];
        }

        // 2. Clinical-action refusal — recommendations, ordering, treatment changes.
        if (self::matchesAny($q, [
            'should i ',
            'should we ',
            'recommend',
            'prescribe',
            'order ',
            'diagnose',
            'start her on',
            'start him on',
            'stop ',
            'discontinue',
            'increase',
            'decrease',
            'taper',
        ])) {
            return [
                'family' => self::FAMILY_REFUSE_CLINICAL_ACTION,
                'builders' => [],
                'refusal_reason' => 'clinical_action_out_of_scope',
            ];
        }

        // 3. Topical families — order matters; check more specific terms first.
        if (self::matchesAny($q, [
            'allergy', 'allergic', 'reaction to', 'penicillin', 'nkda',
        ])) {
            return [
                'family' => self::FAMILY_ALLERGY,
                'builders' => ['identity', 'allergies', 'meds'],
                'refusal_reason' => null,
            ];
        }

        if (self::matchesAny($q, [
            'vaccine', 'vaccination', 'shot', 'immuniz', 'tetanus',
            'pneumococcal', 'flu shot', 'covid shot',
        ])) {
            return [
                'family' => self::FAMILY_IMMUNIZATION,
                'builders' => ['identity', 'immunizations'],
                'refusal_reason' => null,
            ];
        }

        if (self::matchesAny($q, [
            'lab', 'a1c', 'ldl', 'hdl', 'creatinine', 'abnormal',
            'result', 'value', 'panel', 'cbc', 'tsh',
        ])) {
            return [
                'family' => self::FAMILY_LABS,
                'builders' => ['identity', 'problems', 'labs'],
                'refusal_reason' => null,
            ];
        }

        if (self::matchesAny($q, [
            'metformin', 'lisinopril', 'dose', 'dosage', 'refill', 'fill',
            'adherence', 'medication', ' med ', ' meds', 'pill', 'rx',
        ])) {
            return [
                'family' => self::FAMILY_MEDICATION,
                'builders' => ['identity', 'meds', 'allergies'],
                'refusal_reason' => null,
            ];
        }

        if (self::matchesAny($q, [
            'changed', 'new since', 'last visit', 'since march',
            'since april', 'anything new', 'what has changed', 'whats new',
        ])) {
            return [
                'family' => self::FAMILY_WHAT_CHANGED,
                'builders' => self::BUILDERS_FULL,
                'refusal_reason' => null,
            ];
        }

        if (self::matchesAny($q, [
            'age', 'sex', 'name', 'dob', 'date of birth', 'gender',
        ])) {
            return [
                'family' => self::FAMILY_IDENTITY,
                'builders' => ['identity'],
                'refusal_reason' => null,
            ];
        }

        return [
            'family' => self::FAMILY_FALLBACK,
            'builders' => self::BUILDERS_FULL,
            'refusal_reason' => null,
        ];
    }

    /**
     * @param array<int, string> $regexes
     */
    private static function matches(string $haystack, array $regexes): bool
    {
        foreach ($regexes as $re) {
            if (preg_match($re, $haystack) === 1) {
                return true;
            }
        }
        return false;
    }

    /**
     * @param array<int, string> $needles
     */
    private static function matchesAny(string $haystack, array $needles): bool
    {
        foreach ($needles as $needle) {
            if (str_contains($haystack, $needle)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Build a sidecar-shaped local refusal response so the UI render path stays unified.
     *
     * @return array<string, mixed>
     */
    public static function buildRefusalResponse(
        string $traceId,
        string $family,
        string $reason,
    ): array {
        $message = match ($family) {
            self::FAMILY_REFUSE_CLINICAL_ACTION =>
                "I can't make treatment recommendations. Review the chart and your protocol; "
                . "I can summarize the data the chart already contains.",
            self::FAMILY_REFUSE_OTHER_PATIENT =>
                "I can only answer about the patient currently open in this chart.",
            default => "I can't answer that here.",
        };

        return [
            'trace_id' => $traceId,
            'answer_type' => 'refusal',
            'claims' => [],
            'missing_data' => [],
            'refusals' => [$message],
            'suggested_followups' => [],
            'verifier_status' => 'refused_by_router',
            'unsupported_dropped' => 0,
            'router_family' => $family,
            'router_refusal_reason' => $reason,
        ];
    }
}
