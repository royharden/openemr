---
id: AgDR-0021
timestamp: 2026-05-03T05:01:00Z
agent: Codex
model: GPT-5
trigger: Fresh investigation of the recurring "Hepatitis A" line in the Clinical Co-Pilot brief showed the live source packet itself contained "Hepatitis A 1" even though the demo seed intended CVX code 33 to represent Pneumococcal PPSV23.
status: executed
---

# Resolve immunization packet names from CVX codes first

> In the context of the verifier correctly allowing "Hepatitis A" because it
> appeared in live packet evidence, I decided to change
> `ImmunizationsPacketBuilder` so `cvx_code` resolves through OpenEMR's CVX
> `codes` table, falling back to the custom `list_options('immunizations')`
> table only by `immunization_id`, accepting a slightly wider SQL join, to
> match OpenEMR's own immunization card and keep source packets clinically
> truthful. Alternatives considered: changing the demo seed to use a different
> list-options id, suppressing Hep A in the verifier, or treating the issue as
> stale uvicorn code.

## Context

The demo seed inserted `immunizations.cvx_code = '33'` with a note describing
Pneumococcal PPSV23. In stock OpenEMR, CVX code `33` resolves in the `codes`
table to a pneumococcal vaccine, but `list_options('immunizations')` option
`33` is the legacy custom-list label "Hepatitis A 1". The packet builder was
joining `list_options` on `i.cvx_code`, so the sidecar saw Hep A as legitimate
source evidence. The LLM was not hallucinating that entity in the live path.

## Decision

- `ImmunizationsPacketBuilder` now joins `code_types` / `codes` where
  `ct_key = 'CVX'` and `codes.code = immunizations.cvx_code`.
- The legacy custom immunization list is still supported, but only as a
  fallback keyed by `immunizations.immunization_id`.
- Title fallback order is: full CVX text, short CVX text, custom list title,
  note, `CVX <code>`, then generic `Immunization`.
- Added a CLI packet-builder smoke that runs the same builder path as
  `brief.php` against demo pid 9001 without requiring a browser session.
- Extended `validate_demo_patient.sql` with an
  `immunization_pneumococcal_count` check so the seed's intended CVX meaning is
  validated directly.

## Tradeoffs

This keeps the packet builder aligned with the existing OpenEMR UI and avoids
encoding a special-case "not Hep A" sanitizer in the verifier. The verifier
should continue to trust packet evidence; the packet evidence itself must be
correct.

## Verification

- Live packet dump before the fix showed the immunization packet value as
  "Hepatitis A 1".
- `packet_builders_smoke.php` after the fix returns one immunization packet
  with `pneumococcal polysaccharide vaccine, 23 valent`.
- `validate_demo_patient.sql` returns `immunization_pneumococcal_count=1`.
- Direct HTTP `/v1/brief` probe against restarted uvicorn with Maria's real
  packets returned no "Hepatitis" / "Hep A" text.
