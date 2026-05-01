---
id: AgDR-0002
timestamp: 2026-05-01T01:29:33Z
agent: codex
model: GPT-5
trigger: user-prompt
status: executed
---
# Wait through first-run bootstrap instead of restarting

> In the context of the OpenEMR container reporting `health: starting` and then temporarily `unhealthy`,
> I decided to monitor logs and active processes rather than restart or reset the stack,
> accepting a long first-run wait,
> to avoid interrupting dependency installation and corrupting or repeating warmed Docker volumes.
> Alternatives considered: restarting the OpenEMR container, running `docker compose down -v`, or switching to a custom compose stack.

## Consequences

- The first launch completed successfully after Composer, npm, Chromium/chromedriver, theme compilation, quick setup, XDebug installation, and Apache startup.
- Future launches should be faster because Docker volumes now contain installed dependencies and generated assets.
- The documented local runbook warns future agents that initial bootstrap can look unhealthy while still making progress.

## Verification

- OpenEMR logs progressed from `rsync` to `composer install`, `apk add`, `npm install`, theme build, quick setup, XDebug setup, and finally `Starting apache!`.
- The container eventually became healthy without manual reset.
