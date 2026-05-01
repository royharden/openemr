# OpenEMR Codebase Agent Map v2

Generated from local inspection of `openemr/` on 2026-04-30. Scope was limited to `openemr/` and its subdirectories.

This v2 started from `openemr-codebase-agent-map.v1.md` and was reviewed against `OPENEMR_ARCHITECTURE.v1.md`. Useful verified guidance from that document was merged here. Stale, inaccurate, or overly broad claims from that document were intentionally not carried forward.

This document is written for follow-on agents that need to understand where behavior lives before making changes. OpenEMR is not one uniform framework application. It is a long-lived PHP EHR/practice-management system with a legacy procedural UI, legacy Smarty controllers, Composer-loaded namespaced services, Symfony HTTP/event components, a Laminas module bridge, REST/FHIR/OAuth2 entrypoints, and installable custom modules.

## Quick Mental Model

OpenEMR is an electronic health record and practice-management application. The core product covers patient demographics, scheduling, encounters, clinical forms, documents, prescriptions, billing/claims, reporting, patient portal access, APIs, FHIR/SMART, CCDA/CCR, ACLs, user/facility setup, and extension modules.

The most important split is:

- Legacy browser UI: most pages are direct PHP scripts under `interface/` and shared procedural libraries under `library/`.
- Modern PHP classes: namespaced code under `src/`, autoloaded as `OpenEMR\`.
- APIs: `apis/dispatch.php`, `oauth2/authorize.php`, and route maps in `apis/routes/`.
- Module system: Laminas modules under `interface/modules/zend_modules/module/` plus custom modules under `interface/modules/custom_modules/`.
- Per-site state: database config, documents, images, LBF plugins, and custom menu files under `sites/<site_id>/`.

The single most important legacy bootstrap is `interface/globals.php`. Any browser-facing script that includes it gets session/site setup, database connection, globals from the `globals` table, site config, auth checks, modules, audit logging, paths, and translation setup.

Default agent posture: add new business logic in `src/` when feasible, and keep legacy `interface/` or `library/` edits thin. Legacy patterns are often runtime reality, not examples to copy.

## Review Delta From Other Agent Doc

Helpful items imported into v2:

- Added a concise development posture: new code belongs in `src/`, while legacy pages should usually delegate to modern services.
- Added verified local Docker quick-start and devtool command references.
- Added a coding standards section based on `CLAUDE.md`, including strict types, typed globals access, QueryUtils, PSR-3 logging, CSRF/ACL discipline, and PHPStan rule tripwires.
- Expanded the service-layer notes with verified `BaseService` behavior.
- Strengthened the Doctrine migrations warning from `db/README.md`: migrations exist, but are not yet the primary schema-change path.
- Added a reference-docs section so follow-on agents know where repo-native guidance lives.

Items not imported because they were wrong or not safe for this checkout:

- `controller.php` was described as a modern router to `src/Controllers/*`; in this checkout it dispatches to the legacy Smarty `Controller` whitelist in `library/classes/Controller.class.php`.
- A root `modules/` directory was listed, but this checkout uses `interface/modules/zend_modules/` and `interface/modules/custom_modules/`; no top-level `openemr/modules` directory exists.
- `src/Encounter` was listed, but this checkout has no such namespace directory.
- The other doc described `ccdaservice/` as a Node service; this was not verified from the inspected files and is not included.
- Claims that all legacy DB access ultimately routes through Doctrine DBAL were not included; legacy SQL helpers currently create/use an ADODB connection via OpenEMR's compatibility connection factory.
- The other doc treated Doctrine migrations as the normal new schema path. Current repo docs say Doctrine migrations are not fully integrated and should not be used for normal DB changes yet.

## Runtime Request Flow

### Root Entry

`index.php` selects a site id from `?site=`, `HTTP_HOST`, or `default`, validates it, loads `sites/<site_id>/sqlconf.php`, then redirects:

- Installed site: `interface/login/login.php?site=<site_id>`
- Unconfigured site: `setup.php?site=<site_id>`

`sites/default/sqlconf.php` currently has default DB settings and `$config = 0`, so this checkout appears uninstalled until setup modifies that file.

### Legacy UI Bootstrap

Most UI scripts include `interface/globals.php`. That file:

- Loads Composer autoload.
- Checks PHP compatibility.
- Loads `.env` if present.
- Creates logger and exception handler.
- Computes filesystem and web paths (`fileroot`, `webroot`, `srcdir`, `rootdir`, `OE_SITE_DIR`, `OE_SITE_WEBROOT`).
- Sets up the active site from session or `?site=`.
- Opens the database through `library/sql.inc.php`.
- Loads `version.php`.
- Pulls settings from the `globals` table and user overrides from `user_settings`.
- Loads site-specific `sites/<site_id>/config.php`.
- Includes `library/auth.inc.php` unless `$ignoreAuth` or portal-specific bypass flags are set.
- Loads the module system through `OpenEMR\Core\ModulesApplication` if the `modules` table exists.
- Logs HTTP requests through `EventAuditLogger`.
- Returns `OpenEMR\Core\OEGlobalsBag`.

Follow-on agents should assume that legacy scripts depend on global variables even when a newer typed wrapper exists. `OEGlobalsBag` mirrors values into `$GLOBALS` for compatibility.

### Front Controller

`public/index.php` is a newer front controller. It loads `bootstrap.php`, builds a PSR-7 request, and delegates to `OpenEMR\BC\FallbackRouter`.

`FallbackRouter` supports modern front-controller deployment while preserving direct-file semantics. It rewrites key prefixes:

- `/apis` -> `apis/dispatch.php`
- `/oauth2` -> `oauth2/authorize.php`
- `/meta/health` -> `meta/health/index.php`
- `/portal/patient` -> `portal/patient/index.php`
- `/interface/modules/zend_modules/public` -> `interface/modules/zend_modules/public/index.php`

For non-rewritten paths it resolves a real file, blocks sensitive directories (`config`, `db`, `docker`, `sql`, `src`, `tests`, `vendor`, dotfiles, templates, site documents), returns `null` for a small set of static asset extensions, mutates `$_SERVER['SCRIPT_FILENAME']`, `SCRIPT_NAME`, `PHP_SELF`, changes working directory, and includes the legacy file.

### REST, FHIR, OAuth2, SMART

`apis/dispatch.php` and `oauth2/authorize.php` both create `OpenEMR\Common\Http\HttpRestRequest` and run `OpenEMR\RestControllers\ApiApplication`.

`ApiApplication` creates a Symfony `OEHttpKernel` and registers subscribers in this order:

- `ExceptionHandlerListener`
- `TelemetryListener`
- `ApiResponseLoggerListener`
- `SessionCleanupListener`
- `SiteSetupListener`
- `CORSListener`
- `OAuth2AuthorizationListener`
- `AuthorizationListener`
- `RoutesExtensionListener`
- `ViewRendererListener`

Routes are set in `_rest_routes.inc.php`:

- Standard API: `apis/routes/_rest_routes_standard.inc.php`, 96 route entries.
- FHIR R4 US Core 3.1.0: `apis/routes/_rest_routes_fhir_r4_us_core_3_1_0.inc.php`, 71 route entries.
- Portal API: `apis/routes/_rest_routes_portal.inc.php`, 5 route entries.

OAuth2/OpenID Connect/SMART behavior is mainly in `src/RestControllers/AuthorizationController.php`, `src/RestControllers/SMART/`, `src/Common/Auth/OpenIDConnect/`, and `src/FHIR/SMART/`.

### Legacy Smarty Controller

`controller.php` includes `interface/globals.php`, instantiates `library/classes/Controller.class.php`, and dispatches either explicit routing (`?controller=document&action=...`) or legacy positional routing (`?document&list&...`).

The controller whitelist maps these legacy controller names to files in `controllers/`:

- `document` -> `C_Document.class.php`
- `document_category` -> `C_DocumentCategory.class.php`
- `hl7` -> `C_Hl7.class.php`
- `insurance_company` -> `C_InsuranceCompany.class.php`
- `insurance_numbers` -> `C_InsuranceNumbers.class.php`
- `patient_finder` -> `C_PatientFinder.class.php`
- `pharmacy` -> `C_Pharmacy.class.php`
- `practice_settings` -> `C_PracticeSettings.class.php`
- `prescription` -> `C_Prescription.class.php`
- `x12_partner` -> `C_X12Partner.class.php`

Controller output uses Smarty templates under `templates/`.

### Patient Portal

Patient portal code lives under `portal/`, with the richer portal application under `portal/patient/`. The front controller rewrites `/portal/patient` to `portal/patient/index.php`. Portal-specific API routes are in `apis/routes/_rest_routes_portal.inc.php`, and portal services live in `src/Services/PatientPortalService.php` and `src/Services/PatientAccessOnsiteService.php`.

### CLI

`bin/console` is the newer Symfony Console entrypoint. It loads Composer, optionally supports `--skip-globals`, otherwise sets `$_GET['site']`, includes `interface/globals.php` with `$ignoreAuth = true`, then runs `OpenEMR\Common\Command\SymfonyCommandRunner`.

Available Symfony command classes are under `src/Common/Command/`, including ACL modification, background services, CCDA import, document import, API documentation generation, access token generation, API test client registration, email test, and release changelog generation.

`bin/command-runner` is an older custom command runner.

## Dependency And Build Stack

Primary metadata:

- PHP: `composer.json` requires PHP `>=8.2.0`.
- Node: `package.json` requires Node `>=24.0.0`.
- Version: `version.php` reports `8.1.1-dev`, database version `538`, ACL version `13`.

Important PHP libraries:

- ADODB for legacy MySQL access.
- Doctrine DBAL/ORM/Migrations for newer data access and migration work.
- Symfony HTTP Kernel, Console, Event Dispatcher, DI, Finder, Process, Cache, Yaml.
- Laminas MVC/Form/Router/ServiceManager for the module bridge.
- Twig 3 and Smarty 4 plus legacy Smarty compatibility.
- league/oauth2-server and OpenID Connect classes for SMART/OAuth2.
- Monolog, Guzzle, PHPMailer, Dompdf/mpdf/rospdf, PhpSpreadsheet, Flysystem.

Important JS/UI libraries:

- Bootstrap 4.6, Bootswatch, jQuery, jQuery UI.
- DataTables, Select2, Font Awesome, Chart.js, CKEditor 5.
- Angular 1, Backbone, Knockout, Summernote, Dropzone, DOMPurify, i18next.

Build/test scripts:

- PHP: `composer install`, `composer dump-autoload -o`, `composer phpstan`, `composer phpcs`, `composer rector-check`, `composer phpunit-isolated`.
- JS/CSS: `npm install`, `npm run build`, `npm run dev`, `npm run lint:js`, `npm run test:js`, `npm run stylelint`.

## Development Posture And Standards

`CLAUDE.md` is the repo's most concentrated local development guide. Treat it as a useful source of truth for style and test expectations, but still verify against the actual code when behavior matters.

Agent rules of thumb:

- New PHP files should use `declare(strict_types=1);`, PSR-4 namespaces, native parameter/property/return types, and constructor dependencies where practical.
- New business logic should usually live in `src/Services/` or another relevant `src/` namespace, then be called from legacy pages or API controllers.
- Do not use legacy global-heavy code as a style template for new work. Read it to understand runtime behavior, then isolate new logic behind services/events/helpers.
- Prefer `OEGlobalsBag::getString()`, `getInt()`, and `getBoolean()` over direct `$GLOBALS` access in new code.
- Prefer bound SQL through `QueryUtils`, `sqlStatement()`, `sqlQuery()`, or service methods. Never build SQL from unsanitized request data.
- Keep ACL and CSRF checks near the boundary that handles a user action. UI pages generally use `AclMain` and `CsrfUtils`; API routes use `RestConfig::request_authorization_check()` and OAuth/scope listeners.
- Use PSR-3 logging with context arrays, for example `$logger->error('Message', ['id' => $id])`, instead of interpolating sensitive values into the message.
- Catch `\Throwable` for boundary error handling.
- Avoid direct session writes in new code; use the session wrapper/utilities.
- Avoid direct shell execution, `eval`, direct `curl_*`, and service-locator style dependencies in new business logic unless an existing local pattern gives a strong reason.
- When editing Twig templates with render-test coverage, run `composer update-twig-fixtures` and inspect fixture diffs.

Custom static-analysis rules live under `tests/PHPStan/Rules/` and include checks against forbidden globals/request/session access, shell execution, direct curl, eval, catch type issues, and untyped globals access patterns. When changing a file with existing suppressions or baseline issues, prefer fixing the touched area over adding new ignores.

## Local Development

Docker development environments are under `docker/`:

- `development-easy`: default full local environment.
- `development-easy-light`: lighter variant.
- `development-easy-redis`: Redis-enabled variant.
- `development-insane`: heavier/load-testing-oriented variant.
- `production`: production-oriented Docker assets.

Common local start from repo root:

```sh
cd docker/development-easy
docker compose up --detach --wait
```

Expected development URLs from `CLAUDE.md`:

- App: `http://localhost:8300/` or `https://localhost:9300/`
- Default dev login: `admin` / `pass`
- phpMyAdmin: `http://localhost:8310/`

The Docker devtools wrapper can run larger suites from `docker/development-easy/`, for example:

```sh
docker compose exec openemr /root/devtools clean-sweep-tests
docker compose exec openemr /root/devtools unit-test
docker compose exec openemr /root/devtools api-test
docker compose exec openemr /root/devtools e2e-test
docker compose exec openemr /root/devtools services-test
docker compose exec openemr /root/devtools php-log
```

## Data Layer

Legacy DB access is through global functions in `library/sql.inc.php`:

- `sqlStatement()`, `sqlQuery()`, `sqlInsert()` log/audit by default.
- `sqlStatementNoLog()`, `sqlQueryNoLog()` skip audit logging for special internal cases.
- Query binding is supported and should be preferred.
- The ADODB connection is stored in `$GLOBALS['adodb']['db']` and `$GLOBALS['dbh']`.

Newer database infrastructure:

- `config/database.php` defines Doctrine DBAL, ORM, migrations, and `OpenEMR\Common\Database\ConnectionManager`.
- `src/Common/Database/QueryUtils.php` backs many legacy SQL helpers.
- Doctrine entities are under `src/Entities/`, but much of the app still works directly against arrays and SQL helpers.
- `db/` contains Doctrine migrations tooling, but `db/README.md` says it is not fully integrated. Do not use Doctrine migrations for normal schema changes unless the project has explicitly moved that path forward.

Base schema:

- `sql/database.sql` defines about 281 tables.
- Upgrade scripts live in `sql/*-to-*_upgrade.sql`.
- Patch path includes `sql_patch.php`, `sql_upgrade.php`, `library/sql_upgrade_fx.php`, and `src/Services/Utils/SQLUpgradeService.php`.
- Current practical schema-change path is still the master schema plus versioned SQL upgrade scripts. Keep `version.php` database version expectations in mind.

High-value tables:

- `patient_data`: demographics.
- `form_encounter`: encounter headers.
- `forms`: links encounter forms to encounters.
- `registry`: encounter form registry and enablement.
- `globals`: system configuration.
- `user_settings`: per-user config overrides.
- `users`, `users_secure`: user profiles and credentials.
- `facility`: facilities.
- `insurance_data`, `insurance_companies`, `insurance_numbers`: insurance.
- `billing`, `claims`, `ar_session`, `ar_activity`, `payments`: billing and AR.
- `openemr_postcalendar_events`, `openemr_postcalendar_categories`: calendar.
- `documents`, `categories`, `categories_to_documents`: document tree.
- `modules`, `modules_settings`, `modules_hooks_settings`: module installer/runtime state.
- `list_options`, `lists`, `issue_types`: list-driven options and issues.
- `prescriptions`: prescriptions.
- `procedure_order`, `procedure_result`, related procedure tables: lab/procedure orders.
- `immunizations`: immunization records.
- `onsite_portal_activity`, `patient_access_onsite`: portal activity and credentials.
- `uuid_registry`, `uuid_mapping`: UUID mapping used heavily by APIs/FHIR.

## Service Layer Notes

Most modern business/data access classes live in `src/Services/`. Many extend `OpenEMR\Services\BaseService`, but the service layer is not a full ORM and is not uniformly pure DI yet.

Verified `BaseService` behavior:

- Constructor takes a table name, lists table fields with `QueryUtils::listTableFields()`, detects auto-increment columns, and initializes a logger and event dispatcher.
- Provides field selection helpers such as `getSelectFields()` and join extension hooks such as `getSelectJoinTables()`.
- Provides insert/update column builders that whitelist against real table fields and produce bind arrays.
- Exposes `getEventDispatcher()` and optional session access for service methods that need runtime context.
- Includes FHIR search support helpers and returns `ProcessingResult` in many service workflows.

Practical service guidance:

- Put reusable domain behavior in a service even if the first caller is a legacy page.
- Keep API controllers thin: parse/check request, call service, shape response.
- For FHIR, expect an extra mapping layer between OpenEMR records/services and FHIR resource objects under `src/Services/FHIR/`, `src/FHIR/`, and `src/RestControllers/FHIR/`.
- Be careful when instantiating services in old code. Some services still assume globals, an initialized kernel, active site, and database connection.

## Auth, Sessions, ACL, Security

Session handling:

- `src/Common/Session/` contains wrappers and utilities.
- `interface/globals.php` uses `SessionWrapperFactory` and read-only sessions by default unless `$sessionAllowWrite` is set.
- Core session cookie name is controlled by `SessionUtil::CORE_SESSION_ID`.
- `SessionTracker` handles session expiry and optional throttling.

Login/authentication:

- `interface/login/login.php` renders login and handles login setup.
- `library/auth.inc.php` performs login/logout/session validation.
- `src/Common/Auth/AuthUtils.php` handles password validation, Google sign-in, active directory paths, and related auth utility behavior.
- MFA is handled in `interface/main/main_screen.php` using TOTP/U2F registrations.

ACL:

- `src/Common/Acl/AclMain.php` and `AclExtended.php` wrap ACL checks.
- Legacy phpGACL assets are under `gacl/` and ACL tables have `gacl_` prefixes.
- UI pages commonly call `AclMain::aclCheckCore(section, value)`.
- Modules can add ACL sections/settings through module install metadata and module tables.

CSRF and escaping:

- `src/Common/Csrf/CsrfUtils.php` handles CSRF tokens.
- Composer autoload includes global helper files for escaping/sanitization: `library/htmlspecialchars.inc.php`, `library/formdata.inc.php`, `library/sanitize.inc.php`, and `library/formatting.inc.php`.
- Common output helpers include `text()`, `attr()`, `xlt()`, `xla()`, `js_escape()`, and related translation/escaping helpers.

## UI Architecture

The UI is mostly legacy direct PHP scripts under `interface/`.

Main frame:

- `interface/main/main_screen.php`: outside frame, login/MFA handoff, session protection, telemetry/registration dialog setup.
- `interface/main/tabs/main.php`: tabbed main UI, menu loading, JS globals, portal/reminder polling.
- `src/Tabs/TabsWrapper.php`: tab wrapper code.

Menus:

- Main menus are JSON files under `interface/main/tabs/menu/menus/`.
- Main menu roles: `standard.json`, `front_office.json`, `answering_service.json`, `chart_review.json`.
- Patient menu role: `interface/main/tabs/menu/menus/patient_menus/standard.json`.
- Site custom menus can live under `sites/<site_id>/documents/custom_menus/`.
- `src/Menu/MainMenuRole.php` loads the selected main menu, expands special entries such as `Visit Forms` and `Blank Forms`, dispatches `MenuEvent::MENU_UPDATE`, then applies ACL/global restrictions.
- `src/Menu/PatientMenuRole.php` loads patient menus, expands module entries from module hooks, dispatches `PatientMenuEvent::MENU_UPDATE`, then applies restrictions.

Templating:

- Twig templates live mainly under `templates/`, module template folders, and selected `interface` folders.
- `src/Common/Twig/TwigContainer.php` creates Twig with OpenEMR extensions and fires `TwigEnvironmentEvent::EVENT_CREATED` so modules can add loaders/overrides.
- Smarty is still used by `library/classes/Controller.class.php` and legacy controller templates.

Assets:

- Built vendor assets live under `public/assets`.
- Themes live under `public/themes`.
- Images live under `public/images` and site-specific images under `sites/<site_id>/images`.
- `src/Core/Header.php` centralizes script/style header setup and fires `ScriptFilterEvent` and `StyleFilterEvent`.

## Extension System

### Events

OpenEMR uses Symfony EventDispatcher as the main extension mechanism. The kernel is created in `interface/globals.php`, and modules get the dispatcher during bootstrap.

Common extension events include:

- Menus: `MenuEvent::MENU_UPDATE`, `MenuEvent::MENU_RESTRICT`, `PatientMenuEvent::MENU_UPDATE`, `PatientMenuEvent::MENU_RESTRICT`.
- Modules: `ModuleLoadEvents::MODULES_LOADED`.
- Twig: `TwigEnvironmentEvent::EVENT_CREATED`.
- API: `RestApiCreateEvent`, `RestApiSecurityCheckEvent`, `RestApiScopeEvent`, `RestApiResourceServiceEvent`.
- Services: `ServiceSaveEvent::EVENT_PRE_SAVE`, `ServiceSaveEvent::EVENT_POST_SAVE`, `ServiceDeleteEvent`.
- Patients/users/facilities: patient created/updated, user created/updated, facility created/updated.
- Encounters/forms/UI: encounter form load filter, encounter menu/list render events, page heading render events.
- Appointments/calendar: appointment set/render/filter events, calendar event filters.
- Messaging/documents/reports: notification, SMS, patient document, and patient report render events.
- CDA/CCDA/FHIR: CDA pre/post parse, CCDA document creation, FHIR resource search/insert events.

When adding cross-cutting behavior, prefer an event listener/subscriber over editing many legacy scripts.

### Laminas Modules

`interface/globals.php` creates `OpenEMR\Core\ModulesApplication`, which:

- Loads core Laminas modules from `interface/modules/zend_modules/config/application.config.php`.
- Adds database-enabled Laminas modules from the `modules` table.
- Bridges Laminas module bootstrapping with the OpenEMR Symfony event dispatcher.
- Enforces that module scripts can only execute if the module is enabled.

Core always-loaded Laminas modules from config:

- `Application`
- `Installer`
- `Acl`
- `FHIR`
- `CodeTypes`
- `PatientFlowBoard`
- plus Laminas framework modules such as Router, Validator, MVC I18n, and Form.

### Custom Modules

Custom modules live under `interface/modules/custom_modules/<module>/`. Enabled modules are read from the `modules` table and included by `ModulesApplication`.

The custom module bootstrap contract is:

- File name: `openemr.bootstrap.php`.
- The loader injects `$classLoader`, `$eventDispatcher`, and `$module`.
- Modules register their namespace with `ModulesClassLoader`.
- Modules subscribe to events, add menus, add Twig paths, expose public pages, and may have `table.sql`, `info.txt`, `ModuleManagerListener.php`, or `composer.json`.

## Module Catalog

### Top-Level Directory Modules

| Path | Role |
| --- | --- |
| `apis/` | REST/FHIR/portal route dispatch and route maps. |
| `bin/` | CLI entrypoints and helper scripts. |
| `ccdaservice/` | CCDA service support code. |
| `ccr/` | CCR/CCD generation, display, XSL templates. |
| `ci/` | Docker compose and CI support files. |
| `config/` | Experimental PSR-11 container and Doctrine/database service config. |
| `controllers/` | Legacy Smarty controller classes used by `controller.php`. |
| `custom/` | Customization placeholders/templates. |
| `db/` | Doctrine migration config and migrations. |
| `docker/` | Docker build/runtime assets. |
| `Documentation/` | Included product/developer docs, including EHI export diagrams. |
| `gacl/` | Legacy phpGACL ACL library/UI assets. |
| `interface/` | Main browser UI and legacy feature pages. |
| `library/` | Legacy shared PHP libraries, global functions, JS, classes, validation, templates. |
| `meta/` | Metadata/health endpoint. |
| `oauth2/` | OAuth2/SMART authorization endpoint wrapper. |
| `portal/` | Patient portal UI and portal-specific scripts. |
| `public/` | Static assets, themes, images, and front controller. |
| `sites/` | Multisite config, documents, images, LBF plugins, templates, and site data. |
| `sphere/` | Sphere payment/response integration scripts. |
| `sql/` | Base schema, upgrades, patches, seed/example data. |
| `src/` | Namespaced modern PHP classes under `OpenEMR\`. |
| `swagger/` | API documentation artifacts. |
| `templates/` | Twig/Smarty templates shared by controllers and pages. |
| `tests/` | PHPUnit, API, e2e, certification, static-analysis, and JS tests. |
| `tools/` | Helper tooling scripts. |

### `src/` Namespaces

| Namespace | Role |
| --- | --- |
| `Appointment` | Appointment reminder result/support classes. |
| `BC` | Backward-compatibility services: fallback router, DB connection factory/options, static service locator, crypto compatibility. |
| `Billing` | Billing reports, claims, HCFA/UB04/X12 generation, ERA parsing, day sheet aggregation. |
| `ClinicalDecisionRules` | CDR controllers, rule library, alerts, AMC certification report types. |
| `Common` | Cross-cutting infrastructure: ACL, auth, commands, crypto, database, forms, HTTP, logging, sessions, Twig, UUID, utilities, value objects. |
| `Console` | Install command support. |
| `Controllers` | Newer namespaced UI/portal controllers. |
| `Core` | Kernel, module loader/application, header, globals/env bags, error handler, HTTP kernel. |
| `Cqm` | Clinical quality measure/QDM/QRDA support. |
| `Easipro` | Patient-reported outcomes support. |
| `Encryption` | Encryption support classes. |
| `Entities` | Doctrine ORM entity classes. |
| `Events` | Symfony event classes used for module and service extension points. |
| `FHIR` | FHIR models, SMART support, FHIR services/config/autoloading. Largest namespace by file count. |
| `Forms` | Shared form abstractions. |
| `Gacl` | Namespaced ACL support around legacy GACL. |
| `Health` | Health endpoint support. |
| `MedicalDevice` | Medical device support class. |
| `Menu` | Main and patient menu construction and menu events. |
| `OeUI` | UI helper/event support such as page headings/action icons. |
| `Patient` | Patient card/view model helpers. |
| `PaymentProcessing` | Payment processing integrations/webhooks, including Rainforest. |
| `Pdf` | PDF utilities. |
| `Pharmacy` | Pharmacy section rendering event support. |
| `Reminder` | Reminder support class. |
| `Reports` | Report helpers/events. |
| `RestControllers` | Standard API, FHIR API, SMART/OAuth2 controllers, API subscribers, route finders. |
| `Rx` | Prescription/Rx helper class. |
| `Services` | Business/data services for patients, encounters, documents, facilities, insurance, FHIR, billing-related domains, storage, reports, and utilities. |
| `Tabs` | Tabbed UI wrapper code. |
| `Telemetry` | Telemetry service. |
| `Tools` | Developer/tooling classes. |
| `USPS` | USPS support class. |
| `Validators` | Validation result and rules. |

### `interface/` Feature Areas

| Path | Role |
| --- | --- |
| `interface/login/` | Login screen. |
| `interface/main/` | Main application frame, calendar, finder, messages, reminders, reports links, tab shell. |
| `interface/patient_file/` | Patient dashboard, encounter view, history, report, transactions, reminders, birthday alert. |
| `interface/forms/` | Encounter forms and layout-based-form entrypoints. |
| `interface/forms_admin/` | Form registration/admin UI. |
| `interface/billing/` | Billing, claims, payments, ERA/EOB, UB04, X12 helpers. |
| `interface/reports/` | Operational, clinical, billing, inventory, audit, CQM, and patient reports. |
| `interface/super/` | Admin editors for globals, layouts, lists, document templates, codes, site files. |
| `interface/usergroup/` | Users, groups, facilities, ACL-adjacent admin pages. |
| `interface/practice/` | Practice settings pages. |
| `interface/orders/` | Procedure/lab order UI. |
| `interface/patient_tracker/` | Patient flow board/tracker pages. |
| `interface/modules/` | Laminas and custom module roots. |
| `interface/themes/` | Theme support files. |
| `interface/language/` | Language/translation UI. |
| `interface/code_systems/` | Code system management. |
| `interface/drugs/` | Drug inventory/drug admin. |
| `interface/therapy_groups/` | Group therapy workflows. |
| `interface/fax/` | Fax-related legacy pages. |
| `interface/easipro/` | Patient-reported outcomes UI. |
| `interface/webhooks/` | Webhook endpoint. |

### Laminas Module Catalog

| Module | Routes / Hooks | Purpose |
| --- | --- | --- |
| `Acl` | `/acl[/:action][/:id]` | ACL module UI/controller and ACL table model. |
| `Application` | `/`, `/application`, `/index[/:action]`, `/sendto[/:action]`, `/soap[/:action]` | Base Laminas app module; bootstraps module route listener and adds module menu subscriber. |
| `Carecoordination` | `/carecoordination`, `/carecoordination/setup`, `/encounterccdadispatch`, `/encountermanager`, `/ccd` | CCDA/CCD care coordination, setup, encounter CCDA dispatch, imports/uploads; depends on Ccr, Immunization, Syndromic Surveillance, Documents. |
| `Ccr` | `/ccr[/:action][/:id]` | CCR handling module used by care coordination. |
| `CodeTypes` | Event subscriber only | Code-system/list-option mapping and external code event handling. |
| `Documents` | `/documents/documents[/:action][/:id][/:download][/:doencryption][/:key]` | Document table/controller/plugin support for module workflows. |
| `FHIR` | Event subscribers only | UUID mapping and calculated-observation hooks for FHIR support. |
| `Immunization` | `/immunization[/:action][/:id]` | Immunization module controller and layout. |
| `Installer` | `/Installer[/:action][/:id]` | Module installer/manager UI and table model. |
| `PatientFilter` | Event listeners | Patient blacklist/filtering on finder, appointments, and demographics view/update events. |
| `PatientFlowBoard` | Event subscriber | Patient flow board event integration. |
| `Patientvalidation` | `/patientvalidation[/:action][/:id]` | Patient validation module UI. |
| `PrescriptionTemplates` | `/prescription-html-template`, `/prescription-pdf-template` | Prescription HTML/PDF template management. |
| `Syndromicsurveillance` | `/syndromicsurveillance[/:action][/:id]` | Syndromic surveillance module controller/layout. |

### Custom Module Catalog

| Module | Namespace / Description | Main integration points |
| --- | --- | --- |
| `oe-module-claimrev-connect` | `OpenEMR\Modules\ClaimRevConnector`; Claim Revolution clearinghouse connector. | Registers module namespace; hooks global settings, eligibility sections, appointment events, Twig overrides, and menu entries. |
| `oe-module-comlink-telehealth` | `Comlink\OpenEMR\Modules\TeleHealthModule`; Comlink telehealth/video module. | Hooks appointment creation, calendar JS/CSS/rendering, patient portal appointment filtering/rendering, user/patient registration events, admin fields, Twig overrides, body scripts; exposes public room endpoints. |
| `oe-module-dashboard-context` | `OpenEMR\Modules\DashboardContext`; dashboard context manager for patient summary widget visibility. | Hooks patient dashboard render events and menu updates. |
| `oe-module-dorn` | `OpenEMR\Modules\Dorn`; Diagnostic Ordering Result Network. | Lab configuration, lab route setup, compendium install, DORN orders, HL7 result retrieval/acknowledgement, global settings, Twig overrides, menu entry. |
| `oe-module-ehi-exporter` | `OpenEMR\Modules\EhiExporter`; EHI export for ONC certification requirements. | Adds EHI export menu/settings and export behavior for single patient/all-patient electronic health information. |
| `oe-module-faxsms` | `OpenEMR\Modules\FaxSMS`; fax, SMS, email, voice notification module. | Hooks menus, patient report/document actions, SMS/notification render events, notification services, vendor dispatching, RingCentral/SignalWire integrations. |
| `oe-module-prior-authorizations` | `Juggernaut\OpenEMR\Modules\PriorAuthModule`; advanced prior authorization manager. | Adds reports insurance menu item and patient menu item; stores auths in `module_prior_authorizations`; public manager/report pages. |
| `oe-module-weno` | `OpenEMR\Modules\WenoModule`; Weno EZ e-prescribing integration. | Hooks patient render sections, globals, menu, pharmacy section rendering, patient create/update auxiliary events. |

### Encounter Form Catalog

Traditional encounter forms live in `interface/forms/<form>/`. Standard files are usually `info.txt`, `new.php`, `save.php`, `view.php`, `report.php`, and optional `table.sql`.

Forms are registered in the `registry` table through `library/registry.inc.php` and administered by `interface/forms_admin/forms_admin.php`. The encounter view uses `src/Common/Forms/FormLocator.php`, which allows modules to filter form file loading through `LoadEncounterFormFilterEvent` while enforcing safe module include paths.

| Directory | Title from `info.txt` | Notes |
| --- | --- | --- |
| `aftercare_plan` | Aftercare Plan | Standard encounter form with table SQL. |
| `ankleinjury` | Ankle Evaluation Form | Standard encounter form with table SQL. |
| `bronchitis` | Bronchitis Form | Standard encounter form with table SQL. |
| `CAMOS` | CAMOS | Larger form with admin/content parser assets. |
| `care_plan` | Care Plan | Includes JS and table SQL. |
| `clinical_instructions` | Clinical Instructions | Standard form. |
| `clinical_notes` | Clinical Notes | Includes JS and table SQL. |
| `clinic_note` | Clinic Note | Standard note form. |
| `dictation` | Speech Dictation | Dictation form. |
| `eye_mag` | Eye Exam | Large ophthalmology/eye exam form set. |
| `fee_sheet` | Fee Sheet | Billing/coding encounter form. |
| `functional_cognitive_status` | Functional and Cognitive Status | Clinical form. |
| `gad7` | GAD-7 | Clinical assessment form. |
| `group_attendance` | Group Attendance Form | Group encounter support. |
| `LBF` | Layout Based Forms | Dynamic forms built from layout tables rather than a per-form directory. |
| `misc_billing_options` | Misc Billing Options HCFA | Billing options form. |
| `newGroupEncounter` | New Group Encounter Form | Group encounter creation. |
| `newpatient` | New Patient Form | Encounter header/new patient visit form. |
| `note` | Work/School Note | Note/print form. |
| `observation` | Observation | Clinical observation form with JS/CSS. |
| `painmap` | Graphic Pain Map | Pain map form/class. |
| `phq9` | PHQ-9 | Clinical assessment form. |
| `physical_exam` | Physical Exam | Physical exam form. |
| `prior_auth` | Prior Authorization | Administrative form. |
| `procedure_order` | Procedure Order | Lab/procedure order form and deletion handling. |
| `questionnaire_assessments` | New Questionnaire | LForms/questionnaire form, portal-capable. |
| `requisition` | Lab Requisition | Lab requisition/barcode form. |
| `reviewofs` | Review of Systems Checks | ROS checks form. |
| `ros` | Review Of Systems | ROS class-based form. |
| `sdoh` | Social Screening Tool | SDOH assessment, portal-capable. |
| `soap` | SOAP | SOAP encounter note form. |
| `track_anything` | Track anything | Custom tracking/graphing form. |
| `transfer_summary` | Transfer Summary | Standard clinical form. |
| `treatment_plan` | Treatment Plan | Standard clinical form. |
| `vitals` | Vitals | Vitals form with service/calculation support. |

### REST API Resources

Standard API resource groups in `_rest_routes_standard.inc.php`:

- `patient` - largest route group; demographics, encounters, vitals, SOAP notes, insurance, appointments, documents, messages, transactions, and nested patient resources.
- `facility`
- `practitioner`
- `medical_problem`
- `allergy`
- `drug`
- `procedure`
- `immunization`
- `prescription`
- `insurance_company`
- `insurance_type`
- `appointment`
- `user`
- `background_service`
- `product`
- `version`
- `list`
- `transaction`

FHIR route resources in `_rest_routes_fhir_r4_us_core_3_1_0.inc.php`:

- `.well-known`, `metadata`
- `AllergyIntolerance`, `Appointment`, `CarePlan`, `CareTeam`, `Condition`, `Coverage`, `Device`, `DiagnosticReport`, `DocumentReference`, `Encounter`, `Goal`, `Group`, `Immunization`, `Location`, `Media`, `Medication`, `MedicationDispense`, `MedicationRequest`, `Observation`, `OperationDefinition`, `Organization`, `Patient`, `Person`, `Practitioner`, `PractitionerRole`, `Procedure`, `Provenance`, `Questionnaire`, `QuestionnaireResponse`, `RelatedPerson`, `ServiceRequest`, `Specimen`, `ValueSet`

Portal API resources:

- `GET /portal/patient`
- `GET /portal/patient/encounter`
- `GET /portal/patient/encounter/:euuid`
- `GET /portal/patient/appointment`
- `GET /portal/patient/appointment/:auuid`

## Main Workflows

### Login And Main UI

1. User reaches `index.php`.
2. `index.php` chooses site and redirects to `interface/login/login.php`.
3. `login.php` sets `$ignoreAuth = true`, includes `globals.php`, loads logos/language/facility choices, and renders the login template.
4. Submit goes through `library/auth.inc.php`, which validates password or Google sign-in through `AuthUtils`.
5. `interface/main/main_screen.php` handles MFA and session tokens, then loads the tabbed UI.
6. `interface/main/tabs/main.php` loads menu data, JS globals, reminders/portal polling, and tab content.

### Patient Chart

Patient chart pages are under `interface/patient_file/`.

- Summary/dashboard: `interface/patient_file/summary/`.
- History: `interface/patient_file/history/`.
- Encounters: `interface/patient_file/encounter/`.
- Transactions: `interface/patient_file/transaction/`.
- Reports: `interface/patient_file/report/`.

Modern patient services live in `src/Services/PatientService.php`, `src/Services/PatientIssuesService.php`, `src/Services/InsuranceService.php`, `src/Patient/Cards/`, and related service classes.

### Encounters And Forms

`interface/patient_file/encounter/forms.php` displays encounter forms, handles orphaned procedure orders, ESign buttons, and loads form reports through `FormLocator` and `FormReportRenderer`.

Creating/opening forms generally routes to:

- `interface/patient_file/encounter/load_form.php`
- `interface/patient_file/encounter/view_form.php`
- The target form's `new.php`, `save.php`, `view.php`, `report.php`

Form registration state is in `registry`; actual encounter instances are linked via `forms` and form-specific tables.

### Scheduling

Calendar UI lives under `interface/main/calendar/` and still includes PostCalendar-derived code under `interface/main/calendar/modules/PostCalendar/`.

Modern appointment service/API support lives in:

- `src/Services/AppointmentService.php`
- `src/RestControllers/AppointmentRestController.php`
- `src/RestControllers/FHIR/FhirAppointmentRestController.php`
- appointment events under `src/Events/Appointments/`

Calendar data is primarily in `openemr_postcalendar_events` and categories in `openemr_postcalendar_categories`.

### Billing And Claims

Billing UI lives under `interface/billing/`. Billing domain classes live under `src/Billing/`.

Important billing classes:

- `src/Billing/Claim.php`
- `src/Billing/Hcfa1500.php`, `HCFAInfo.php`
- `src/Billing/X125010837P.php`, `X125010837I.php`
- `src/Billing/EDI270.php`
- `src/Billing/ParseERA.php`
- `src/Billing/BillingProcessor/`
- `src/Billing/DaySheet/`

The fee sheet encounter form is `interface/forms/fee_sheet/`. Billing touches `billing`, `claims`, `payments`, `ar_session`, `ar_activity`, `procedure_*`, insurance tables, and code tables.

### Documents

Documents use both legacy controller and Laminas module surfaces:

- Legacy controller: `controllers/C_Document.class.php`, route through `controller.php`.
- Category controller: `controllers/C_DocumentCategory.class.php`.
- Laminas module: `interface/modules/zend_modules/module/Documents/`.
- Services: `src/Services/DocumentService.php`, `src/Services/DocumentTemplates/`.
- Site storage: `sites/<site_id>/documents/`.
- Document config: `sites/<site_id>/config.php` under `$GLOBALS['oer_config']['documents']`.

### Clinical Decision Rules And CQM

Clinical decision rules live in:

- `src/ClinicalDecisionRules/`
- `library/clinical_rules.php`
- `templates/super/rules/`
- `interface/patient_file/rules/`

CQM/QRDA support is in `src/Cqm/` and `src/Services/Qdm/`, `src/Services/Qrda/`, plus reports such as `interface/reports/cqm.php`.

### FHIR, SMART, CCDA, CCR

FHIR/SMART:

- Route maps: `apis/routes/_rest_routes_fhir_r4_us_core_3_1_0.inc.php`.
- Controllers: `src/RestControllers/FHIR/`.
- Services/mappers: `src/Services/FHIR/`.
- FHIR model classes: `src/FHIR/R4/`.
- SMART/OAuth2: `src/RestControllers/SMART/`, `src/FHIR/SMART/`, `src/Common/Auth/OpenIDConnect/`, `oauth2/authorize.php`.

CCDA/CCR:

- CCR legacy code: `ccr/`.
- CCDA service code: `ccdaservice/`.
- Laminas care coordination module: `interface/modules/zend_modules/module/Carecoordination/`.
- CDA services/events: `src/Services/Cda/`, `src/Events/CDA/`.
- EHI export custom module: `interface/modules/custom_modules/oe-module-ehi-exporter/`.

### Reports

Report pages live primarily in `interface/reports/`. There are report helpers under `src/Reports/` and service classes under `src/Services/Reports/`.

Reports are usually direct PHP scripts that include `globals.php`, check ACLs, query via SQL helpers/services, and render HTML/PDF/CSV.

### Background Services And Notifications

Background service command and reports:

- `src/Common/Command/BackgroundServicesCommand.php`
- `src/RestControllers/BackgroundServiceRestController.php`
- `interface/reports/background_services.php`
- `background_services` table

Notification and messaging code spans:

- `interface/main/messages/`
- `src/Events/Messaging/`
- `src/Services/MessageService.php`
- `src/Common/Command/PhoneNotificationCommand.php`
- custom module `oe-module-faxsms`

## Where To Change Things

Use these starting points for common future tasks:

| Task | Start here |
| --- | --- |
| Add/modify a browser UI page | The specific `interface/` script, then shared helpers in `library/` or services in `src/Services/`. |
| Add/modify API behavior | `apis/routes/*`, matching `src/RestControllers/*`, then `src/Services/*`. |
| Add/modify FHIR resource behavior | `src/RestControllers/FHIR/*`, `src/Services/FHIR/*`, FHIR route map, UUID mapping support. |
| Add a new business operation | Prefer a `src/Services/*Service.php` method; call it from legacy page/API controller. |
| Add a menu item | Prefer listener on `MenuEvent::MENU_UPDATE` or `PatientMenuEvent::MENU_UPDATE`; otherwise edit menu JSON. |
| Add an encounter form | Add `interface/forms/<name>/info.txt`, `new.php`, `save.php`, `view.php`, `report.php`, optional `table.sql`; register through forms admin/registry. |
| Add a custom module | Create `interface/modules/custom_modules/<module>/openemr.bootstrap.php`, register namespace, subscribe to events, add `info.txt` and `table.sql` if needed. |
| Add a Laminas module | Add under `interface/modules/zend_modules/module/<Module>`, configure `module.config.php`, then install/enable via modules table/installer if not core. |
| Add configuration | For user-facing globals use `globals`/`interface/super/edit_globals.php`; for site-local static config use `sites/<site_id>/config.php`; for experimental DI use `config/*.php`. |
| Add database schema | Update `sql/database.sql`, add current upgrade script, consider service/query changes and tests. |
| Add permission checks | Use `AclMain::aclCheckCore()` in UI, `RestConfig::request_authorization_check()` in API, and update ACL install/upgrade data if adding new ACL objects. |
| Add tests | Isolated tests in `tests/Tests/Isolated` or unit-isolated suites; DB/API tests in configured `tests/Tests/*` suites. |

## Testing Map

OpenEMR separates tests by required initialization:

- `phpunit-isolated.xml`: no DB; sets `DISABLE_DATABASE=1`; includes `tests/Tests/Isolated`, selected BC/unit tests.
- `phpunit.xml`: DB/initialized application tests; suites include unit, e2e, API, services, validators, controllers, common, ECQM, certification, email.
- `phpunit.integration.xml`: integration API/subscriber tests.
- JS tests use Jest config in `jest.config.js`, with tests under `tests/js/`.
- Static analysis helpers: `phpstan.neon.dist`, `.phpstan/`, `tests/PHPStan/`, `rector.php`, `phpcs.xml.dist`, Semgrep config.

Useful commands from repository root:

```sh
composer phpunit-isolated
phpunit -c phpunit.xml
phpunit -c phpunit.integration.xml
composer phpstan
composer phpcs
composer rector-check
npm run test:js
npm run lint:js
npm run stylelint
```

Repo testing notes from `tests/Tests/README.md` and `CLAUDE.md`:

- Browser E2E tests use Symfony Panther.
- Fixtures live under `tests/Tests/Fixture` and currently support patient data and FHIR patient resources.
- Isolated Twig tests include compilation tests for all Twig templates and render tests for selected templates.
- PHPUnit data providers may need the repo-standard `@codeCoverageIgnore` comment because they execute before coverage instrumentation.
- Full static-analysis and quality commands are expensive but catch cross-file issues; PHPStan should be understood as whole-program analysis, not only changed-file linting.

## Agent Risk Notes

- Many scripts require `interface/globals.php` and rely on globals set as local variables. Refactoring a page without preserving local/global expectations can break distant includes.
- `$GLOBALS`, `OEGlobalsBag`, and session values are often the same practical state. Check all three when debugging.
- Avoid direct string SQL interpolation. Use bound parameters with `sqlStatement`, `sqlQuery`, `QueryUtils`, or services.
- Do not bypass ACL or CSRF checks. Legacy pages often use explicit `AclMain` and `CsrfUtils` calls.
- Module bootstrap runs during `globals.php`; keep module bootstrap lightweight.
- Directly including module files must use safe paths. `ModulesApplication::isSafeModuleFileForInclude()` exists for this reason.
- Menu JSON is filtered by requirements, ACL, globals, and module events. If a menu item does not appear, inspect all of those layers.
- Encounter form display can be filtered by modules through `LoadEncounterFormFilterEvent`.
- API requests are mediated by Symfony kernel subscribers; behavior may be in a subscriber rather than the route closure.
- FHIR patient requests have patient-bound restrictions; user and patient tokens are handled differently.
- `sites/default/sqlconf.php` and `sites/default/config.php` are site-specific and often changed by setup/deployment, not just source edits.
- Some older libraries use side effects on include. Prefer small targeted edits and regression checks around the exact workflow.
- This checkout includes a front controller, but the legacy direct-file model is still central. Do not assume a single router owns all browser pages.
- `controller.php` is legacy-controller routing here, not the main API/Symfony/Laminas router.
- There are two migration stories in the tree. Prefer current SQL upgrade conventions unless a maintainer explicitly asks for Doctrine migrations.
- There are two module families. New custom behavior usually belongs in `interface/modules/custom_modules/` with event listeners; Laminas `zend_modules` are mostly existing surfaces.
- There are two template engines. New templates should usually be Twig, but legacy controllers may still require Smarty.
- Internal integer IDs and external UUIDs are both real. API/FHIR work usually needs `UuidRegistry` or `uuid_mapping`.

## High-Value Files To Read First

Core boot/routing:

- `index.php`
- `public/index.php`
- `bootstrap.php`
- `interface/globals.php`
- `src/BC/FallbackRouter.php`
- `src/Core/Kernel.php`
- `src/Core/ModulesApplication.php`
- `src/Core/OEGlobalsBag.php`
- `src/BC/ServiceContainer.php`

Auth/session/security:

- `interface/login/login.php`
- `interface/main/main_screen.php`
- `library/auth.inc.php`
- `src/Common/Auth/AuthUtils.php`
- `src/Common/Acl/AclMain.php`
- `src/Common/Csrf/CsrfUtils.php`
- `src/Common/Session/`

Data:

- `library/sql.inc.php`
- `src/Common/Database/QueryUtils.php`
- `config/database.php`
- `sql/database.sql`
- `version.php`

APIs:

- `apis/dispatch.php`
- `_rest_routes.inc.php`
- `apis/routes/_rest_routes_standard.inc.php`
- `apis/routes/_rest_routes_fhir_r4_us_core_3_1_0.inc.php`
- `apis/routes/_rest_routes_portal.inc.php`
- `src/RestControllers/ApiApplication.php`
- `src/Common/Http/HttpRestRouteHandler.php`
- `src/RestControllers/Subscriber/RoutesExtensionListener.php`

UI:

- `interface/main/tabs/main.php`
- `src/Menu/MainMenuRole.php`
- `src/Menu/PatientMenuRole.php`
- `interface/main/tabs/menu/menus/standard.json`
- `interface/main/tabs/menu/menus/patient_menus/standard.json`
- `src/Core/Header.php`
- `src/Common/Twig/TwigContainer.php`

Patients/encounters/forms:

- `interface/patient_file/summary/demographics.php`
- `interface/patient_file/encounter/forms.php`
- `interface/patient_file/encounter/load_form.php`
- `src/Common/Forms/FormLocator.php`
- `library/registry.inc.php`
- `src/Services/PatientService.php`
- `src/Services/EncounterService.php`
- `src/Services/FormService.php`

Modules:

- `interface/modules/zend_modules/config/application.config.php`
- `interface/modules/zend_modules/module/*/config/module.config.php`
- `interface/modules/custom_modules/*/openemr.bootstrap.php`
- `interface/modules/zend_modules/module/Installer/`

Billing/documents:

- `interface/billing/`
- `src/Billing/`
- `controllers/C_Document.class.php`
- `src/Services/DocumentService.php`
- `interface/modules/zend_modules/module/Documents/`

Reference docs in this repo:

- `CLAUDE.md`: development guide, coding standards, local dev/test commands.
- `CONTRIBUTING.md`: contribution workflow and setup details.
- `API_README.md`: proprietary REST API notes.
- `FHIR_README.md`: FHIR R4 / US Core notes.
- `DOCKER_README.md`: Docker setup.
- `README-Isolated-Testing.md`: host-side isolated testing.
- `tests/Tests/README.md`: test suite structure and fixtures.
- `db/README.md`: Doctrine migrations status and warnings.
