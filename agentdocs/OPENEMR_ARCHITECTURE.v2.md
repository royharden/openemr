# OpenEMR Architecture — Agent Onboarding Guide (v2)

> **Audience:** AI coding agents who need to ramp up on OpenEMR fast in order to ship code changes safely.
> **Scope:** Everything inside `./openemr/`.
> **Version:** v2 (merges [v1](OPENEMR_ARCHITECTURE.v1.md) with [openemr-codebase-agent-map.md](openemr-codebase-agent-map.md)). v1 covers coding standards, PHPStan rules, the worked-example request flow, gotchas, and CI in more depth — read it alongside this. v2 supersedes v1 for boot sequence, route inventory, module catalog, and event-name specifics.
> **Read this first**, then jump to the section you need. Cross-reference [CLAUDE.md](../CLAUDE.md) for coding standards (it is authoritative on style).

---

## 1. TL;DR — The 60-second model

OpenEMR is a self-hosted Electronic Medical Record + Practice Management web app. It runs on PHP 8.2+ / MySQL, exposes a REST API, a FHIR R4 (US Core 3.1.0) API, SMART-on-FHIR OAuth2, and CCDA/CCR document pipelines. The codebase has **two layers**:

| Layer | Where | Style | Status |
|---|---|---|---|
| **Modern** | `src/` (PSR-4 `OpenEMR\…`), `templates/*.twig`, `db/Migrations/` | DI, Symfony components, Twig, strict types, PHPStan level 10 | Where new code goes |
| **Legacy** | `interface/`, `library/`, `controllers/`, `*.php` at repo root, Smarty templates | Procedural, `$GLOBALS`, `$_SESSION`, ADODB | Still ~70% of runtime; do not extend, but you will read it constantly |

**The two layers communicate via** `library/sql.inc.php` ↔ `src/Common/Database/QueryUtils`, `$GLOBALS` ↔ `OEGlobalsBag` (the bag mirrors values back into `$GLOBALS` for legacy consumers), Smarty ↔ Twig. Most new services extend `OpenEMR\Services\BaseService`. The Symfony `EventDispatcher` on the `Kernel` is the canonical extension point.

**Version constants** (`version.php`): currently `8.1.1-dev`, database version `538`, ACL version `13`. Bump these when you ship a schema/ACL change.

**Top-level entry points (root PHP files):**

| File | Role |
|---|---|
| `index.php` | Front controller. Picks `site_id` from `?site=`, `HTTP_HOST`, or `default`; validates it; loads `sites/<site_id>/sqlconf.php`; redirects to `interface/login/login.php?site=<id>` (installed) or `setup.php?site=<id>` (`$config = 0`, uninstalled). |
| `public/index.php` | **Modern front controller.** Loads `bootstrap.php`, builds a PSR-7 request, delegates to `OpenEMR\BC\FallbackRouter`. |
| `controller.php` | Legacy Smarty router → `library/classes/Controller.class.php`. Has a fixed whitelist (see §6.4). |
| `bootstrap.php` | Minimal CLI bootstrap (autoloader, env, error handler). Used by `bin/console`. |
| `setup.php` | Install wizard (states 0–7: perms, DB, PHP/web check, theme). Writes `sites/<id>/sqlconf.php`. |
| `sql_upgrade.php`, `sql_patch.php` | Run after a version bump to apply schema deltas under `sql/`. Backed by `library/sql_upgrade_fx.php` + `src/Services/Utils/SQLUpgradeService.php`. |
| `acl_upgrade.php`, `ippf_upgrade.php` | ACL system upgrade, IPPF locale upgrade. |
| `admin.php` | Multi-site admin UI. |
| `_rest_routes.inc.php` | Loader that pulls `apis/routes/*.inc.php`. |

---

## 2. Directory map (what lives where)

```
openemr/
├── src/                # Modern PSR-4 (OpenEMR\…)               ← write new code here
├── library/            # Legacy procedural helpers              ← read-mostly
├── interface/          # Legacy web UI (PHP screens by domain)  ← read-mostly
├── controllers/        # Legacy C_*.class.php Smarty controllers (used by controller.php)
├── portal/             # Patient portal (mostly independent; portal/patient/index.php is the modern app)
├── apis/               # REST/FHIR dispatcher + route maps
├── oauth2/             # OAuth2/SMART authorization server endpoint
├── swagger/            # API documentation artifacts
├── templates/          # Twig (modern, majority) + a little Smarty (legacy)
├── sql/                # Master schema + version-pair upgrade scripts
├── db/                 # Doctrine Migrations (experimental, not yet primary)
├── config/             # Experimental PSR-11 container + Doctrine database config
├── tests/              # PHPUnit, Panther E2E, isolated, custom PHPStan rules, JS
├── docker/             # Compose flavors: development-easy, light, redis, insane, production
├── public/             # Static assets, themes, images, modern front controller
├── bin/                # bin/console (Symfony Console), command-runner (older)
├── cli/                # Doctrine ORM/Migrations CLI (experimental)
├── ccdaservice/        # Node service for CCDA generation/parsing
├── ccr/                # Continuity of Care Record helpers + XSL templates
├── meta/               # Metadata + /meta/health endpoint
├── sphere/             # Sphere payment integration scripts
├── contrib/            # Community add-ons, code-system data (icd9/10, snomed, rxnorm)
├── custom/             # Per-site customization placeholders
├── tools/              # Helper tooling scripts
├── Documentation/      # Product/developer docs
├── gacl/               # Legacy phpGACL ACL library + UI assets
├── modules/            # Composer-loaded modules
├── sites/default/      # Per-instance config + document storage (multi-site)
│   ├── sqlconf.php     # DB credentials ($config = 0 means "not installed yet")
│   ├── config.php      # Site-local config (e.g. $GLOBALS['oer_config']['documents'])
│   ├── documents/      # Patient chart files; site custom_menus/, LBF plugins
│   └── logs/
├── package.json, composer.json, gulpfile.js
└── CLAUDE.md           # Coding standards (authoritative — see v1 §10)
```

**Multi-site:** OpenEMR can host many practices on one install. Each `sites/<site_id>/sqlconf.php` points to a separate DB. `index.php` resolves `$_SERVER['HTTP_HOST']` → `site_id`. Site-local custom menus live under `sites/<site_id>/documents/custom_menus/`.

---

## 3. Technology stack (snapshot)

