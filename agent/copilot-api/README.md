# Clinical Co-Pilot Sidecar (`copilot-api`)

Python FastAPI service that:

1. Receives source packets + a task token from the OpenEMR gateway.
2. Calls Claude with tool-use-forced structured output; Week 2 document
   extraction and graph synthesis default to `claude-sonnet-4-6`.
3. Parses the tool payload through Pydantic (`LLMOutput.model_validate(...)`).
4. Runs the deterministic verifier (8 rules).
5. Optionally repairs once.
6. Emits Langfuse spans (PHI-safe metadata only).
7. Returns the verified response.

The sidecar **never holds MariaDB credentials** and never receives raw patient names. Everything it sees is what the gateway hands it.

## Run locally

```bash
cd openemr/agent/copilot-api
pip install -e .

export ANTHROPIC_API_KEY=sk-ant-...
export COPILOT_OPENEMR_GATEWAY_SHARED_SECRET=$(openssl rand -hex 32)
export COPILOT_VISION_MODEL=claude-sonnet-4-6
export COPILOT_SYNTHESIS_MODEL=claude-sonnet-4-6
# optional
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`GET /healthz` → `{"status":"ok"}`.

## Run evals (offline, no API key)

```bash
python -m evals.runner
```

Exit `0` on all-pass.

## Wire into OpenEMR gateway

Set on the OpenEMR PHP host:

```text
COPILOT_API_BASE_URL=http://copilot-api:8000
COPILOT_OPENEMR_GATEWAY_SHARED_SECRET=<same as sidecar>
```

The gateway includes them in the request headers; the sidecar's `auth.py` rejects anything without a matching secret.

## Build the Docker image

```bash
docker build -t copilot-api:0.1.0 .
docker run --rm -p 8000:8000 \
    -e ANTHROPIC_API_KEY \
    -e COPILOT_OPENEMR_GATEWAY_SHARED_SECRET \
    -e COPILOT_VISION_MODEL=claude-sonnet-4-6 \
    -e COPILOT_SYNTHESIS_MODEL=claude-sonnet-4-6 \
    copilot-api:0.1.0
```

## Deployment Scope

Week 2 is local-Docker only. Railway redeploy/configuration is intentionally out
of scope for this sprint; run the sidecar beside the Docker OpenEMR stack and
point OpenEMR at `http://host.docker.internal:8000`.

## PHI handling

- The sidecar receives a `patient_uuid_hash` (SHA256-truncated), not a raw UUID or name.
- Source packets carry the patient's UUID for verifier patient-binding checks; this UUID never leaves the gateway → sidecar → Claude path.
- Langfuse metadata stores only the hash, packet counts, and latencies. No claim text, no source values, no patient identity.
- Set `COPILOT_ENV=production` to ensure raw model output is not stored in traces (currently never stored regardless).

---

## Week 2 Setup

### Installation: `sqlite-vec` Embedded Vectors

Wk2 uses **sqlite-vec** for hybrid retrieval (BM25 + dense embeddings). Install via `pyproject.toml` and pre-compile the C extension:

**macOS (Intel/Apple Silicon):**
```bash
pip install -e .
# sqlite-vec 0.1.6 wheels pre-built; no compilation needed
```

**Linux (Ubuntu 22.04+):**
```bash
sudo apt-get install -y build-essential python3.11-dev
pip install -e .
```

**Windows (via WSL2 or native):**
```powershell
# From PowerShell in openemr/agent/copilot-api/ directory
pip install -e .
# Wheels available; if compilation needed:
#   choco install visualstudio2022-workload-nativedesktop
```

Verify installation:
```bash
python -c "from sqlite_vec import sqlite_vec; print('sqlite-vec OK')"
```

### Vendor Configuration

**Voyage API (embeddings fallback):**
- Key: `VOYAGE_API_KEY=pa-...`
- Fallback: OpenAI `text-embedding-3-small` (requires `OPENAI_API_KEY`).
- Wk2 default: Voyage (faster, cheaper).

**Cohere Rerank (retrieval reranking, fallback available):**
- Key: `COHERE_API_KEY=cohere_...`
- Fallback: Local cross-encoder model (slower, no API call).
- Wk2 default: Cohere (better ranking quality).

