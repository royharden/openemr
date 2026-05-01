# Clinical Co-Pilot — AI Cost Analysis

**Date:** 2026-05-01
**Author:** Opus 4.7 (Claude Code)
**Scope:** Per-turn LLM cost for the Clinical Co-Pilot brief + follow-ups, projected at 100 / 1K / 10K / 100K active clinician users. Architectural deltas required at each tier so the unit economics actually hold.

> **One-line thesis:** the clinical agent is cheap *per turn* — Haiku 4.5 with prompt caching lands a verified pre-room brief at well under one cent — but the architectural cost dominates as soon as you cross the "one Postgres can't hold the audit log" line. The interesting numbers are not the LLM bill; they're what happens to Langfuse, audit storage, Railway egress, and on-call rotation.

---

## 1. Per-turn LLM cost (the easy part)

### Inputs
- **Model:** `claude-haiku-4-5-20251001` (locked in `agent/copilot-api/.env.example`; see [AgDR-0006](../agentdocs/decisions/AgDR-0006-anthropic-sdk-tool-use-and-haiku-4-5.md)).
- **Pricing (2026-05, public Anthropic rates):** Haiku 4.5 = $1.00 / 1M input tokens, $5.00 / 1M output tokens. Cache reads are 90% off input, cache writes are +25% on input.
- **Per-turn token budget (measured against current packet shape):**
  - System prompt + verifier rules block: ~900 input tokens (cached after first call).
  - Source packets (capped at 50/turn, each ~80 tokens): ~4,000 input tokens.
  - Tool schema (`emit_briefing.input_schema`): ~600 input tokens (cached).
  - Generated JSON output: ~600 output tokens.
  - Repair-once attempt fires on ~5% of calls: amortized +200 input + 400 output tokens.

### Per-turn cost (steady state, cached)
| Component | Tokens | Rate | Cost |
|---|---:|---:|---:|
| System + tool schema (cache hit) | 1,500 | $0.10 / 1M | $0.000150 |
| Packets (uncached, per-turn) | 4,000 | $1.00 / 1M | $0.004000 |
| Output JSON | 600 | $5.00 / 1M | $0.003000 |
| Repair (5% × extra 600 tokens) | 30 in + 20 out | mixed | $0.000130 |
| **Per-turn total** | | | **~$0.0073** |

Add the *first* call's cache-write penalty (~$0.0011 once per ~5-minute cache TTL, per process). For a single clinician doing 30 turns/day inside one process, the amortized warm cost is ~$0.008/turn.

### Assumed turn volume per clinician per day
- 1 pre-room brief × ~12 patients = 12.
- 1 follow-up (`what-changed`, `medication_check`, etc.) on ~50% of those = 6.
- Free-text follow-up on ~10% = 1–2.
- **Round figure: 20 turns / clinician / workday.** 220 workdays / year. Assume 2x burst for triage / nursing assist later → planning model = **40 turns / day**.

---

## 2. Projection table

All figures are LLM cost only at the per-turn rate above; *architectural* costs are layered in §3.

| Users (concurrent) | Turns / day | Turns / year | LLM-only cost / yr | LLM cost / user / mo |
|---:|---:|---:|---:|---:|
| 100 | 4,000 | 880,000 | ~$6,400 | ~$5.30 |
| 1,000 | 40,000 | 8.8M | ~$64,000 | ~$5.30 |
| 10,000 | 400,000 | 88M | ~$640,000 | ~$5.30 |
| 100,000 | 4M | 880M | ~$6.4M | ~$5.30 |

Reality check: $5–6/clinician/month for the LLM is below the price of any clinical SaaS line item. The interesting cliff is what surrounds it — see next section.

---

## 3. Architectural deltas at each tier

### Tier 1 — 100 users
- **Architecture:** current. One Railway sidecar, Anthropic direct API, Langfuse Cloud free tier, OpenEMR `audit_master` table, no Redis.
- **Bottlenecks:** none. Langfuse free tier (50K observations/mo) covers 100 × 30/day × 22 days ≈ 66K — already over the free tier *if every turn is one observation*. At 100 users you're on the $59/mo Langfuse Pro plan.
- **Adds vs. baseline:** Langfuse Pro $59/mo, Railway sidecar ~$10/mo, Anthropic ~$530/mo. Total infra ~$600/mo.
- **Per user / month all-in:** ~$6.

### Tier 2 — 1,000 users
- **What breaks first:** OpenEMR's `audit_master` writes. At 40K turns/day each one writes a row — single-instance MariaDB starts contending around 5–10 audit rows/sec sustained. Acceptable here, but plan a partitioning pass.
- **Architecture deltas:**
  - Add **Redis (or Railway KV)** in front of the gateway for cache-context (last brief per `pid`) so a quick re-render doesn't recompute packets. Redis costs ~$15/mo at this scale.
  - Bump sidecar to 2 replicas behind a private health-checked load balancer for zero-downtime deploys.
  - Switch Langfuse to self-hosted Postgres-backed instance (~$30/mo VM + $20/mo storage), or stay on Langfuse Team ($499/mo). Self-host wins here.
  - Begin streaming `agent_turn` audit rows to S3-compatible cold storage nightly; keep last 90 days hot in MariaDB.