- **Runtime:** PHP `>=8.2.0`, Node `>=24.0.0` (build only), MySQL/MariaDB
- **Backend:** Laminas MVC (legacy modules), Symfony components (HttpKernel, EventDispatcher, Console, DI, HttpFoundation, Finder, Process, Cache, Yaml), Doctrine DBAL 4.x + ORM + Migrations
- **Auth:** league/oauth2-server, OpenID Connect classes (SMART-on-FHIR)
- **Frontend:** Bootstrap 4.6, jQuery 3.7, AngularJS 1.x (yes, AngularJS), Backbone, Knockout, DataTables, Select2, Chart.js, CKEditor 5, Summernote, Dropzone, DOMPurify, i18next; SASS via Gulp 4
- **Templates:** Twig 3.x (modern, majority), Smarty 4.5 (legacy: `library/classes/Controller.class.php` + `controllers/C_*`)
- **DB access:** ADODB legacy surface API in `library/sql.inc.php`; `OpenEMR\Common\Database\QueryUtils` and `ConnectionManager` (`config/database.php`) for new code; `BC/DatabaseConnectionFactory` to vend connections without `new`
- **PDFs/exports:** Dompdf, mpdf, rospdf, PhpSpreadsheet, Flysystem
- **Mail/HTTP/logs:** PHPMailer, Guzzle, Monolog
- **Testing:** PHPUnit 11, Symfony Panther (E2E), Jest 29
- **Static analysis:** PHPStan level 10 (`max`), Rector, custom rules in `tests/PHPStan/Rules/`
- **APIs:** REST (proprietary `/apis/`), FHIR R4 US Core 3.1.0, SMART-on-FHIR, OAuth2/OIDC, optional CDS Hooks

---

## 4. Runtime request flow

### 4.1 Legacy bootstrap — `interface/globals.php`

This is the most-included file in the repository. Any browser-facing legacy script that includes it gets:

1. Composer autoload
2. PHP compatibility check
3. `.env` load (if present)
4. Logger + exception handler creation
5. Filesystem and web paths: `$fileroot`, `$webroot`, `$srcdir`, `$rootdir`, `OE_SITE_DIR`, `OE_SITE_WEBROOT`
6. Active site resolution from session or `?site=`
7. Database opened via `library/sql.inc.php` (sets `$GLOBALS['adodb']['db']`, `$GLOBALS['dbh']`)
8. `version.php` loaded
9. Settings pulled from the `globals` table; user overrides from `user_settings`
10. Site-local `sites/<site_id>/config.php` included
11. `library/auth.inc.php` included **unless** `$ignoreAuth` or a portal bypass flag is set
12. Module system loaded via `OpenEMR\Core\ModulesApplication` if the `modules` table exists
13. HTTP request logged via `EventAuditLogger`
14. Returns an `OpenEMR\Core\OEGlobalsBag` instance — but **also mirrors values into `$GLOBALS`** so legacy code keeps working

Refactoring a page **must preserve local + global expectations** because distant includes read these.

### 4.2 Modern front controller — `public/index.php` + FallbackRouter

`public/index.php` loads `bootstrap.php`, builds a PSR-7 request, and delegates to `OpenEMR\BC\FallbackRouter`. The router rewrites these prefixes:

| URL prefix | Target |
|---|---|
| `/apis` | `apis/dispatch.php` |
| `/oauth2` | `oauth2/authorize.php` |
| `/meta/health` | `meta/health/index.php` |
| `/portal/patient` | `portal/patient/index.php` |
| `/interface/modules/zend_modules/public` | `interface/modules/zend_modules/public/index.php` |

For non-rewritten paths it resolves a real file, **blocks sensitive directories** (`config`, `db`, `docker`, `sql`, `src`, `tests`, `vendor`, dotfiles, templates, site documents), passes through static assets, mutates `$_SERVER['SCRIPT_FILENAME']` / `SCRIPT_NAME` / `PHP_SELF`, changes working directory, and includes the legacy file. The legacy direct-file model is still central — **do not assume one router owns all browser pages**.

### 4.3 REST / FHIR / OAuth2 / SMART

`apis/dispatch.php` and `oauth2/authorize.php` both build an `OpenEMR\Common\Http\HttpRestRequest` and run `OpenEMR\RestControllers\ApiApplication`.

`ApiApplication` registers Symfony kernel subscribers in this order:

1. `ExceptionHandlerListener`
2. `TelemetryListener`
3. `ApiResponseLoggerListener`
4. `SessionCleanupListener`
5. `SiteSetupListener`
6. `CORSListener`
7. `OAuth2AuthorizationListener`
8. `AuthorizationListener`
9. `RoutesExtensionListener`
10. `ViewRendererListener`

**Behavior often lives in a subscriber, not the route closure.** Check the listeners first when debugging API-layer behavior.

Routes (loaded via `_rest_routes.inc.php`):

| Route map | File | Entries |
|---|---|---|
| Standard REST | `apis/routes/_rest_routes_standard.inc.php` | 96 |
| FHIR R4 US Core 3.1.0 | `apis/routes/_rest_routes_fhir_r4_us_core_3_1_0.inc.php` | 71 |
| Patient portal | `apis/routes/_rest_routes_portal.inc.php` | 5 |

OAuth2 / OIDC / SMART code: `src/RestControllers/AuthorizationController.php`, `src/RestControllers/SMART/`, `src/Common/Auth/OpenIDConnect/`, `src/FHIR/SMART/`.

### 4.4 Legacy Smarty controller — `controller.php`

Includes `interface/globals.php`, instantiates `library/classes/Controller.class.php`, and dispatches either explicit (`?controller=document&action=…`) or positional (`?document&list&…`) routing. Whitelist:

| Controller name | Class file (under `controllers/`) |
|---|---|
| `document` | `C_Document.class.php` |
| `document_category` | `C_DocumentCategory.class.php` |
| `hl7` | `C_Hl7.class.php` |
| `insurance_company` | `C_InsuranceCompany.class.php` |
| `insurance_numbers` | `C_InsuranceNumbers.class.php` |
| `patient_finder` | `C_PatientFinder.class.php` |
| `pharmacy` | `C_Pharmacy.class.php` |
| `practice_settings` | `C_PracticeSettings.class.php` |
| `prescription` | `C_Prescription.class.php` |
| `x12_partner` | `C_X12Partner.class.php` |

Output uses Smarty templates under `templates/`.

### 4.5 CLI

`bin/console` — Symfony Console entrypoint. Loads Composer; supports `--skip-globals`; otherwise sets `$_GET['site']`, includes `interface/globals.php` with `$ignoreAuth = true`, then runs `OpenEMR\Common\Command\SymfonyCommandRunner`. Available commands under `src/Common/Command/`: ACL modification, background services, CCDA import, document import, API documentation generation, access token generation, API test client registration, email test, release changelog generation.

`bin/command-runner` — older custom runner; prefer `bin/console`.

`cli/` — experimental Doctrine ORM/Migrations CLI.

---

## 5. Modern code (`src/`) — namespace map

