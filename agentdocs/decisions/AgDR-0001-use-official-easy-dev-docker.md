---
id: AgDR-0001
timestamp: 2026-05-01T01:29:33Z
agent: codex
model: GPT-5
trigger: user-prompt
status: executed
---
# Use official easy development Docker stack

> In the context of needing a local runnable OpenEMR instance for a brownfield course project,
> I decided to use OpenEMR's official `docker/development-easy/docker-compose.yml` stack,
> accepting a heavier multi-service local environment,
> to achieve maximum compatibility with OpenEMR's existing development and test tooling.
> Alternatives considered: creating a minimal custom OpenEMR/MariaDB compose file, reusing the Railway production runbook locally, or running PHP/MariaDB directly on Windows.

## Consequences

- Local OpenEMR runs with the same development assumptions documented by upstream OpenEMR.
- The stack includes MariaDB, phpMyAdmin, Selenium, CouchDB, OpenLDAP, and Mailpit.
- Startup is heavier than a minimal compose file but better suited to future code edits and testing.

## Verification

- `docker compose up -d` completed from `docker/development-easy`.
- `docker compose ps` showed the OpenEMR service healthy after first bootstrap.
- The OpenEMR login page loaded at `https://localhost:9300/` and `http://localhost:8300/`.
