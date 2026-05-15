<?php

/**
 * Reconciles a Co-Pilot extracted medication list against the OpenEMR
 * `prescriptions` table for a given patient (Plan §6.3, AgDR-0077).
 *
 * Inputs:
 *   * The latest extracted medication-list facts for the patient's document
 *     rows in `copilot_document_facts`. The repository emits one row per
 *     medication.<slug>.<attr> field path; we group them by `<slug>` to
 *     rebuild MedicationListEntry-shaped rows.
 *   * The active prescriptions for the same patient_id.
 *
 * Output:
 *   * One row per drug name (union of both sides), classified as:
 *       - confirmed              : drug present in both sources (string match)
 *       - newly_listed           : drug only in extracted list (uploaded chart)
 *       - possibly_discontinued  : drug only in prescriptions (Rx record)
 *
 * Matching strategy (Plan §6.3 / AgDR-0077): case-insensitive, normalized
 * drug-name string match. RxNorm code matching is deferred to Wk3 — the
 * OpenEMR `prescriptions.rxnorm_drugcode` column is optional and almost
 * always empty on demo seed data; relying on it would silently regress
 * to "all newly_listed" on the demo fixtures. A future iteration can
 * upgrade to RxNorm-prefix matching without changing the public surface.
 *
 * Anti-patterns we explicitly avoid:
 *   * NO LLM-as-matcher. Boolean string match only — deterministic,
 *     testable, no API budget.
 *   * NO fuzzy substring match. "Lisinopril" must equal "Lisinopril",
 *     not "Lisinopril-HCTZ" (which is a different drug). The
 *     normalization strips punctuation and parentheticals only.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Service;

use OpenEMR\Common\Database\QueryUtils;
use Psr\Log\LoggerInterface;

final class MedicationReconciliation
{
    public const STATUS_CONFIRMED = 'confirmed';
    public const STATUS_NEWLY_LISTED = 'newly_listed';
    public const STATUS_POSSIBLY_DISCONTINUED = 'possibly_discontinued';

    public function __construct(
        private readonly LoggerInterface $logger,
    ) {}

    /**
     * Reconcile the most recent extracted medication list for `$pid` against
     * the patient's active prescriptions.
     *
     * @return array{
     *   rows: list<array{drug_name: string, extracted_dose: ?string, extracted_route: ?string, extracted_frequency: ?string, prescription_dose: ?string, prescription_route: ?string, prescription_active: ?int, status: string}>,
     *   summary: array{confirmed: int, newly_listed: int, possibly_discontinued: int, total: int},
     *   extracted_count: int,
     *   prescription_count: int,
     * }
     */
    public function reconcileForPatient(int $pid): array
    {
        $extracted = $this->loadExtractedEntries($pid);
        $prescriptions = $this->loadActivePrescriptions($pid);

        return self::buildReconciliation($extracted, $prescriptions);
    }

    /**
     * Pure-function core split out for unit-testing without a database.
     *
     * @param list<array{drug_name: string, dose: ?string, route: ?string, frequency: ?string}> $extracted
     * @param list<array{drug_name: string, dose: ?string, route: ?string, active: ?int}>      $prescriptions
     * @return array{
     *   rows: list<array{drug_name: string, extracted_dose: ?string, extracted_route: ?string, extracted_frequency: ?string, prescription_dose: ?string, prescription_route: ?string, prescription_active: ?int, status: string}>,
     *   summary: array{confirmed: int, newly_listed: int, possibly_discontinued: int, total: int},
     *   extracted_count: int,
     *   prescription_count: int,
     * }
     */
    public static function buildReconciliation(array $extracted, array $prescriptions): array
    {
        $extractedIndex = [];
        foreach ($extracted as $row) {
            $key = self::normalizeDrugName($row['drug_name']);
            if ($key === '') {
                continue;
            }
            $extractedIndex[$key] = $row;
        }
        $prescriptionIndex = [];
        foreach ($prescriptions as $row) {
            $key = self::normalizeDrugName($row['drug_name']);
            if ($key === '') {
                continue;
            }
            $prescriptionIndex[$key] = $row;
        }

        $rows = [];
        $allKeys = array_unique(array_merge(array_keys($extractedIndex), array_keys($prescriptionIndex)));
        // Deterministic ordering — alphabetical by normalized key keeps the
        // panel stable across re-uploads regardless of the original row order.
        sort($allKeys);

        $confirmed = 0;
        $newlyListed = 0;
        $possiblyDiscontinued = 0;
        foreach ($allKeys as $key) {
            $ex = $extractedIndex[$key] ?? null;
            $rx = $prescriptionIndex[$key] ?? null;
            if ($ex !== null && $rx !== null) {
                $status = self::STATUS_CONFIRMED;
                $confirmed++;
                $displayName = $ex['drug_name'];
            } elseif ($ex !== null) {
                $status = self::STATUS_NEWLY_LISTED;
                $newlyListed++;
                $displayName = $ex['drug_name'];
            } else {
                $status = self::STATUS_POSSIBLY_DISCONTINUED;
                $possiblyDiscontinued++;
                /** @var array{drug_name: string, dose: ?string, route: ?string, active: ?int} $rx */
                $displayName = $rx['drug_name'];
            }
            $rows[] = [
                'drug_name' => $displayName,
                'extracted_dose'      => $ex['dose'] ?? null,
                'extracted_route'     => $ex['route'] ?? null,
                'extracted_frequency' => $ex['frequency'] ?? null,
                'prescription_dose'   => $rx['dose'] ?? null,
                'prescription_route'  => $rx['route'] ?? null,
                'prescription_active' => isset($rx['active']) ? (int) $rx['active'] : null,
                'status'              => $status,
            ];
        }

        return [
            'rows'    => $rows,
            'summary' => [
                'confirmed'             => $confirmed,
                'newly_listed'          => $newlyListed,
                'possibly_discontinued' => $possiblyDiscontinued,
                'total'                 => count($rows),
            ],
            'extracted_count'    => count($extractedIndex),
            'prescription_count' => count($prescriptionIndex),
        ];
    }

    /**
     * Normalize a drug name for matching: lowercase, strip parentheticals
     * (e.g. "Aspirin (low-dose)" → "aspirin"), collapse whitespace, drop
     * trailing punctuation. Plan §6.3 string-match contract.
     */
    public static function normalizeDrugName(string $raw): string
    {
        $value = trim($raw);
        if ($value === '') {
            return '';
        }
        // Drop parentheticals so brand/strength notes don't break matches.
        $value = (string) preg_replace('/\([^)]*\)/', '', $value);
        // Lowercase and collapse whitespace.
        $value = (string) preg_replace('/\s+/', ' ', strtolower($value));
        // Trim residual punctuation/whitespace.
        return trim($value, " \t\n\r\0\x0B.,;");
    }

    /**
     * Load the most recent medication-list document facts for this patient's
     * document rows and reconstruct one entry per drug slug. We pick the
     * latest document_sha256 by max(created_at) so an older medication list
     * doesn't surface stale entries if the patient uploaded a fresher one.
     *
     * @return list<array{drug_name: string, dose: ?string, route: ?string, frequency: ?string}>
     */
    private function loadExtractedEntries(int $pid): array
    {
        try {
            $latestSha = QueryUtils::fetchSingleValue(
                "SELECT f.document_sha256
                 FROM copilot_document_facts AS f
                 INNER JOIN documents AS d ON d.uuid = f.document_uuid
                 WHERE d.foreign_id = ? AND f.doc_type = 'medication_list'
                 ORDER BY f.created_at DESC
                 LIMIT 1",
                'document_sha256',
                [$pid],
            );
            if (!is_string($latestSha) || $latestSha === '') {
                return [];
            }
            $rows = QueryUtils::fetchRecords(
                "SELECT f.field_path, f.field_value_json
                 FROM copilot_document_facts AS f
                 INNER JOIN documents AS d ON d.uuid = f.document_uuid
                 WHERE d.foreign_id = ? AND f.doc_type = 'medication_list' AND f.document_sha256 = ?",
                [$pid, $latestSha],
            );
        } catch (\RuntimeException | \PDOException $exc) {
            $this->logger->error('MedicationReconciliation: load extracted facts failed', [
                'exception' => $exc,
            ]);
            return [];
        }

        // Group by `<slug>` (the second segment of `medication.<slug>.<attr>`).
        // QueryUtils::fetchRecords returns list<array<mixed>> per PHPDoc;
        // is_array($row) is always true so the guard is dead.
        $bySlug = [];
        foreach ($rows as $row) {
            $path = is_string($row['field_path'] ?? null) ? $row['field_path'] : '';
            $value = self::decodeStoredFieldValue($row['field_value_json'] ?? null);
            $parts = explode('.', $path);
            // Expect ["<slug>", "<attr>"]. Older eval rows may include the
            // normalized ["medication", "<slug>", "<attr>"] prefix.
            if (count($parts) === 3 && $parts[0] === 'medication') {
                array_shift($parts);
            }
            if (count($parts) !== 2) {
                continue;
            }
            $slug = $parts[0];
            $attr = $parts[1];
            if (!isset($bySlug[$slug])) {
                $bySlug[$slug] = ['drug_name' => '', 'dose' => null, 'route' => null, 'frequency' => null];
            }
            if (in_array($attr, ['drug_name', 'dose', 'route', 'frequency'], true)) {
                $bySlug[$slug][$attr] = $value;
            }
        }

        $entries = [];
        foreach ($bySlug as $entry) {
            // $entry['drug_name'] is string|null (default '' but loop above
            // can overwrite with $value which is is_string(...) ? string : null).
            // The `?? ''` coerces null to '' so $drug is always string here;
            // the empty-string check filters both "was null" and
            // "was empty string" in one shot.
            $drug = $entry['drug_name'] ?? '';
            if ($drug === '') {
                continue;
            }
            $entries[] = [
                'drug_name' => $drug,
                'dose'      => $entry['dose'] ?? null,
                'route'     => $entry['route'] ?? null,
                'frequency' => $entry['frequency'] ?? null,
            ];
        }
        return $entries;
    }

    private static function decodeStoredFieldValue(mixed $raw): ?string
    {
        if (!is_string($raw) || $raw === '') {
            return null;
        }

        try {
            $decoded = json_decode($raw, true, flags: JSON_THROW_ON_ERROR);
        } catch (\JsonException) {
            return $raw;
        }

        if (!is_array($decoded)) {
            return is_scalar($decoded) ? (string) $decoded : null;
        }
        $value = $decoded['value'] ?? null;
        return is_scalar($value) ? (string) $value : null;
    }

    /**
     * Load active prescriptions for `$pid`. We treat `active=1` as
     * "currently prescribed"; rows with `active=0` are excluded so a long
     * historical list of discontinued prescriptions doesn't pollute the
     * `possibly_discontinued` column.
     *
     * @return list<array{drug_name: string, dose: ?string, route: ?string, active: ?int}>
     */
    private function loadActivePrescriptions(int $pid): array
    {
        try {
            $rows = QueryUtils::fetchRecords(
                'SELECT drug, dosage, route, active
                 FROM prescriptions
                 WHERE patient_id = ? AND active = 1',
                [$pid],
            );
        } catch (\RuntimeException | \PDOException $exc) {
            $this->logger->error('MedicationReconciliation: load prescriptions failed', [
                'exception' => $exc,
            ]);
            return [];
        }

        $out = [];
        foreach ($rows as $row) {
            // QueryUtils::fetchRecords returns list<array<mixed>>; is_array
            // is dead. Each $row['key'] is `mixed` — narrow per-field below.
            $drug = is_string($row['drug'] ?? null) ? $row['drug'] : '';
            if ($drug === '') {
                continue;
            }
            // $row['active'] is mixed; can be int from MySQL or string from
            // legacy code paths. is_numeric is the right narrowing here —
            // (int) cast on mixed is what PHPStan rejects at level-10.
            $activeRaw = $row['active'] ?? null;
            $active = is_numeric($activeRaw) ? (int) $activeRaw : null;
            $out[] = [
                'drug_name' => $drug,
                'dose'      => is_string($row['dosage'] ?? null) ? $row['dosage'] : null,
                'route'     => is_string($row['route'] ?? null) ? $row['route'] : null,
                'active'    => $active,
            ];
        }
        return $out;
    }
}