`src/` is PSR-4 under the `OpenEMR\` prefix. New code goes here.

| Namespace | Role |
|---|---|
| `Appointment` | Appointment reminder result/support classes |
| `BC` | **Backward-compatibility services**: `FallbackRouter`, `DatabaseConnectionFactory`, `ServiceContainer` (static facade for legacy code → logger, DB, clock, PSR-7/17, crypto), crypto compatibility |
| `Billing` | Claims (X12 837), HCFA-1500, UB04, ERA (835) parsing, payment gateway, AR/daysheet |
| `ClinicalDecisionRules` | CDR controllers, rule library, alerts, AMC certification report types |
| `Common` | Cross-cutting infrastructure (see §5.2) |
| `Console` | Install command support |
| `Controllers` | Newer namespaced UI/portal controllers |
| `Core` | `Kernel`, `OEHttpKernel`, `OEGlobalsBag`, `Header`, `ModulesApplication`, `ModulesClassLoader`, `AbstractModuleActionListener`, error handler |
| `Cqm` | Clinical quality measures, QDM 5.5/5.6, QRDA III generation |
| `Easipro` | EasiPRO / PROMIS patient-reported outcomes |
| `Encryption` | Encryption support classes |
| `Entities` | Doctrine ORM entities (limited; most code still uses arrays + SQL helpers) |
| `Events` | Symfony event classes (extension points; see §7) |
| `FHIR` | **Largest namespace.** R4 models (`R4/`), SMART support, exporters, autoloaders |
| `Forms` | Shared form abstractions |
| `Gacl` | Namespaced wrapper around legacy GACL |
| `Health` | Health endpoint support |
| `MedicalDevice` | Medical device support |
| `Menu` | `MainMenuRole`, `PatientMenuRole`, menu events |
| `OeUI` | UI helper events (page headings, action icons) |
| `Patient` | Patient card / view-model helpers |
| `PaymentProcessing` | Payment integrations + webhooks (e.g. Rainforest) |
| `Pdf` | PDF utilities |
| `Pharmacy` | Pharmacy section rendering events |
| `Reminder` | Reminder support |
| `Reports` | Report helpers/events |
| `RestControllers` | Standard + FHIR + SMART/OAuth2 controllers, API subscribers, route finders |
| `Rx` | Prescription helpers |
| `Services` | Business/data services for patients, encounters, documents, facilities, insurance, FHIR, billing, storage, reports, utilities |
| `Tabs` | Tabbed UI wrapper |
| `Telemetry` | Telemetry service |
| `Tools` | Developer/tooling classes |
| `USPS` | USPS address validation |
| `Validators` | `ProcessingResult` standard wrapper, validation rules |

> **Correction from v1:** `src/Modules/` does not exist. Modules live under `interface/modules/` (Laminas + custom). See §7.

### 5.1 Service layer (`src/Services/`)

Most services extend `OpenEMR\Services\BaseService`. `BaseService` provides CRUD against `TABLE_NAME`, FHIR search via `FhirSearchWhereClauseBuilder`, UUID registry handling, lifecycle event dispatch, pagination, field selection. Some specialized services (e.g. `PatientPortalService`, `PatientAccessOnsiteService`) do not — confirm by reading the file.

**New service skeleton:**
```php
namespace OpenEMR\Services;
class ExampleService extends BaseService
{
    public const TABLE_NAME = "example";
    public function __construct() { parent::__construct(self::TABLE_NAME); }
}
```

**Hot services to know:** `PatientService`, `EncounterService`, `FormService`, `AppointmentService`, `DocumentService`, `InsuranceService`, `AllergyIntoleranceService`, `ConditionService`, `MedicationService`, `ImmunizationService`, `ObservationService`, `ProcedureService`, `MessageService`, `BackgroundService`, `PatientPortalService`, `PatientAccessOnsiteService`, `FhirExportServiceLocator`.

### 5.2 Common (`src/Common/`)

| Subpackage | What it gives you |
|---|---|
| `Database/` | `QueryUtils` (escaping, prepared statements, table introspection), `QueryPagination`, `ConnectionManager`, `DatabaseQueryTrait` |
| `Auth/` | `AuthUtils` (password validation, Google sign-in, AD), OAuth2 key config, OIDC, MFA (`MfaUtils`) |
| `Acl/` | `AclMain::aclCheckCore($section, $value)` — canonical permission gate; `AclExtended` |
| `Logging/` | PSR-3 logger; `SystemLoggerAwareTrait`; `EventAuditLogger` for HIPAA audit |
| `Crypto/` | `CryptoGen` for column/document encryption |
| `Http/` | `Psr17Factory`, `HttpRestRequest`, `HttpRestRouteHandler` |
| `Twig/` | `TwigContainer` builds Twig env + fires `TwigEnvironmentEvent::EVENT_CREATED` for module overrides |
| `Session/` | `SessionWrapperFactory`, `SessionUtil` (`CORE_SESSION_ID` cookie), `SessionTracker` (expiry + throttling) |
| `Uuid/` | `UuidRegistry` — int ↔ UUID for FHIR (`uuid_registry`, `uuid_mapping` tables) |
| `Csrf/` | `CsrfUtils::collectCsrfToken()` / `verifyCsrfToken()` |
| `Forms/` | `FormLocator` (encounter form file resolution + `LoadEncounterFormFilterEvent`), CSRF, validation |
| `Command/` | Symfony Console command classes (`BackgroundServicesCommand`, `PhoneNotificationCommand`, etc.) |

**Output/escaping helpers (composer-autoloaded globals from `library/`):** `text()`, `attr()`, `xlt()`, `xla()`, `js_escape()`. Use these in any UI/template code that interpolates user input. Backed by `library/htmlspecialchars.inc.php`, `library/formdata.inc.php`, `library/sanitize.inc.php`, `library/formatting.inc.php`.

### 5.3 REST and FHIR

- **`src/RestControllers/`** — `ApiApplication.php` is the Symfony HttpKernel; `Subscriber/` contains the 10 listeners from §4.3. Per-resource controllers (`PatientRestController`, etc.).
- **`src/FHIR/`** — R4 resources in `R4/` (PHPFHIR-generated), `Export/` serializers, `SMART/` for SMART-on-FHIR. Service interfaces: `IResourceSearchableService`, `IResourceCreatableService`, `IResourceReadableService`, `IResourceUpdateableService`, `IPatientCompartmentResourceService`, `IFhirExportableResourceService`.
- **`src/Services/FHIR/`** — domain → FHIR mappers.

---

## 6. Legacy code (`library/`, `interface/`, `controllers/`)

You will read this code daily. Do not extend its patterns; bridge into `src/` instead.

### 6.1 `library/` — procedural helpers

| File | Role |
|---|---|
| `library/sql.inc.php` | Legacy DB API. `sqlStatement`/`sqlQuery`/`sqlInsert` log+audit by default; `sqlStatementNoLog`/`sqlQueryNoLog` skip audit for special internal cases. **Always use bound parameters** (avoid string interpolation). Connection lives in `$GLOBALS['adodb']['db']` and `$GLOBALS['dbh']`. |
| `library/auth.inc.php` | Session/auth bootstrap. Side-effect: requires login or kicks to `login.php`. |
| `library/acl.inc.php` | Legacy ACL gates. New code → `AclMain::aclCheckCore`. |
| `library/options.inc.php` | Generates select/text/codes form widgets across the UI. Reads `list_options`. |
| `library/patient.inc.php` | Demographics/insurance/contact retrieval. |
| `library/appointments.inc.php` | Calendar appointment CRUD. |
| `library/payment.inc.php` | Payment posting / adjustments. |
| `library/log.inc.php` | Audit-log helpers (writes `log` and `audit_master`). |
| `library/registry.inc.php` | **Encounter form registration** (read by `FormLocator`). |
| `library/clinical_rules.php` | CDR rule evaluation entry. |
| `library/sql_upgrade_fx.php` | DB upgrade helpers used by `sql_upgrade.php`. |

**Subdirectories:** `classes/` (Document, Note, Person, Controller, CouchDB), `ajax/` (XHR endpoints), `admin/`, `ESign/`, `MedEx/`, `smarty/`, `smarty_legacy/`, `validation/`.

### 6.2 `interface/` — legacy web UI

Each subdirectory is a user-facing area. Most files include `interface/globals.php` first.

| Path | Area |
|---|---|
| `login/` | Login screen (`login.php` sets `$ignoreAuth = true` then includes globals) |
| `main/` | Main app frame, calendar (`main/calendar/` + PostCalendar derivative), finder, messages, reminders, tab shell |
| `main/main_screen.php` | Outside frame, MFA (TOTP/U2F), session protection, telemetry/registration dialog |
| `main/tabs/main.php` | Tabbed UI, menu loading, JS globals, portal/reminder polling |
| `main/tabs/menu/menus/` | Main menu JSON files: `standard.json`, `front_office.json`, `answering_service.json`, `chart_review.json` |
| `main/tabs/menu/menus/patient_menus/` | Patient menu JSON: `standard.json` |
| `patient_file/` | Patient dashboard, encounter view, history, transactions, reports, reminders, birthday alert |
| `patient_file/encounter/forms.php` | Lists encounter forms; handles orphans, ESign, form report rendering |
| `patient_file/encounter/load_form.php` / `view_form.php` | Routes to a form's `new.php`/`save.php`/`view.php`/`report.php` |
| `forms/` | Encounter forms (see catalog §8) |
| `forms_admin/` | Form registration/admin UI |
| `billing/` | Claims, payments, ERA/EOB, UB04, X12 helpers |
| `practice/` | Facility/insurance/pharmacy admin |
| `reports/` | Operational, clinical, billing, inventory, audit, CQM, patient reports |
| `super/` | Admin editors: globals, layouts, lists, document templates, codes, site files |
| `usergroup/` | Users, groups, facilities, ACL admin |
| `orders/` | Procedure/lab order UI |
| `patient_tracker/` | Flow board / queue |
| `drugs/`, `code_systems/` | Drug DB, ICD/SNOMED/RxNorm |
| `themes/` | Theme SCSS sources (Gulp → `public/themes/`) |
| `fax/`, `batchcom/` | Fax dispatch, batch comms |
| `esign/` | E-signature workflow |
| `language/` | Translation UI |
| `easipro/` | PROMIS UI |
| `webhooks/` | Webhook endpoint |
| `modules/` | Module mount points (see §7) |
| `smart/` | SMART-on-FHIR app launch UI |

### 6.3 `portal/` — patient portal

Mostly independent of `/interface/`. The richer modern app is `portal/patient/` (rewritten by `FallbackRouter`). Subdirs: `account/`, `patient/`, `messaging/`, `report/`, `sign/`, `lib/`. Portal-specific REST routes in `apis/routes/_rest_routes_portal.inc.php`. Services: `src/Services/PatientPortalService.php`, `src/Services/PatientAccessOnsiteService.php`. Tables: `onsite_portal_activity`, `patient_access_onsite`.

### 6.4 `controllers/` — legacy Smarty controllers

`C_Document`, `C_DocumentCategory`, `C_Hl7`, `C_InsuranceCompany`, `C_InsuranceNumbers`, `C_PatientFinder`, `C_Pharmacy`, `C_PracticeSettings`, `C_Prescription`, `C_X12Partner`. Reached via `controller.php?controller=…`. Output uses Smarty templates under `templates/`.

### 6.5 `templates/` — Twig (majority) + Smarty (legacy)

Twig dominates: `login/`, `core/`, `portal/`, `emails/`, `interface/`, `documents/`, `reports/`, `encounters/`, `oauth2/`, `api/`. Module template folders extend the Twig path via `TwigEnvironmentEvent::EVENT_CREATED`. Smarty remains for `library/classes/Controller.class.php` and the `controllers/C_*` flow.

**Twig render-fixture protocol:** after editing a Twig template that has render coverage in `tests/Tests/Isolated/Common/Twig/fixtures/render/`, run `composer update-twig-fixtures` and review the diff before committing.

---

## 7. Extension model: events + modules

OpenEMR uses Symfony `EventDispatcher` as the **primary** extension mechanism. Subscribe to events in module bootstrap rather than editing many legacy scripts.

### 7.1 Common event names

| Domain | Events |
|---|---|
| Menus | `MenuEvent::MENU_UPDATE`, `MenuEvent::MENU_RESTRICT`, `PatientMenuEvent::MENU_UPDATE`, `PatientMenuEvent::MENU_RESTRICT` |
| Modules | `ModuleLoadEvents::MODULES_LOADED` |
| Twig | `TwigEnvironmentEvent::EVENT_CREATED` |
| API | `RestApiCreateEvent`, `RestApiSecurityCheckEvent`, `RestApiScopeEvent`, `RestApiResourceServiceEvent` |
| Services | `ServiceSaveEvent::EVENT_PRE_SAVE`, `ServiceSaveEvent::EVENT_POST_SAVE`, `ServiceDeleteEvent` |
| Patients/users/facilities | created/updated lifecycle events |
| Encounters/forms | `LoadEncounterFormFilterEvent`, encounter menu/list render, page heading render |
| Appointments/calendar | set/render/filter events |
| Messaging/documents/reports | notification, SMS, patient document, patient report render |
| CDA/CCDA/FHIR | CDA pre/post parse, CCDA document creation, FHIR resource search/insert |
| UI scripts/styles | `ScriptFilterEvent`, `StyleFilterEvent` (fired by `src/Core/Header.php`) |

Menu loading: `MainMenuRole`/`PatientMenuRole` load JSON, expand special entries (`Visit Forms`, `Blank Forms`, module hooks), dispatch `MENU_UPDATE`, then apply ACL/global restrictions.

### 7.2 Laminas modules — `interface/modules/zend_modules/module/`

Loaded from `interface/modules/zend_modules/config/application.config.php` plus DB-enabled modules from the `modules` table. Bridged to the Symfony dispatcher by `OpenEMR\Core\ModulesApplication`, which **enforces that module scripts only execute if the module is enabled** and provides `isSafeModuleFileForInclude()` for safe path checks.

| Module | Routes / Hooks | Purpose |
|---|---|---|
| `Acl` | `/acl[/:action][/:id]` | ACL UI/controller + table model |
| `Application` | `/`, `/application`, `/index[/:action]`, `/sendto[/:action]`, `/soap[/:action]` | Base Laminas app; route listener + module menu subscriber |
| `Carecoordination` | `/carecoordination`, `/carecoordination/setup`, `/encounterccdadispatch`, `/encountermanager`, `/ccd` | CCDA/CCD; depends on Ccr, Immunization, Syndromicsurveillance, Documents |
| `Ccr` | `/ccr[/:action][/:id]` | CCR handling |
| `CodeTypes` | event subscriber only | Code-system / list-option mapping |
| `Documents` | `/documents/documents[/:action][/:id][/:download][/:doencryption][/:key]` | Document table/controller/plugin |
| `FHIR` | event subscribers only | UUID mapping + calculated-observation hooks |
| `Immunization` | `/immunization[/:action][/:id]` | Immunization controller + layout |
| `Installer` | `/Installer[/:action][/:id]` | Module installer/manager UI |
| `PatientFilter` | event listeners | Patient blacklist/filtering on finder, appointments, demographics |
| `PatientFlowBoard` | event subscriber | Flow-board integration |
| `Patientvalidation` | `/patientvalidation[/:action][/:id]` | Patient validation UI |
| `PrescriptionTemplates` | `/prescription-html-template`, `/prescription-pdf-template` | Rx template management |
| `Syndromicsurveillance` | `/syndromicsurveillance[/:action][/:id]` | Syndromic surveillance |

**Do not add new Laminas modules.** Touch only when fixing existing behavior.

### 7.3 Custom modules — `interface/modules/custom_modules/`

The modern path. Enabled rows in the `modules` table → loaded by `ModulesApplication`. Naming: `oe-module-<name>`.

**Bootstrap contract:**
- Entry file: `openemr.bootstrap.php`
- Loader injects `$classLoader`, `$eventDispatcher`, `$module`
- Module registers its namespace with `ModulesClassLoader`
- Subscribes to events; adds menus, Twig paths, public pages
- Optional: `table.sql`, `info.txt`, `ModuleManagerListener.php`, `composer.json`

| Module | Namespace | Integration points |
|---|---|---|
| `oe-module-claimrev-connect` | `OpenEMR\Modules\ClaimRevConnector` | Globals, eligibility, appointment events, Twig overrides, menus |
| `oe-module-comlink-telehealth` | `Comlink\OpenEMR\Modules\TeleHealthModule` | Appointments, calendar JS/CSS/render, portal appointments, user/patient events, admin fields, Twig overrides; public room endpoints |
| `oe-module-dashboard-context` | `OpenEMR\Modules\DashboardContext` | Patient dashboard render, menus |
| `oe-module-dorn` | `OpenEMR\Modules\Dorn` | Lab config + routes, compendium install, DORN orders, HL7 results, globals, Twig, menus |
| `oe-module-ehi-exporter` | `OpenEMR\Modules\EhiExporter` | EHI export menu/settings; single + all-patient export |
| `oe-module-faxsms` | `OpenEMR\Modules\FaxSMS` | Menus, patient report/document actions, SMS/notification render, vendor dispatch (RingCentral/SignalWire) |
| `oe-module-prior-authorizations` | `Juggernaut\OpenEMR\Modules\PriorAuthModule` | Reports insurance + patient menu items; `module_prior_authorizations` table; public manager/report pages |
| `oe-module-weno` | `OpenEMR\Modules\WenoModule` | Patient render, globals, menu, pharmacy section, patient create/update events |

**Modules tables:** `modules`, `modules_settings`, `modules_hooks_settings`.

---

## 8. Encounter forms (`interface/forms/`)

Standard files per form: `info.txt`, `new.php`, `save.php`, `view.php`, `report.php`, optional `table.sql`. Registered in the `registry` table via `library/registry.inc.php`; admin UI at `interface/forms_admin/forms_admin.php`. Encounter view uses `src/Common/Forms/FormLocator.php`, which lets modules filter form loading via `LoadEncounterFormFilterEvent` while enforcing safe include paths.

| Directory | Title | Notes |
|---|---|---|
| `aftercare_plan` | Aftercare Plan | |
| `ankleinjury` | Ankle Evaluation | |
| `bronchitis` | Bronchitis | |
| `CAMOS` | CAMOS | Larger; admin/content parser assets |
| `care_plan` | Care Plan | JS + table SQL |
| `clinical_instructions` | Clinical Instructions | |
| `clinical_notes` | Clinical Notes | JS + table SQL |
| `clinic_note` | Clinic Note | |
| `dictation` | Speech Dictation | |
| `eye_mag` | Eye Exam | Large ophthalmology set |
| `fee_sheet` | Fee Sheet | Billing/coding |
| `functional_cognitive_status` | Functional and Cognitive Status | |
| `gad7` | GAD-7 | Assessment |
| `group_attendance` | Group Attendance | |
| `LBF` | Layout Based Forms | **Dynamic** — built from layout tables, not a per-form directory |
| `misc_billing_options` | Misc Billing Options HCFA | |
| `newGroupEncounter` | New Group Encounter | |
| `newpatient` | New Patient (encounter header) | |
| `note` | Work/School Note | |
| `observation` | Observation | JS/CSS |
| `painmap` | Graphic Pain Map | |
| `phq9` | PHQ-9 | Assessment |
| `physical_exam` | Physical Exam | |
| `prior_auth` | Prior Authorization | |
| `procedure_order` | Procedure Order | |
| `questionnaire_assessments` | New Questionnaire | LForms; portal-capable |
| `requisition` | Lab Requisition | Barcode |
| `reviewofs` | ROS Checks | |
| `ros` | Review Of Systems | Class-based |
| `sdoh` | Social Screening Tool | Portal-capable |
| `soap` | SOAP | |
| `track_anything` | Track Anything | Custom tracking/graphing |
| `transfer_summary` | Transfer Summary | |
| `treatment_plan` | Treatment Plan | |
| `vitals` | Vitals | Service + calculation support |

---

## 9. APIs — REST, FHIR, OAuth2, SMART

### 9.1 Standard REST resource groups

`patient` (largest — demographics, encounters, vitals, SOAP, insurance, appointments, documents, messages, transactions, nested resources), `facility`, `practitioner`, `medical_problem`, `allergy`, `drug`, `procedure`, `immunization`, `prescription`, `insurance_company`, `insurance_type`, `appointment`, `user`, `background_service`, `product`, `version`, `list`, `transaction`.

### 9.2 FHIR R4 US Core 3.1.0 resources

`.well-known`, `metadata`, `AllergyIntolerance`, `Appointment`, `CarePlan`, `CareTeam`, `Condition`, `Coverage`, `Device`, `DiagnosticReport`, `DocumentReference`, `Encounter`, `Goal`, `Group`, `Immunization`, `Location`, `Media`, `Medication`, `MedicationDispense`, `MedicationRequest`, `Observation`, `OperationDefinition`, `Organization`, `Patient`, `Person`, `Practitioner`, `PractitionerRole`, `Procedure`, `Provenance`, `Questionnaire`, `QuestionnaireResponse`, `RelatedPerson`, `ServiceRequest`, `Specimen`, `ValueSet`.

### 9.3 Portal API

`GET /portal/patient`, `GET /portal/patient/encounter`, `GET /portal/patient/encounter/:euuid`, `GET /portal/patient/appointment`, `GET /portal/patient/appointment/:auuid`.

### 9.4 Reference docs

`API_README.md` (proprietary REST), `FHIR_README.md` (FHIR R4 / US Core), Swagger UI under `/swagger/`.

---

## 10. Database

### 10.1 Schema location

- **Master:** `sql/database.sql` — ~281 `CREATE TABLE` statements.
- **Version-pair upgrades:** `sql/<from>-to-<to>_upgrade.sql`. `sql_upgrade.php` walks these in order; backed by `library/sql_upgrade_fx.php` + `src/Services/Utils/SQLUpgradeService.php`.
- **Doctrine Migrations:** `db/Migrations/Version*.php` — present but **experimental** per `db/README.md`. Long-term direction. Configured in `db/migration-config.php` and `config/database.php`.

### 10.2 High-value tables grouped by domain

| Domain | Tables |
|---|---|
| Patient demographics | `patient_data`, `addresses`, `history_data`, `insurance_data`, `employer_data`, `person`, `contact`, `contact_relation` |
| Encounters / forms | `form_encounter`, `forms`, `registry` (encounter form enablement), `form_soap`, `form_vitals`, `form_vital_details`, `form_clinical_notes`, `form_reviewofs`, `form_ros` |
| Prescriptions / drugs | `prescriptions`, `drugs`, `drug_inventory`, `drug_sales`, `drug_templates`, `erx_rx_log`, `erx_narcotics` |
| Billing / insurance | `billing`, `claims`, `payments`, `ar_session`, `ar_activity`, `fee_schedule`, `fee_sheet_options`, `benefit_eligibility`, `insurance_companies`, `insurance_numbers` |
| Procedures / labs | `procedure_order`, `procedure_result`, related procedure tables |
| Scheduling | `openemr_postcalendar_events`, `openemr_postcalendar_categories`, `care_teams`, `care_team_member` |
| Audit / logging | `audit_master`, `audit_details`, `api_log`, `direct_message_log`, `log` |
| ACL / users | `users`, `users_secure` (creds), `groups`, `gacl_*` (~25 tables) |
| Modules | `modules`, `modules_settings`, `modules_hooks_settings` |
| Configuration | `globals`, `user_settings`, `list_options`, `lists`, `issue_types` |
| FHIR / OAuth2 | `uuid_registry`, `uuid_mapping`, `oauth_clients`, `oauth_trusted_user`, `jwt_grant_history` |
| Documents | `documents`, `categories`, `categories_to_documents` |
| Portal | `onsite_portal_activity`, `patient_access_onsite` |
| Other | `immunizations`, `codes`, `clinical_plans`, `clinical_rules`, `questionnaire_*`, `form_questionnaire_assessments`, `background_services` |

**Look up canonical column names:** `grep "CREATE TABLE \`<name>\`" sql/database.sql -A 60`.

### 10.3 Reading data

- Modern: `OpenEMR\Common\Database\QueryUtils::fetchRecords($sql, $bindings)` + `QueryPagination`.
- Legacy: `sqlStatement`, `sqlQuery`, `sqlInsert`, `sqlFetchArray` from `library/sql.inc.php`. Use bound parameters always.
- Both ultimately use Doctrine DBAL 4. **Never** instantiate a connection directly — use `BC/DatabaseConnectionFactory` or `Common/Database/ConnectionManager`.

### 10.4 UUIDs

Many entities have both an integer `id` and a UUID. The `uuid_registry` and `uuid_mapping` tables map them. Use `OpenEMR\Common\Uuid\UuidRegistry` (FHIR exposure depends on it).

---

## 11. Auth, ACL, security

- **Login:** `interface/login/login.php` → `library/auth.inc.php`. Password validation, Google sign-in, AD via `OpenEMR\Common\Auth\AuthUtils`. MFA (TOTP/U2F) handled in `interface/main/main_screen.php`.
- **Sessions:** `OpenEMR\Common\Session\` — `SessionWrapperFactory`, `SessionUtil` (`CORE_SESSION_ID` cookie), `SessionTracker` (expiry + throttling). Read-only by default unless `$sessionAllowWrite` is set. **Do not write `$_SESSION` directly in new code** — PHPStan rule `ForbiddenDirectSessionWriteRule` blocks it.
- **ACL:** UI calls `AclMain::aclCheckCore($section, $value)`. API calls `RestConfig::request_authorization_check()`. Backed by GACL (`gacl/` legacy assets, `src/Gacl/` namespaced wrapper, `gacl_*` tables). Modules add ACL sections via install metadata + module tables.
- **OAuth2 / OIDC / SMART:** `src/Common/Auth/OpenIDConnect/`, `src/FHIR/SMART/`, `src/RestControllers/AuthorizationController.php`, `oauth2/authorize.php`. Scopes enforced by `OAuth2AuthorizationListener`.
- **Audit log:** HIPAA audit goes to `audit_master`/`audit_details` via `OpenEMR\Common\Logging\EventAuditLogger`. Touched patient data → audit it.
- **Crypto:** `OpenEMR\Common\Crypto\CryptoGen`. Keys live under `sites/<id>/documents/logs_and_misc/methods/` (do not commit).
- **CSRF:** `OpenEMR\Common\Csrf\CsrfUtils::collectCsrfToken()` / `verifyCsrfToken()`.
- **Output escaping:** Always use `text()` / `attr()` / `xlt()` / `xla()` / `js_escape()` in templates and UI scripts.

---

## 12. Coding standards (the parts you'll trip over)

Read [CLAUDE.md](../CLAUDE.md) for the full list and v1 §10 for fuller treatment. Most-cited rules:

1. `declare(strict_types=1);` at the top of every new PHP file.
2. Native types on every parameter, property, return.
3. Use `OEGlobalsBag` instead of `$GLOBALS`. Typed getters: `getString`, `getInt`, `getBoolean`.
4. Use `QueryUtils` instead of raw `mysqli_*` or fresh connections.
5. Inject dependencies through the constructor; no service locators in business logic.
6. Catch `\Throwable`, not `\Exception`.
7. PSR-3 logging context arrays — never interpolate values into the message string.
8. No `eval`, `exec/system/shell_exec`, or direct `curl_*`. Use Guzzle.
9. `match` on enums without `default` — preserves PHPStan exhaustiveness.
10. Domain primitives for IDs (`PatientId`, `EncounterId`).
11. `DateTimeImmutable`, `readonly` value objects.
12. No `@phpstan-ignore` to silence errors; fix at the source.

### Custom PHPStan rules (`tests/PHPStan/Rules/`, ~18 rules)

`ForbidGlobalKeywordRule`, `ForbiddenGlobalsAccessRule`, `ForbiddenCatchTypeRule`, `ForbiddenShellExecutionRule`, `ForbiddenCurlFunctionsRule`, `ForbiddenEvalRule`, `ForbiddenDirectSessionWriteRule`, `ForbiddenRequestGlobalsRule`, `ForbiddenInstantiationsRule`, `OEGlobalsBagTypedGetterRule`, … Registered in `.phpstan/extension.neon`.

---

## 13. Build, test, CI

### 13.1 Local dev

```bash
cd docker/development-easy
docker compose up --detach --wait
# App:        http://localhost:8300/   (https://localhost:9300/)
# admin/pass
# phpMyAdmin: http://localhost:8310/
```

Docker flavors: `development-easy` (default), `development-easy-light`, `development-easy-redis`, `development-insane` (load testing), `production`.

### 13.2 Tests

PHPUnit configurations:
- `phpunit-isolated.xml` — no DB; sets `DISABLE_DATABASE=1`; `tests/Tests/Isolated` + selected BC/unit tests
- `phpunit.xml` — DB/initialized; suites: unit, e2e, API, services, validators, controllers, common, ECQM, certification, email
- `phpunit.integration.xml` — integration API/subscriber tests

```bash
# In Docker (from docker/development-easy/)
docker compose exec openemr /root/devtools clean-sweep-tests   # all
docker compose exec openemr /root/devtools unit-test
docker compose exec openemr /root/devtools api-test
docker compose exec openemr /root/devtools e2e-test
docker compose exec openemr /root/devtools services-test

