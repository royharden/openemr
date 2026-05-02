---
id: AgDR-0010
timestamp: 2026-05-02T01:05:00Z
agent: codex
model: GPT-5
trigger: user-prompt (audit whether tests, evals, and observability are appropriate and improve them where needed)
status: executed
---
# Bind verifier patient checks to the request hash

> In the context of auditing the Clinical Co-Pilot eval suite,
> I decided to make the verifier compare every cited packet's `patient_uuid` hash against the request's `patient_uuid_hash`,
> accepting that sidecar fixtures and eval cases must provide or derive matching hashes,
> to ensure patient binding is based on the gateway-bound request rather than whatever packet happens to appear first.
> Alternatives considered: keep first-packet inference (simpler but misses all-wrong-patient packet sets); send raw request patient UUID to the sidecar (stronger direct comparison but expands raw identifier exposure).

## Verification

- Added unit coverage for all-wrong-patient packet sets.
- Added eval case `12_all_wrong_patient_packets.json`.
- Updated the eval runner to derive request hashes for legacy cases and accept explicit hashes for boundary cases.
- Added observability tests for PHI-minimized trace metadata, feedback scoring, and cost estimation.
- `python -m pytest tests -q` passed 29/29.
- `python -m evals.runner` passed 12/12.
