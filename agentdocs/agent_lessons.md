# Agent Lessons

This file captures reusable lessons, surprises, and environment-specific pitfalls discovered by agents. Future agents should append new lessons under "Entries" with a UTC timestamp, agent/model, short title, impact, and recommended handling.

Rules for future entries:
- Keep lessons practical and reusable.
- Include exact commands, paths, or symptoms when they help the next agent.
- Do not include PHI, private secrets, or noisy logs.
- If a lesson changes a durable project direction, also create an Agent Decision Record in `agentdocs/decisions/`.

## Entries

### 2026-05-01T~18:00Z - Claude Code / claude-sonnet-4-6 - This repo has two remotes; always push to both after every commit

Impact: The project is published simultaneously to GitHub (`origin`, `https://github.com/royharden/openemr`) and Gauntlet GitLab (`gauntlet`, `https://labs.gauntletai.com/royharden/openemr`). Pushing to only one leaves the other stale, which matters because the Gauntlet evaluation environment reads from GitLab.

Recommended handling: After every `git commit` sequence, run both pushes:
```bash
git push origin master && git push gauntlet master
```
There is also a `gitlab` remote pointing to the same GitLab URL — this is a duplicate and can be ignored; `gauntlet` is canonical. See AgDR-0007 for the decision record.

### 2026-04-30T23:55:00Z - Claude Code / claude-opus-4-7 - `messages.parse()` and top-level `cache_control=` don't exist in the Anthropic Python SDK

