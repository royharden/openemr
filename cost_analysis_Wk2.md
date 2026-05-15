# Week 2 Cost Analysis: Multimodal Evidence Agent

**Date:** 2026-05-10
**Period:** Wk2 development (2026-05-09 to 2026-05-10, sprint)
**Scope:** Per-turn + projected production cost
**Currency:** USD

---

## 1. Development Spend (Actual, Sprint)

### Anthropic API (Vision + Synthesis)

| Use Case | Model | Avg Tokens | Calls | Rate | Cost |
|----------|-------|-----------|-------|------|------|
| Lab PDF extraction | Sonnet 4.6 vision | 800 in / 400 out | 18 | $3.00/$15.00 | $0.048 |
| Intake form extraction | Sonnet 4.6 vision | 1200 in / 300 out | 18 | $3.00/$15.00 | $0.081 |
| Evidence synthesis | Haiku 4.5 | 2000 in / 400 out | 50 | $0.80/$4.00 | $0.100 |
| Tool planning (fallback) | Haiku 4.5 | 800 in / 200 out | 5 | $0.80/$4.00 | $0.008 |
| **Subtotal** | — | — | 91 | — | **$0.237** |

**Notes:**
- Lab/intake extraction tested with 18 eval case documents (mix of clean + scanned + handwritten).
- Synthesis tested across 50 golden eval cases (single-turn, no repair loops).
- Tool planning fallback only triggered when gateway planning fails (rare).

### Voyage Embeddings (Dense Retrieval)

| Use Case | Tokens | Calls | Rate | Cost |
|----------|--------|-------|------|------|
| Query embedding (retrieval) | 50 | 50 | $0.02 / 1k | $0.001 |
| Corpus indexing (one-time) | ~2M | 1 | $0.02 / 1k | $0.040 |
| **Subtotal** | — | 51 | — | **$0.041** |

**Notes:**
- Query embeddings: ~50 tokens per evidence retrieval (Wk2 has 8 RAG eval cases + optional live queries).
- Corpus indexing (CDC ACIP + openFDA drug labels): one-time cost, amortized across prod lifetime.

### Cohere Reranking (Hybrid RAG)

| Use Case | Docs | Calls | Rate | Cost |
|----------|------|-------|------|------|
| Rerank candidate chunks | 20 → 5 | 50 | $0.001 per doc | $0.001 |
| **Subtotal** | — | — | — | **$0.001** |

**Notes:**
- Cohere charges per document reranked, not per query. We score 20 candidates down to 5 (conservative estimate).
- Only triggered on RAG-enabled use cases (Wk2: 8 cases + optional queries).

### OpenFDA API (Corpus Building, One-Time)

| Component | Calls | Rate | Cost |
|-----------|-------|------|------|
| Drug label fetch (25 high-freq drugs) | 25 | Free (public) | $0.00 |

**Notes:**
- OpenFDA API is free (rate-limited to 240 req/min, sufficient).
- Drug label corpus built once; no per-turn cost.

### Langfuse (Observability)

| Activity | Volume | Cost |
|----------|--------|------|
| Trace ingestion (50 eval cases) | ~50 traces | ~$0 (free tier: 10k/mo) |
| **Subtotal** | — | **$0.00** |

**Notes:**
- Free tier covers 10k trace events/month; Wk2 uses ~50 for eval run.
- Production: $29/mo for 100k events/mo + unlimited traces (sufficient for 100 users).

### **Wk2 Development Total: ~$0.28 USD**

Breakdown:
- Anthropic (vision + synthesis): $0.237 (84%)
- Voyage (embeddings): $0.041 (15%)
- Cohere (rerank): $0.001 (<1%)
- Langfuse (traces): $0.00 (free tier)

---

## 2. Per-Turn Production Cost (Estimate)

Baseline: Single physician interaction (one question + evidence retrieval + answer).

### Typical Turn: Free-Text Follow-Up

**Flow:**
1. Clinician attaches lab PDF (extraction) OR asks question (no extraction).
2. Gateway executes read-only tools (6 tools, ~10 tool calls).
3. Sidecar retrieves evidence (RAG: query embedding + rerank).
4. Sidecar synthesizes brief (Haiku synthesis).
5. Sidecar verifies output (deterministic verifier, no LLM cost).

**Costs:**

| Step | Model | Tokens | Cost |
|------|-------|--------|------|
| Lab PDF extraction (if attached) | Sonnet 4.6 | 800 in / 400 out | $0.0032 |
| Evidence retrieval (BM25 + Voyage embed) | Voyage | 50 | $0.001 |
| Reranking (20 → 5 chunks) | Cohere | 20 × $0.001 | $0.02 |
| Synthesis (brief + tool results) | Haiku 4.5 | 2000 in / 400 out | $0.0018 |
| **Per-Turn Total (with extraction)** | — | — | **$0.0060** |
| **Per-Turn Total (no extraction)** | — | — | **$0.0028** |

