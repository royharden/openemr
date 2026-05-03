---
id: AgDR-0013
timestamp: 2026-05-02T15:45:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: Plan slice 4 from plan_next01_opus47_2026-05-02_review_and_final_local_completion.md — close the source-chip drill-down defensibility gap that Codex flagged.
status: executed
---

# Source-chip drill-down via gateway-supplied packets_summary

> In the context of source citation being load-bearing for clinical trust but
> chips today rendering only the opaque `source_id` string,
> I decided to ship a click-to-popover that surfaces packet metadata
> (table, label, observed_at, freshness) plus an optional "Open record"
> deep-link, and have the gateway return a `packets_summary` array alongside
> the verified response so the UI never has to guess,
> accepting that the deep-link is best-effort (only fires for a curated allowlist
> of `source_table` → OpenEMR record path mappings),
> to achieve verifiable provenance without reaching into raw packet `value`
> fields (which can carry sensitive content).

## Decision detail

- Gateway response gains `packets_summary: [{source_id, source_table, label,
  observed_at, freshness}]`. PHI-bounded — no `value`, no `comments`.
- `copilot.js` replaces the old static `<span class="copilot-source-chip">`
  with a clickable/keyboard-focusable element that opens a popover. The
  popover dismisses on the next document click, supports `Enter`/`Space`,
  and reads metadata from a per-turn cache populated from `packets_summary`.
- Deep-link allowlist (`POPOVER_RECORD_PATHS` in `copilot.js`): `lists`,
  `prescriptions`, `lists_allergy`, `procedure_result`, `procedure_order`,
  `immunizations`. Other source tables show metadata only.

## Verification

- PHP `php -l` clean on `brief.php` (now emits `packets_summary`).
- Manual JS check via the rendered panel; pytest suite still 41/41.
