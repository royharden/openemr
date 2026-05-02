---
id: AgDR-0009
timestamp: 2026-05-01T23:00:00Z
agent: claude-code
model: claude-sonnet-4-6
trigger: user-prompt (activate Langfuse with real credentials; user signed up for Hobby/free account)
status: executed
---
# Langfuse Cloud (US) activated with dev credentials

> In the context of the Langfuse integration being fully code-complete but missing credentials,
> I decided to add the three Langfuse env vars to `agent/copilot-api/.env` using the user's Hobby-tier Cloud account on the US region,
> accepting that 30-day retention and 50 k observations/month are the ceiling (well above demo volume),
> to achieve end-to-end trace visibility in Langfuse Cloud for the Week-1 submission demo.
> Alternatives considered: self-host Langfuse on Railway (adds a service, unnecessary for demo volume); use EU Cloud endpoint (wrong — account is US region; EU endpoint returns auth errors).

## Key facts

- Langfuse project: **EMR-SO** (org: REH)
- Cloud region: **US** — host `https://us.cloud.langfuse.com`
- Public key: stored in `agent/copilot-api/.env` (gitignored); never committed in full
- Secret key: stored in `agent/copilot-api/.env` (gitignored); never committed
- Credential source file: `LANGFUSE_KEY_DEV.txt` at repo root (outside `openemr/`, not tracked by git)
- Tier: **Hobby (free)** — sufficient for demo; see tradeoffs below

## Hobby tier vs paid

| Feature | Hobby (free) | Pro (~$59/mo) |
|---|---|---|
| Observations/month | 50,000 | Higher limits / pay-per-use |
| Data retention | 30 days | 90 days |
| Projects | 1 | Multiple |
| Team RBAC | No | Yes |
| SSO | No | Yes |
| Support | Community | Email |

**Verdict:** Hobby is more than enough for this class demo. At ~2 observations per brief (trace + generation), the 50 k limit supports ~25,000 briefs/month. Demo traffic will be in the hundreds.

## Critical env-var naming note

The Langfuse Cloud UI `.env` snippet uses `LANGFUSE_BASE_URL`. The Langfuse **Python SDK v3** and the project's `observability.py` read `LANGFUSE_HOST`. These are the same value; only the variable name differs by client. Always use `LANGFUSE_HOST` in this project's `.env`.

## Verification

- `.env` updated; sidecar reads the three vars at startup via `observability._get_client()`.
- With all three vars set, `_get_client()` returns a live `Langfuse` instance pointing at `us.cloud.langfuse.com`.
- Next manual verification: start the sidecar locally and POST a brief; confirm a trace appears in the Langfuse Cloud dashboard.
