---
id: AgDR-0024
timestamp: 2026-05-03T10:57:49Z
agent: Codex
model: GPT-5
trigger: User requested a Railway update runbook to bring the Clinical Co-Pilot app live on the existing vanilla OpenEMR deployment
status: proposed
---

# Railway Co-Pilot update path

> In the context of an existing Railway OpenEMR deployment that was initialized before the Co-Pilot module existed, I decided the live update path should add a private `copilot-api` Railway service from the monorepo subdirectory `agent/copilot-api`, wire OpenEMR to it with `COPILOT_API_BASE_URL` plus a shared secret, and explicitly activate the custom module in the persistent OpenEMR database. This accepts a manual one-time module activation and demo seed step to avoid rebuilding the already-working OpenEMR/MariaDB deployment. Alternatives considered: redeploy the whole stack from scratch after the Co-Pilot code exists, or expose the sidecar publicly for easier testing. A full rebuild would risk losing known-good deployment state; a public sidecar would weaken the trust-boundary story.

## Verification

- Checked the existing vanilla Railway runbook and current Co-Pilot module/sidecar code paths.
- Checked current Railway docs for private networking, monorepo root directory, build configuration, and healthchecks.
- Authored `../humanrunbooks/railway_update_app_codex_2026-05-03_bring_clinical_copilot_live.md` with the operational steps.
- This decision is `proposed` because the runbook was written but the Railway deploy was not executed in this pass.