**OpenFDA API (drug label corpus):**
- Key: `OPENFDA_API_KEY=<32-char string>`
- Endpoint: `https://api.fda.gov/drug/label.json`
- Rate limit: 240 req/min × 120k req/day (sufficient for Wk2).

**Deterministic Eval Mode:**
- Set `COPILOT_EVAL_MODE=1` in `.env` to mock all vendor calls.
- Voyage → deterministic hash-based embedding.
- Cohere → deterministic score based on keyword overlap.
- Allows full 50-case eval suite to run offline, fast, reproducible.
- Real vendor APIs tested nightly in `.github/workflows/eval-gate-live.yml`.

### Corpus Refresh

The RAG corpus is built once and stored at `agent/copilot-api/corpus.db`:

```bash
# Wk2: Build corpus (idempotent, ~5 min)
COPILOT_EVAL_MODE=1 python scripts/build_corpus.py --corpus-path corpus.db

# Output: corpus.db (sqlite3; CDC ACIP + openFDA + HMS-LOE chunks)
# Chunks indexed by source_year, grade, organization for efficient retrieval.

# Future (Wk3): Add refresh cadence
# - CDC ACIP: weekly (check last-modified-date)
# - openFDA: monthly (new drug approvals)
# - HMS Library: as-needed
```

Runtime behavior:
- `COPILOT_RAG_CORPUS_PATH` overrides the default `corpus.db` location.
- If `corpus.db` is present, `/v1/rag/retrieve` uses the SQLite/BM25/vector corpus.
- If it is absent, local dev falls back to deterministic built-in chunks.
- Set `COPILOT_RAG_REQUIRE_CORPUS=1` to make startup and retrieval fail fast when the corpus is unavailable.

### Endpoints (Week 2 New)

**`POST /v1/extract/lab-pdf`**
- Extract structured facts from lab PDF.
- Input: multipart/form-data with `patient_uuid`, `document_file`, `document_sha256`.
- Output: `ExtractedDocument` with `LabResult` + source packets (bbox, quote, page).
- Vision model: Claude Sonnet 4.6.
- Uses pdfplumber for deterministic text-match bbox (no hallucination).

**`POST /v1/extract/intake-form`**
- Extract demographics, chief concern, medications, allergies from intake form (PDF/PNG/JPEG).
- Input: multipart/form-data with `patient_uuid`, `document_file`, `document_sha256`.
- Output: `ExtractedDocument` with `IntakeFields` + source packets.
- For image-only inputs (no text layer), bbox=null (allowed).

**`POST /v1/rag/retrieve`**
- Hybrid retrieval: BM25 + Voyage dense + Cohere rerank.
- Input: `{"query": "...", "top_k": 5}`.
- Output: top-5 `GuidelineChunk` packets (source_year, grade, organization, quote).

**`POST /v1/copilot/answer`**
- Full agent: intake extraction + evidence retrieval + synthesis + verification.
- Input: `{"use_case": "...", "patient_uuid_hash": "...", "packets": [...], "question": "..."}`
- Output: `VerifiedResponse` (claims, refusals, missing_data, verifier_status, issues).
- LLM: Claude Haiku 4.5 (synthesis).

### Testing & Eval

**Unit tests (L1):**
```bash
pytest app/extractors/test_lab_pdf.py -v
pytest app/extractors/test_intake_form.py -v
pytest app/rag/test_retriever.py -v
```

**Integration tests (L2):**
```bash
pytest tests/integration/test_routes.py -v
```

**E2E smoke (L3, pre-push):**
```bash
bash scripts/run_eval_gate.sh --smoke
```

**Full eval (L4, CI):**
```bash
bash scripts/run_eval_gate.sh --full
```

**Live smoke (L5, nightly):**
```bash
# Runs in GitHub Actions; same 10 cases with real Anthropic/Voyage/Cohere APIs
# Reports latency + cost metrics to Langfuse
```

### Startup Self-Test

On container start, `app/startup.py` runs `validate_provider_credentials()`:
- Tests Anthropic API key (dummy Haiku request).
- Tests Voyage API key (dummy embedding).
- Tests Cohere API key (dummy rerank).
- Fails fast if any key is missing or invalid; sidecar returns 503 `/healthz` until fixed.
- Prevents runtime surprises during eval runs.

---