- **New costs:** +$50–600/mo depending on Langfuse choice. Anthropic ~$5,300/mo.
- **Per user / month all-in:** ~$6.

### Tier 3 — 10,000 users
- **What breaks:** Anthropic per-account rate limits (RPM). Even at Tier 4 enterprise contract, 400K turns/day is 4.6 turns/sec mean and ~30/sec p95 (peak hospital-day mornings). Need batched calls.
- **Architecture deltas:**
  - **Move repair-pass to the Anthropic Batch API** (≥50% off output rates, 24h SLA). Repair is non-real-time anyway.
  - Negotiate **provisioned throughput** for the live brief path; price drops ~30% on input.
  - Self-host Langfuse on Kubernetes (3-node cluster, ClickHouse storage, ~$1,200/mo).
  - Audit log moves to a dedicated MariaDB cluster (read replica + binlog → S3 → Athena) since clinical compliance now has 10+ year retention requirements.
  - Add a **packet-cache layer** (Redis) keyed by `(patient_uuid, packet_builder_version, last_touch_ts)` so unchanged packets aren't re-built every turn. Cuts gateway DB load ~70%.
  - Add a **regional sidecar** in each cloud region the EHR runs in. Cross-region private networking on Railway / GCP / AWS.
  - Hire / rotate **on-call engineer** ($150K/yr loaded) — this is the dominant cost at this tier.
- **New infra costs:** +$2K–4K/mo. Anthropic ~$53K/mo (with batching + provisioned discount: ~$38K). On-call: $150K/yr fully loaded.
- **Per user / month all-in:** ~$5.50.

### Tier 4 — 100,000 users
- **What breaks:** trust + audit + procurement, not the model.
- **Architecture deltas:**
  - **Self-hosted LLM inference** for the `medication_check` and `allergy_check` paths (Llama-class fine-tune on de-identified packets). Anthropic stays on `pre_room_brief` and `what-changed` because clinical reasoning matters most there. This is the single biggest unit-cost lever — drops Anthropic spend by ~60%.
  - **Per-tenant prompt caching** with Anthropic 1-hour cache (1h beta); each hospital's prompt prefix lives separately to keep PHI boundaries clean.
  - **Two-region active/active** Anthropic routing with explicit failover to Sonnet 4.6 if Haiku 4.5 latency p95 exceeds budget.
  - Audit log goes to **append-only object storage with object-lock** (regulatory write-once requirement). Hot/warm/cold tiering, query-via-Athena.
  - Langfuse becomes a secondary observability source; primary clinical-trace store is a HIPAA-BAA'd vendor (Datadog-with-PHI-tier or in-house).
  - **BAA team + compliance officer** dedicated to the AI surface.
  - **Red-team rotation** quarterly (prompt injection, jailbreak, source-citation forgery).
- **New costs:** Anthropic ~$2.5M/yr after self-hosted offload, +$1.5M/yr inference cluster (GPU pool), +$1M/yr for compliance / on-call / red-team. Storage ~$200K/yr.
- **Per user / month all-in:** ~$4.50.

---

## 4. Sensitivity — what kills these numbers

| Lever | Sensitivity | Mitigation |
|---|---|---|
| Output tokens | Linear, output is 5x input rate | Cap claim count at 6, claim text at 200 chars (already enforced at prompt + schema level). |
| Repair-pass frequency | Each percentage point ≈ +$0.0001/turn | Tighten schema upfront; the verifier already drops on second failure rather than retrying again. |
| Cache miss rate | First-call penalty is +25% on the prefix | Keep sidecar workers warm; aim for ≥80% cache hit rate (current measurement: 0%, no production traffic yet). |
| Note RAG / vector DB (v2) | Adds ~3K input tokens/turn → +$0.003/turn | Out of scope for v1 by design. When added, gate behind a feature flag and run cost A/B. |
| Batch repair adoption | Each 10pp shift to batch ≈ -2% on output cost | Move all `what-changed` repair to batch first; brief repair stays interactive. |

---

## 5. Numbers we still need from production

These are the genuinely uncertain inputs. The figures above are bounded by the assumption that they land near the median, which is exactly what production should validate before the Tier 2 architectural delta is real money.

- Actual median + p95 packet count per turn (we cap at 50, but real distributions will shift the 4,000-token estimate).
- Repair-pass rate (5% is a guess — could be 1% with a tighter schema or 15% if Haiku 4.5 struggles with edge packets).
- Cache hit rate at steady state (need warm-worker telemetry from Langfuse).
- Real follow-up frequency per clinician (the 50% `what-changed` assumption has zero evidence yet).
- Audit-row write latency under sustained load (the Tier 2 partitioning trigger).

A two-week canary at one clinic gets us all five — and converts this document from estimate to forecast.