Impact: The previously written `app/llm.py` called `client.messages.parse(output_format=LLMOutput, cache_control={"type":"ephemeral"})`. Neither symbol exists in `anthropic==0.46.0` (and pyproject pinned an `anthropic>=0.92` version that doesn't exist on PyPI either). The whole sidecar was therefore non-functional against a real key — it would fail on the first call. The issue was masked because the only smoke path was the offline `evals.runner` (which imports the verifier directly and never hits the LLM).

Recommended handling: For structured output in current SDKs, use `client.messages.create(...)` with `tools=[{ "name": ..., "input_schema": MyModel.model_json_schema() }]` and `tool_choice={"type":"tool","name":...}`, then `MyModel.model_validate(block.input)` on the `tool_use` content block. `cache_control` belongs on individual content blocks (or not at all on older Haiku models), not as a top-level kwarg. Add at least one *live* smoke test (e.g. `smoke_test.py`) so the next agent doesn't ship a non-callable LLM path.

### 2026-04-30T23:55:00Z - Claude Code / claude-opus-4-7 - Older Haiku model IDs return 404 from the issued API key

Impact: The user asked for "Haiku 3" to minimize cost. `claude-3-haiku-20240307` returned `not_found_error`. `claude-3-5-haiku-20241022` also returned `not_found_error`. `claude-haiku-4-5-20251001` worked. Likely cause: this account / API contract no longer routes to retired model IDs. Don't blindly accept "use the cheapest old model" — confirm the model is callable on *this* key before locking it in.

Recommended handling: When the user asks for a specific model that may be retired, run a one-line probe (`client.messages.create(model=ID, max_tokens=1, messages=[{"role":"user","content":"ping"}])`) and fall back upward (Haiku 3 → 3.5 → 4.5 → Sonnet) until you get a 200. Document the chosen model in `.env.example` so the substitution isn't silent.

### 2026-04-30T23:55:00Z - Claude Code / claude-opus-4-7 - `dotenv.load_dotenv()` won't override an empty-string env var inherited from the shell

Impact: A parent shell that exports `ANTHROPIC_API_KEY=` (empty) defeats `load_dotenv()` because dotenv treats "already set" as "leave it alone" by default. Symptom: the `.env` is correct, `find_dotenv()` returns it, `load_dotenv()` returns `True`, and `os.getenv("ANTHROPIC_API_KEY")` is still `""`.

Recommended handling: After the first `load_dotenv()`, check whether the target keys are non-empty; if any are empty strings, call `load_dotenv(override=True)`. This is the pattern used in `agent/copilot-api/app/llm.py`.

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - Custom modules require a row in the `modules` table

Impact: Dropping a module folder under `interface/modules/custom_modules/` is not enough — `ModulesApplication::bootstrapCustomModules()` only loads custom modules that have a row in the `modules` table with `mod_active = 1` and `type = 0` (custom, not Laminas). Without the row the bootstrap.php is silently skipped.

Recommended handling: Insert a row before testing module load, e.g.:
```sql
INSERT INTO modules
(mod_name, mod_directory, mod_parent, mod_type, mod_active, mod_ui_name,
 mod_relative_link, mod_ui_order, mod_ui_active, mod_description, mod_nick_name,
 mod_enc_menu, directory, date, sql_run, type, sql_version, acl_version)
VALUES
('Clinical Co-Pilot', 'oe-module-clinical-copilot', '', '', 1, 'Clinical Co-Pilot',
 '', 0, 1, 'Read-only AI co-pilot embedded in patient chart', 'copilot', 'no',
 'oe-module-clinical-copilot', NOW(), 1, 0, '0', '0');
```
Also: `dev-reset-install-demodata` truncates the modules table — re-insert after every reset.

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - `CsrfUtils::verifyCsrfToken` signature is `(token, session, subject)`, not `(token, subject)`

Impact: `CsrfUtils::verifyCsrfToken($csrf, 'ClinicalCopilot')` looks like it should work but throws — the second positional argument is a `SessionInterface`, not the subject. Mirror `CsrfUtils::collectCsrfToken($session, 'ClinicalCopilot')` (subject is the trailing arg in both, but the session arg is mandatory in `verifyCsrfToken`).

Recommended handling: always pass the active session: `CsrfUtils::verifyCsrfToken($csrf, $session, 'ClinicalCopilot')`.

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - mariadb client (not `mysql`) inside the Dockerized DB

Impact: `docker compose exec mysql mysql ...` returns `executable file not found in $PATH`. The image (`mariadb:11.8.6`) ships with `mariadb` but not the `mysql` symlink.

Recommended handling: use `docker compose exec mysql mariadb -uroot -proot openemr -e "..."`. Same flags, same SQL.

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - Brief gateway path traversal: 5 `../` from `public/api/brief.php` to globals

Impact: Custom-module ajax endpoints under `public/` need `require_once(__DIR__ . "/../../../../globals.php")` (4 `../`). One nested deeper at `public/api/brief.php` needs **5** `../`. Off-by-one breaks the include silently.

Recommended handling: count the path: `public/api/brief.php` → `public/` → `oe-module-.../` → `custom_modules/` → `modules/` → `interface/` → `globals.php` = 5 `../`.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - First Docker bootstrap is slow on Windows/OneDrive

Impact: The first `docker compose up -d` from `docker/development-easy` took a long time before OpenEMR served requests. The slow phases were repository sync, Composer install, Chromium/chromedriver installation, npm install, theme compilation, and ownership changes over the mounted tree.

Recommended handling: Do not assume the container is broken merely because OpenEMR is temporarily `unhealthy` during first bootstrap. Watch `docker compose logs --tail 200 openemr` and `docker compose exec -T openemr sh -lc "ps -o pid,etime,time,stat,comm,args | head"` to distinguish progress from a real stall. Avoid `docker compose down -v` unless intentionally resetting all warmed volumes.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - OpenEMR health JSON can be stricter than login readiness

Impact: `https://localhost:9300/meta/health/readyz` returned HTTP 200, but the JSON body included `status: setup_required` with `oauth_keys: false` even after Docker marked OpenEMR healthy and the login page worked.

Recommended handling: For local UI readiness, verify the login page and an `admin` / `pass` login flow. For API/OAuth work, revisit OAuth key/client generation separately before treating the API surface as ready.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - OAuth client helper did not produce usable credentials yet

Impact: Running `docker compose exec -T openemr /root/devtools register-oauth2-client` returned `client id: null` and `client secret: null`.

Recommended handling: Do not rely on Swagger/API OAuth testing until the OAuth keys/client registration path has been checked. The UI is runnable, but API validation needs a separate setup pass.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - Official easy-dev stack starts more than just OpenEMR

Impact: The local development stack also starts MariaDB, phpMyAdmin, Selenium, CouchDB, OpenLDAP, and Mailpit. This is heavier than a minimal app/database compose, but it matches OpenEMR's development tooling.

Recommended handling: Keep this as the default for brownfield development unless there is a clear reason to create a smaller task-specific compose file.