# On host
composer phpunit-isolated
composer update-twig-fixtures   # after Twig edits
npm run test:js                 # Jest
```

### 13.3 Quality (host-side)

```bash
composer code-quality     # phpcs + phpstan + rector + …
composer phpstan          # level 10 max — always full codebase
composer phpcs / phpcbf
composer rector-check / rector-fix
composer require-checker
composer codespell
composer conventional-commits:check
composer php-syntax-check
npm run lint:js / lint:js-fix
npm run stylelint
```

### 13.4 Build

```bash
npm run build       # Production: Gulp compiles SCSS → public/themes/, public/assets/
npm run dev         # Watch
npm run gulp-build  # Build only, no watch
```

Gulp sources: `interface/themes/tabs_style_*.scss`, `interface/themes/oe-styles/`, `interface/themes/colors/`.

### 13.5 CI (`.github/workflows/`, ~30 workflows)

`test.yml`, `api-test.yml`, `isolated-tests.yml`, `e2e-test.yml`, `phpstan.yml`, `phpstan-baseline-diff.yml`, `styling.yml`, `conventional-commits.yml`, `spellcheck.yml`, `shellcheck.yml`, `semgrep.yml`, `database.yml`, `inferno-test.yml` (FHIR/SMART compliance), `build-dev-php-fpm-docker.yml`. Pre-commit hooks: `prek install` (or `pre-commit install`).

### 13.6 Commit messages

Conventional Commits: `<type>(<scope>): <description>`, types `feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert`. AI-assisted commits add an `Assisted-by:` trailer (e.g., `Assisted-by: Claude Code`).

---

## 14. Worked examples — request → response

### 14.1 FHIR `GET /apis/default/fhir/AllergyIntolerance?patient=<uuid>`

1. Hits `apis/dispatch.php`.
2. Route matched in `_rest_routes_fhir_r4_us_core_3_1_0.inc.php` → handler in `src/RestControllers/FHIR/`.
3. `ApiApplication` runs subscribers in order. `OAuth2AuthorizationListener` validates the Bearer token + scope `user/AllergyIntolerance.read`. `AclMain::aclCheckCore` confirms permission.
4. Controller calls `AllergyIntoleranceService::getAll(['patient' => $uuid])`.
5. `BaseService` builds parameterized SQL via `QueryUtils`, joins UUID via `UuidRegistry`.
6. Returns `ProcessingResult` of domain objects.
7. `src/Services/FHIR/` mapper builds `FHIRAllergyIntolerance` resources; `src/FHIR/Export/` serializes.
8. `ApiResponseLoggerListener` + `TelemetryListener` log; `EventAuditLogger` writes to `audit_master`.
9. `CORSListener` adds CORS headers; `ViewRendererListener` writes the response.

### 14.2 Legacy form save (vitals)

1. User submits `interface/forms/vitals/save.php`.
2. File requires `interface/globals.php` → all 14 boot steps run (§4.1).
3. CSRF verified via `CsrfUtils::verifyCsrfToken()`.
4. ACL via `AclMain::aclCheckCore` (or legacy `acl_check`).
5. Insert via `sqlInsert(...)` from `library/sql.inc.php` (audited automatically).
6. Audit row written via `library/log.inc.php` helpers.
7. Redirect back to encounter view in `interface/patient_file/encounter/`.

---

## 15. Where to look for X (cheat sheet)

| Task | Start here |
|---|---|
| Add a service | `src/Services/<Foo>Service.php` extending `BaseService` |
| Add a REST endpoint | Route in `apis/routes/_rest_routes_standard.inc.php`; controller in `src/RestControllers/`; service in `src/Services/` |
| Add a FHIR resource | `src/RestControllers/FHIR/`, `src/Services/FHIR/`, `src/FHIR/Export/`, FHIR route map, `UuidRegistry` |
| Add a clinical UI screen | `interface/<area>/`. Reuse Twig in `templates/`. Wire menu via module event subscriber. |
| Run on every patient save | Subscribe to a `src/Events/Patient/*` or `ServiceSaveEvent::EVENT_POST_SAVE` event |
| Schema change | Add `sql/<from>-to-<to>_upgrade.sql`; long-term: Doctrine `db/Migrations/Version*.php`. Update `version.php` DB version. |
| Add a global setting | Define in globals service / `interface/super/edit_globals.php`; read via `OEGlobalsBag` typed getters |
| Add site-local config | `sites/<site_id>/config.php` |
| ACL-gate a UI action | `AclMain::aclCheckCore($section, $value)` |
| ACL-gate an API action | `RestConfig::request_authorization_check()` (also enforced by listeners) |
| Audit a patient-data action | `EventAuditLogger` in `src/Common/Logging/` |
| Add a Twig template | `templates/<area>/`; if render-test covered, run `composer update-twig-fixtures` |
| Add a menu item | Listener on `MenuEvent::MENU_UPDATE` / `PatientMenuEvent::MENU_UPDATE`; otherwise edit menu JSON |
| Add an encounter form | `interface/forms/<name>/info.txt` + `new.php` + `save.php` + `view.php` + `report.php` (+ `table.sql`); register via `forms_admin` / `registry` table |
| Add a custom module | `interface/modules/custom_modules/<name>/openemr.bootstrap.php`; register namespace; subscribe events; add `info.txt` + `table.sql` |
| Add a CLI command | `src/Common/Command/<Foo>Command.php`; expose via `bin/console` |
| Encrypt a column / document | `OpenEMR\Common\Crypto\CryptoGen` |
| Resolve `$GLOBALS['foo']` | `OEGlobalsBag::getString('foo')` (or typed equivalents) |
| Replace a `new Service()` | Inject through constructor; configure in DI container under `src/Core/` |
| Output user input safely | `text()` / `attr()` / `xlt()` / `xla()` / `js_escape()` |

---

## 16. Common gotchas

- **Two template engines** — `.twig` modern, `.tpl` Smarty. New work uses Twig.
- **Two DB APIs** — `sqlStatement` legacy vs `QueryUtils` modern. Don't mix in the same function.
- **Two module systems** — Laminas (`zend_modules`) vs Symfony (`custom_modules`). New modules use Symfony.
- **`globals.php` side effects** — many legacy files require it first. It sets `$GLOBALS`, starts session, auths the user, opens DB, loads modules. Removing the include breaks distant downstream code.
- **`OEGlobalsBag` mirrors into `$GLOBALS`** — when debugging, check `$GLOBALS`, the bag, *and* session simultaneously; they're the same practical state.
- **PHPStan baseline** — never add new entries; fix the type error. When editing a file, also fix existing baseline entries for it.
- **PHPStan must run on full codebase**, then filter for changed files.
- **Twig render fixtures** — silent diffs in `tests/Tests/Isolated/Common/Twig/fixtures/render/`. Run `composer update-twig-fixtures` after edits and review the diff.
- **`prek` / pre-commit** — install once with `prek install`. Hooks (phpstan, rector, phpcs, codespell) catch issues before CI.
- **Multi-site** — production deployments often run >1 site. `sites/<id>/sqlconf.php` is per-site. Anything you store outside the DB needs to be site-scoped.
- **UUIDs vs IDs** — FHIR speaks UUIDs, internal tables speak ints. Bridge via `UuidRegistry`.
- **API behavior often lives in a Subscriber, not the route closure** — check the 10 listeners in §4.3 first.
- **Patient FHIR requests have patient-bound restrictions** — user vs patient tokens are handled differently.
- **Module file includes must use safe paths** — `ModulesApplication::isSafeModuleFileForInclude()` exists for this.
- **Conventional Commits enforced in CI** — get the format right or the build fails.
- **Default checkout looks "uninstalled"** — `sites/default/sqlconf.php` ships with `$config = 0`; setup writes the real value.
- **Some legacy libraries side-effect on include.** Prefer small, targeted edits + regression checks around the exact workflow.

---

## 17. Reference — high-value files to read first

**Boot / routing:** `index.php`, `public/index.php`, `bootstrap.php`, `interface/globals.php`, `src/BC/FallbackRouter.php`, `src/Core/Kernel.php`, `src/Core/ModulesApplication.php`, `src/Core/OEGlobalsBag.php`, `src/BC/ServiceContainer.php`.

**Auth / session / security:** `interface/login/login.php`, `interface/main/main_screen.php`, `library/auth.inc.php`, `src/Common/Auth/AuthUtils.php`, `src/Common/Acl/AclMain.php`, `src/Common/Csrf/CsrfUtils.php`, `src/Common/Session/`.

**Data:** `library/sql.inc.php`, `src/Common/Database/QueryUtils.php`, `config/database.php`, `sql/database.sql`, `version.php`.

**APIs:** `apis/dispatch.php`, `_rest_routes.inc.php`, `apis/routes/*.inc.php`, `src/RestControllers/ApiApplication.php`, `src/Common/Http/HttpRestRouteHandler.php`, `src/RestControllers/Subscriber/RoutesExtensionListener.php`.

**UI:** `interface/main/tabs/main.php`, `src/Menu/MainMenuRole.php`, `src/Menu/PatientMenuRole.php`, `interface/main/tabs/menu/menus/standard.json`, `interface/main/tabs/menu/menus/patient_menus/standard.json`, `src/Core/Header.php`, `src/Common/Twig/TwigContainer.php`.

**Patients / encounters / forms:** `interface/patient_file/summary/demographics.php`, `interface/patient_file/encounter/forms.php`, `interface/patient_file/encounter/load_form.php`, `src/Common/Forms/FormLocator.php`, `library/registry.inc.php`, `src/Services/PatientService.php`, `src/Services/EncounterService.php`, `src/Services/FormService.php`.

**Modules:** `interface/modules/zend_modules/config/application.config.php`, `interface/modules/zend_modules/module/*/config/module.config.php`, `interface/modules/custom_modules/*/openemr.bootstrap.php`, `interface/modules/zend_modules/module/Installer/`.

**Billing / documents:** `interface/billing/`, `src/Billing/`, `controllers/C_Document.class.php`, `src/Services/DocumentService.php`, `interface/modules/zend_modules/module/Documents/`.

**In-repo docs:** `CLAUDE.md` (authoritative coding standards), `CONTRIBUTING.md`, `README.md`, `API_README.md`, `FHIR_README.md`, `DOCKER_README.md`, `README-Isolated-Testing.md`, `tests/Tests/README.md`, `db/README.md`.

---

## 18. Mental model summary

Treat OpenEMR as **two codebases stapled together**:

- **Modern half** (`src/`, Twig, Symfony DI, EventDispatcher, PHPStan max, Doctrine DBAL) — write code here. Services extend `BaseService`. Controllers stay thin. Modules subscribe to events. UUIDs flow through the registry. Logging is PSR-3 with context arrays.
- **Legacy half** (`interface/`, `library/`, `controllers/`, Smarty, `$GLOBALS`, `$_SESSION`, ADODB, raw SQL) — what the user sees. Read constantly, patch surgically, **never extend its patterns**. When you must edit it, bridge into `src/` for new logic, then call from the legacy file.

The goal of every change is to **leave the modern half larger and cleaner** while keeping the legacy half functional. PHPStan + custom rules + Rector + the Twig render-test harness are the safety net — run them locally before committing.

---

## Appendix A — Changes from v1

- **Removed:** Reference to `src/Modules/` (that namespace does not exist; modules live at `interface/modules/`).
- **Corrected:** Smarty's role — limited to `library/classes/Controller.class.php` + `controllers/C_*.class.php`. Most templates are Twig.
- **Added — boot:** Full 14-step `interface/globals.php` boot sequence; `public/index.php` + `FallbackRouter` rewrites + sensitive-directory blocklist.
- **Added — APIs:** Exact 10-subscriber order in `ApiApplication`; route counts (96 standard / 71 FHIR / 5 portal); standard + FHIR + portal resource enumerations.
- **Added — legacy router:** `controller.php` whitelist (10 `C_*` controllers).
- **Added — extensibility:** Specific event names (`MenuEvent::*`, `ServiceSaveEvent::*`, `RestApi*Event`, `LoadEncounterFormFilterEvent`, `TwigEnvironmentEvent::EVENT_CREATED`, `ScriptFilterEvent`, `StyleFilterEvent`, etc.).
- **Added — modules:** Full Laminas catalog with routes; full custom-module catalog with namespaces and integration points.
- **Added — forms:** Encounter form catalog (~35 forms with titles/notes), `FormLocator`, `LoadEncounterFormFilterEvent`, `library/registry.inc.php`, `registry` table.
- **Added — output safety:** `text()` / `attr()` / `xlt()` / `xla()` / `js_escape()` and their library-side backers.
- **Added — menu data:** Menu JSON files (`standard.json`, `front_office.json`, `answering_service.json`, `chart_review.json`); patient menus; site-custom-menu location.
- **Added — DB:** `users_secure`, `ar_session`, `ar_activity`, `payments`, `procedure_order`, `procedure_result`, `uuid_mapping`, `modules*`, `registry`, `globals`, `user_settings`, `list_options`, `onsite_portal_activity`, `patient_access_onsite`, `background_services`. Plus `ConnectionManager` + `config/database.php`.
- **Added — runtime:** Version constants from `version.php` (`8.1.1-dev`, DB 538, ACL 13).
- **Added — testing:** PHPUnit configuration split (`phpunit-isolated.xml` / `phpunit.xml` / `phpunit.integration.xml`).
- **Added — CLI:** `bin/console --skip-globals`; `bin/command-runner` is older.
- **Added — site state:** `sites/default/sqlconf.php` ships with `$config = 0` (uninstalled until setup); `OEGlobalsBag` mirrors values into `$GLOBALS`.
