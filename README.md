> **Fork:** This is a custom fork of [OpenEMR](https://github.com/openemr/openemr) developed during the [Gauntlet AgentForge](https://gauntletai.com) bootcamp. It adds a **Clinical Co-Pilot** AI module that surfaces verifier-gated patient briefings — identity, active problems, medications, allergies, recent labs, and immunizations — directly inside the OpenEMR patient chart via a Claude-powered FastAPI sidecar.
>
> **Thesis:** *A clinical agent intentionally constrained — read-only, current-patient, source-cited, verifier-gated, observable, and deployed — because in a clinical context the trustworthy 30% beats the impressive 80%.*
>
> **What the Co-Pilot does:**
> - Renders a read-only briefing card inside any patient chart, source-cited at the claim level.
> - Supports **7 first-class use cases**: pre-room brief, what changed, medication check, allergy check, recent abnormal labs, immunization history, and free-text chart follow-up.
> - LLM tool planning: the sidecar `POST /v1/tool-plan` chooses among **6 read-only tools** (`get_patient_identity`, `get_active_problems`, `get_active_medications`, `get_allergy_list`, `get_recent_labs`, `get_immunization_history`); OpenEMR executes them inside the authenticated current-patient gateway.
> - Free-text follow-up: physician can ask a chart-scoped question (e.g., *"What dose of lisinopril?"*) and gets a verifier-gated answer with click-through source chips. Clinical-action and other-patient questions are refused at the gateway before tool planning or LLM synthesis.
> - Source chip popovers: every cited claim chip opens a metadata card (table, field, observed-at, freshness) with an optional "Open record" deep-link.
> - Deterministic verifier with 11 rules (source attribution, patient binding, active-status, trend, blank-vs-negative, refusal scope, cross-patient, stale-data labeling, sensitive-data caveat, lists/prescriptions conflict surfacing) — see [agent/copilot-api/app/verifier.py](agent/copilot-api/app/verifier.py).
> - Sidecar auth: shared-secret **and** per-request HMAC task token bound to `patient_uuid_hash` (validated at the sidecar; expired tokens denied).
> - Clinician feedback chips (Helpful / Missing data / Incorrect / Too slow / Source unclear) post to Langfuse as scored trace events; `trace_id` joins to the OpenEMR `agent_turn` audit row.
> - 71/71 pytest + 34/34 eval cases passing offline (including router refusals, tool selection, tool failure, patient-override arguments, and immunization-history grounding).
>
> | Component | Location |
> |---|---|
> | OpenEMR module (PHP) | `interface/modules/custom_modules/oe-module-clinical-copilot/` |
> | AI sidecar (Python/FastAPI) | `agent/copilot-api/` |
> | Eval cases + runner | `agent/copilot-api/evals/` |
> | Demo data seed (synthetic) | [`agent/copilot-api/demo/seed_demo_patient.sql`](agent/copilot-api/demo/seed_demo_patient.sql) |
> | Project planning & architecture | `planning/` |
> | **AI Cost Analysis** (per-turn + 100 / 1K / 10K / 100K users) | [`planning/cost_analysis.md`](planning/cost_analysis.md) |
> | Audit & user docs | [`AUDIT.md`](AUDIT.md), [`planning/Users.md`](planning/Users.md) |
> | Agent work logs & decisions | `agentdocs/` |
> | Local Docker setup | `README-LOCAL-DOCKER.md` |
>
> **Deployment status:** Sidecar Dockerfile under `agent/copilot-api/Dockerfile`. Deployed URL and demo video link are pending Railway provisioning (see [`planning/plan_next01_opus47_2026-05-02_review_and_final_local_completion_status.md`](planning/plan_next01_opus47_2026-05-02_review_and_final_local_completion_status.md)).
>
> Upstream: [openemr/openemr](https://github.com/openemr/openemr) — all original OpenEMR documentation follows below.

---

[![Syntax Status](https://github.com/openemr/openemr/actions/workflows/syntax.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/syntax.yml)
[![Styling Status](https://github.com/openemr/openemr/actions/workflows/styling.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/styling.yml)
[![Testing Status](https://github.com/openemr/openemr/actions/workflows/test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/test.yml)
[![JS Unit Testing Status](https://github.com/openemr/openemr/actions/workflows/js-test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/js-test.yml)
[![PHPStan](https://github.com/openemr/openemr/actions/workflows/phpstan.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/phpstan.yml)
[![Rector](https://github.com/openemr/openemr/actions/workflows/rector.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/rector.yml)
[![ShellCheck](https://github.com/openemr/openemr/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/shellcheck.yml)
[![Docker Compose Linting](https://github.com/openemr/openemr/actions/workflows/docker-compose-lint.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/docker-compose-lint.yml)
[![Dockerfile Linting](https://github.com/openemr/openemr/actions/workflows/hadolint.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/hadolint.yml)
[![Isolated Tests](https://github.com/openemr/openemr/actions/workflows/isolated-tests.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/isolated-tests.yml)
[![Inferno Certification Test](https://github.com/openemr/openemr/actions/workflows/inferno-test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/inferno-test.yml)
[![Composer Checks](https://github.com/openemr/openemr/actions/workflows/composer.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/composer.yml)
[![Composer Require Checker](https://github.com/openemr/openemr/actions/workflows/composer-require-checker.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/composer-require-checker.yml)
[![API Docs Freshness Checks](https://github.com/openemr/openemr/actions/workflows/api-docs.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/api-docs.yml)
[![codecov](https://codecov.io/gh/openemr/openemr/graph/badge.svg?token=7Eu3U1Ozdq)](https://codecov.io/gh/openemr/openemr)

[![Backers on Open Collective](https://opencollective.com/openemr/backers/badge.svg)](#backers) [![Sponsors on Open Collective](https://opencollective.com/openemr/sponsors/badge.svg)](#sponsors)

# OpenEMR

[OpenEMR](https://open-emr.org) is a Free and Open Source electronic health records and medical practice management application. It features fully integrated electronic health records, practice management, scheduling, electronic billing, internationalization, free support, a vibrant community, and a whole lot more. It runs on Windows, Linux, Mac OS X, and many other platforms.

### Contributing

OpenEMR is a leader in healthcare open source software and comprises a large and diverse community of software developers, medical providers and educators with a very healthy mix of both volunteers and professionals. [Join us and learn how to start contributing today!](https://open-emr.org/wiki/index.php/FAQ#How_do_I_begin_to_volunteer_for_the_OpenEMR_project.3F)

> Already comfortable with git? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for quick setup instructions and requirements for contributing to OpenEMR by resolving a bug or adding an awesome feature 😊.

### Support

Community and Professional support can be found [here](https://open-emr.org/wiki/index.php/OpenEMR_Support_Guide).

Extensive documentation and forums can be found on the [OpenEMR website](https://open-emr.org) that can help you to become more familiar about the project 📖.

### Reporting Issues and Bugs

Report these on the [Issue Tracker](https://github.com/openemr/openemr/issues). If you are unsure if it is an issue/bug, then always feel free to use the [Forum](https://community.open-emr.org/) and [Chat](https://www.open-emr.org/chat/) to discuss about the issue 🪲.

### Reporting Security Vulnerabilities

Check out [SECURITY.md](.github/SECURITY.md)

### API

Check out [API_README.md](API_README.md)

### Docker

Check out [DOCKER_README.md](DOCKER_README.md)

### FHIR

Check out [FHIR_README.md](FHIR_README.md)

### For Developers

If using OpenEMR directly from the code repository, then the following commands will build OpenEMR (Node.js version 24.* is required) :

```shell
composer install --no-dev
npm install
npm run build
composer dump-autoload -o
```

### Contributors

This project exists thanks to all the people who have contributed. [[Contribute]](CONTRIBUTING.md).
<a href="https://github.com/openemr/openemr/graphs/contributors"><img src="https://opencollective.com/openemr/contributors.svg?width=890" /></a>


### Sponsors

Thanks to our [ONC Certification Major Sponsors](https://www.open-emr.org/wiki/index.php/OpenEMR_Certification_Stage_III_Meaningful_Use#Major_sponsors)!


### License

[GNU GPL](LICENSE)
