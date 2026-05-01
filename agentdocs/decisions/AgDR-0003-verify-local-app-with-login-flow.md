---
id: AgDR-0003
timestamp: 2026-05-01T01:29:33Z
agent: codex
model: GPT-5
trigger: user-prompt
status: executed
---
# Verify local readiness with the login flow

> In the context of a health endpoint returning HTTP 200 but reporting `setup_required` in its JSON body,
> I decided to verify local app readiness with the actual OpenEMR login page and default credentials,
> accepting that API/OAuth readiness remains a separate follow-up,
> to confirm the UI is runnable for upcoming brownfield edits.
> Alternatives considered: treating `/meta/health/readyz` as the sole readiness signal, or blocking local setup until OAuth client registration succeeded.

## Consequences

- The local UI is considered ready for browser-based development and testing.
- API/Swagger/OAuth testing should be checked separately before API-specific work.
- The local Docker README distinguishes UI readiness from the stricter health/OAuth checks.

## Verification

- `https://localhost:9300/` redirected to `interface/login/login.php?site=default` and returned the OpenEMR login page.
- Posting `admin` / `pass` returned a redirect to `/interface/main/tabs/main.php`.
- `docker compose ps` showed `development-easy-openemr-1` healthy.
