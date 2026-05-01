# Clinical Co-Pilot Sidecar (`copilot-api`)

Python FastAPI service that:

1. Receives source packets + a task token from the OpenEMR gateway.
2. Calls Claude (Sonnet 4.6 by default, adaptive thinking) with prompt caching on the system prompt.
3. Parses structured JSON via Pydantic (`messages.parse(output_format=LLMOutput)`).
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
    copilot-api:0.1.0
```

## Deploy to Railway

1. Create a new private service `copilot-api` (no public domain).
2. Point it at the `agent/copilot-api/` Dockerfile.
3. Env vars:
   - `ANTHROPIC_API_KEY`
   - `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET`
   - `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` (optional)
   - `COPILOT_MODEL=claude-sonnet-4-6` (override to switch model)
4. Set on the OpenEMR service:
   - `COPILOT_API_BASE_URL=http://${{copilot-api.RAILWAY_PRIVATE_DOMAIN}}:8000`
   - `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET=<same secret>`

The sidecar should have **no public domain** — only the OpenEMR service reaches it over Railway's private network.

## PHI handling

- The sidecar receives a `patient_uuid_hash` (SHA256-truncated), not a raw UUID or name.
- Source packets carry the patient's UUID for verifier patient-binding checks; this UUID never leaves the gateway → sidecar → Claude path.
- Langfuse metadata stores only the hash, packet counts, and latencies. No claim text, no source values, no patient identity.
- Set `COPILOT_ENV=production` to ensure raw model output is not stored in traces (currently never stored regardless).