**Assumptions:**
- 50% of turns include document extraction; 50% are question-only.
- Average extraction: 1 document × Sonnet 4.6 vision.
- Average retrieval: 1 query + 20 candidate chunks + 5 reranked results.
- Average synthesis: 2k input tokens (packets + evidence + prompt) + 400 output tokens.
- Verifier cost: $0 (deterministic Python, no LLM).
- No repair loops (verifier accepts 95%+ of claims on first pass).

**Average per turn:** $(0.0060 + 0.0028) / 2 = **$0.0044 USD**

---

## 3. Projected Production Cost (Scaled)

Assumptions:
- 1 FTE physician using Co-Pilot: ~30 turns/day × 250 work days = **7,500 turns/year**.
- 100 FTE physicians: **750k turns/year**.
- 1,000 FTE physicians: **7.5M turns/year**.

### Cost at Scale

| Scale | Turns/Year | API Cost | Langfuse | Total/Year | Per Turn |
|-------|-----------|----------|----------|-----------|----------|
| **1 physician** | 7,500 | $33 | $0 | **$33** | $0.0044 |
| **10 physicians** | 75,000 | $330 | $29 | **$359** | $0.0048 |
| **100 physicians** | 750,000 | $3,300 | $29 | **$3,329** | $0.0044 |
| **1,000 physicians** | 7,500,000 | $33,000 | $348 | **$33,348** | $0.0044 |

**Notes:**
- Langfuse cost: $29/mo (100k events) for 1–100 physicians; $348/mo (1M events) for 1k physicians.
- Anthropic volume pricing may apply at 1M+ tokens/month (negotiate with sales).
- Cohere reranking cost remains <1% at all scales.
- Voyage embedding cost is minimal (~$2.5k/year at 1M turns).

---

## 4. Comparison to Alternative Architectures

### Local Extraction (No Vision API)

**Alternative:** Use local OCR (e.g., tesseract + form field detection).

**Cost savings:** -$0.003/turn (no Sonnet vision).
**Trade-off:**
- 30–50% lower accuracy on messy/scanned documents.
- Adds ~2–3 sec latency (local compute).
- Increases maintenance burden (new OCR models, fallback logic).
- **Not recommended for clinical context** (Wk2 uses Sonnet for accuracy).

### Cloud RAG (No SQLite-Vec)

**Alternative:** Pinecone, Weaviate, or other managed vector DB.

**Cost:**
- Pinecone starter: $30/mo + $0.025 per 1M vectors/month.
- Weaviate cloud: $50/mo + compute.
- At 15k chunks × 1k calls/month: **~$50–100/month baseline**.

**Trade-off:**
- SQLite-vec is embedded (free), but requires local disk (~50 MB for corpus).
- Pinecone scales better for 100k+ chunks.
- **Wk2 uses SQLite-vec for simplicity** (corpus small enough for single container).

### LLM-as-Judge (Eval)

**Alternative:** Use Claude to evaluate each case (instead of boolean rubrics).

**Cost:**
- 50 cases × 1k tokens/eval = $0.04 per eval run.
- Weekly regression runs: $0.04 × 4 = **$0.16/month**.

**Trade-off:**
- LLM judges are expensive (~0.1¢/case) + slow (5–10 sec/case).
- Boolean rubrics are deterministic, fast (<1 sec/case), and reproducible.
- **Wk2 uses boolean rubrics** (AgDR-0035).

---

## 5. Sensitivity Analysis

**Cost drivers (Wk2 production, 100 physicians):**

| Variable | ±10% Impact | Notes |
|----------|-------------|-------|
| Extraction frequency | ±$330 | If 50% vs 60% of turns include extraction |
| Synthesis token count | ±$165 | 2000 vs 2200 input tokens (evidence quantity) |
| Retrieval candidate set | ±$33 | 20 vs 25 chunks before reranking |
| Voyage embedding cost | ±$3 | Minor contributor (<1%) |

**Largest cost lever:** Extraction frequency. If only 30% of turns use extraction (question-only brief), per-turn cost drops to **$0.0035**.

---

## 6. Billing & Cost Controls

### Monthly Forecast (100 physicians, conservative)

```
Anthropic:  ~$275    (vision + synthesis)
Voyage:     ~$2.5    (embeddings)
Cohere:     ~$0.75   (reranking)
Langfuse:   ~$29     (observability)
─────────────────────
Total:      ~$307/month
```

