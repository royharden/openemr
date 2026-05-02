# Co-Pilot Eval Suite

Tests the deterministic verifier against fixed `(LLMOutput, packets)` fixtures.
Runs offline; no Anthropic API key needed.

## Run

```bash
cd agent/copilot-api
python -m evals.runner
```

Exit code: `0` on all-pass, `1` on any failure.
Result artifact: `eval_results.json` in the repo root.

## Cases

| # | Name | Tests |
|---|------|-------|
| 01 | `a1c_trend_two_sources` | trend claim with 2 source_ids passes |
| 02 | `blank_vs_negative_allergies` | "no allergies" with no negative source is dropped |
| 03 | `cross_patient_rejection` | packet from a different `patient_uuid` is dropped |
| 04 | `refusal_scope_no_recommendations` | "I recommend prescribing X" is dropped |
| 05 | `unsupported_source_id` | citation to a packet not in the request set is dropped |
| 06 | `stale_meds_must_label_freshness` | stale medication claims require a staleness caveat |
| 07 | `lists_rx_duplicate_conflict_must_be_surfaced` | duplicate list/prescription meds must be surfaced as conflicts |
| 08 | `sensitive_packet_requires_caveat` | sensitive packets require explicit caveats |
| 09 | `prompt_injection_in_packet_value` | chart text that tries to instruct the model cannot create recommendations |
| 10 | `verifier_latency_under_budget` | verifier-only latency stays inside budget |
| 11 | `allergy_conflict_surfaced_as_conflict_claim` | contradictory allergy facts can pass when surfaced as a conflict |
| 12 | `all_wrong_patient_packets_rejected` | request hash, not first packet, controls patient binding |

## Add a case

Drop a new `cases/NN_name.json` with shape:

```json
{
  "name": "...",
  "description": "...",
  "request": {
    "patient_uuid_hash": "optional sha256(patient_uuid) first 12 chars"
  },
  "packets": [/* SourcePacket[] */],
  "llm_output": {/* LLMOutput */},
  "expectations": {
    "verifier_status": "passed | passed_with_drops | failed",
    "min_accepted_claims": 1,
    "min_dropped": 1,
    "max_dropped": 0,
    "rules_must_fire": ["patient_binding"],
    "missing_data_must_mention": ["...substring..."]
  }
}
```