### Cost Controls (Production)

1. **Rate limiting:** API keys configured to 240 req/min (Cohere, Voyage, OpenFDA).
2. **Caching:** Frequently asked evidence queries cached in sqlite-vec (no re-embedding).
3. **Batching:** Corpus refresh batched weekly (not per-turn).
4. **Fallbacks:** Local cross-encoder replaces Cohere if rate-limited; OpenAI replaces Voyage if down.
5. **Monitoring:** Langfuse traces cost estimates; alerts if per-turn cost exceeds $0.01.

---

## 7. Conclusion

**Wk2 production cost is sub-cent per clinical interaction** ($0.0044 USD average), dominated by Anthropic vision API for extraction. At typical EHR scale (100–1000 physicians), annual cost ranges from $33k–$333k, comfortably within clinical IT budgets. Local SQLite-vec + deterministic verifier keep operational complexity low and cost predictable.

---

## 8. Latency Profile (real Langfuse data)

> **Status:** populated from a live 50-turn sidecar canary on 2026-05-12.
> The canary used synthetic non-PHI packets against `/v1/brief`, with
> `COPILOT_EVAL_MODE` unset, Langfuse enabled, and immediate flush enabled.

### 8.1 Methodology

1. The Docker OpenEMR stack was already healthy; the sidecar was started locally from `agent/copilot-api` with Langfuse credentials loaded from `.env`, `COPILOT_EVAL_MODE` unset, `COPILOT_REQUIRE_TASK_TOKEN=0`, and `COPILOT_LANGFUSE_FLUSH_IMMEDIATE=1`.
2. Startup self-test was skipped for this run because the self-test hung before the HTTP server bound; the live canary requests themselves were still non-eval vendor calls.
3. A 50-turn synthetic canary posted directly to `/v1/brief` using three non-PHI source packets (LDL, atorvastatin, penicillin allergy) and a mix of pre-room and free-text follow-up prompts.
4. The canary result was 50/50 HTTP 200: 36 `passed`, 14 `passed_with_drops`, 0 failed.
5. Langfuse confirmed the newest traces as `clinical_copilot.brief` with `brief_v1` observations. The helper was then run as:

   ```bash
   # from the openemr/ project root, with the agent venv active
   python agentdocs/latency_percentiles.py --trace-name clinical_copilot.brief --n 50
   ```

   The script reads `LANGFUSE_*` from the environment, pulls the most recent N traces named `clinical_copilot.brief`, reads `brief_v1` observation `duration_ms`, and emits the markdown tables below. It exits non-zero with a clear message if credentials are missing or no traces are found, so it is safe to wire into a smoke job.

6. The production gateway path uses `/v1/brief` for synthesis and cost telemetry. It currently emits one `brief_v1` observation per turn, not per-node `intake_extractor` / `evidence_retriever` / `synthesizer` / `verifier` spans. Per-node graph spans therefore remain `n/a` for this production-path canary; adding per-node `/v1/brief` spans would be a future observability enhancement.

### 8.2 Per-node latency (ms)

| Metric | intake_extractor | evidence_retriever | synthesizer | verifier |
|--------|------------------|--------------------|-------------|----------|
| p50    | n/a              | n/a                | n/a         | n/a      |
| p95    | n/a              | n/a                | n/a         | n/a      |
| n      | 0                | 0                  | 0           | 0        |

This canary used the production `/v1/brief` endpoint, which records a single
`brief_v1` observation. The older graph endpoint can emit `clinical_copilot.graph`
traces, but it is not the cost-bearing gateway path and does not currently
emit token/cost metadata.

### 8.3 End-to-end latency (ms)

| Metric | Value |
|--------|-------|
| p50    | 3,078 |
| p95    | 4,952 |
| n      | 50    |

### 8.4 Per-sample cost (USD)

| Metric | Value |
|--------|-------|
| Total cost across sample | $0.2758 |
| Mean cost per trace      | $0.005515 |
| Sample size              | 50 |

### 8.5 Bottleneck identification

For the production `/v1/brief` synthesis path, the observed p95 is under 5
seconds and the dominant cost/latency source is the live Anthropic briefing
generation. This canary did not include document extraction or native OpenEMR
browser/page load time, so it should be read as the sidecar synthesis budget,
not the full upload-and-writeback demo budget.

The next observability improvement is to emit explicit child spans inside
`process_brief()` for LLM generation and deterministic verification. That
would make `/v1/brief` per-step latency visible without relying on the older
graph endpoint.

---

**End of Cost Analysis**
