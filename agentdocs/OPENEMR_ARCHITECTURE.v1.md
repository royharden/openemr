# OpenEMR Architecture — Agent Onboarding Guide

> **Audience:** AI coding agents who need to ramp up on OpenEMR fast in order to ship code changes safely.
> **Scope:** Everything inside `./openemr/`. This is a 20+ year-old PHP codebase mid-migration from procedural legacy → modern PSR-4 / Symfony / Twig.
> **Read this first**, then jump to the section you need. Cross-reference [CLAUDE.md](../CLAUDE.md) for coding standards (it is authoritative on style).

---

## 1. TL;DR — The 60-second model

OpenEMR is a self-hosted Electronic Medical Record + Practice Management web app. It runs on PHP 8.2+ / MySQL, exposes a REST API, a FHIR R4 (US Core 3.1.0) API, SMART-on-FHIR OAuth2, and a SOAP-ish CDA pipeline. The codebase has **two layers**:

| Layer | Where | Style | Status |
|---|---|---|---|
| **Modern** | `src/` (PSR-4 `OpenEMR\…`), `templates/*.twig`, `db/Migrations/` | DI, Symfony components, Twig, strict types, PHPStan level 10 | Where new code goes |
| **Legacy** | `interface/`, `library/`, `*.php` at repo root, Smarty templates | Procedural, `$GLOBALS`, `$_SESSION`, ADODB | Still ~70% of runtime; do not extend, but you will read it constantly |

**The two layers talk through:** `library/sql.inc.php` (legacy DB) ↔ `src/Common/Database/QueryUtils` (modern DB), `$GLOBALS` ↔ `OEGlobalsBag`, Smarty ↔ Twig. New service classes extend `OpenEMR\Services\BaseService`. The Symfony `EventDispatcher` on the `Kernel` is the canonical extension point.

**Entry points (top-level PHP files):**

| File | Role |
|---|---|
| `index.php` | Front controller. Detects site, sets `$_SESSION['site_id']`, redirects to login or setup. |
| `controller.php` | Modern router → `src/Controllers/Interface/`, `src/Controllers/Portal/`. Handles HTTP exceptions and ACL denials. |
| `bootstrap.php` | Minimal CLI bootstrap (autoloader, env, error handler). Used by `bin/console`. |
| `setup.php` | Install wizard (states 0–7: perms, DB, PHP/web check, theme). |
| `sql_upgrade.php`, `sql_patch.php` | Run after a version bump to apply schema deltas under `sql/`. |
| `acl_upgrade.php`, `ippf_upgrade.php` | Specialized upgrade scripts (ACL system, IPPF locale). |
| `admin.php` | Multi-site admin UI. |
| `_rest_routes.inc.php` | Loader that pulls `apis/routes/*.inc.php`. |

---

## 2. Directory map (what lives where)

```
openemr/
├── src/                # Modern PSR-4 (OpenEMR\…)               ← write new code here
├── library/            # Legacy procedural helpers              ← read-mostly
├── interface/          # Legacy web UI (PHP screens by domain)  ← read-mostly
├── portal/             # Patient portal (mostly independent)
├── apis/               # REST/FHIR dispatcher + route maps
├── oauth2/             # OAuth2 authorization server endpoints
├── swagger/            # Swagger UI assets for API docs
├── templates/          # Twig (modern) + a little Smarty (legacy)
├── sql/                # Master schema + version-pair upgrade scripts
├── db/                 # Doctrine Migrations (experimental, not yet primary)
├── tests/              # PHPUnit, Panther E2E, isolated, custom PHPStan rules
├── docker/             # Compose flavors: development-easy, light, redis, insane, production
├── docker/development-easy/   # Default local dev environment
├── public/             # Static assets, generated CSS, third-party JS
├── bin/                # bin/console (Symfony Console), command-runner
├── cli/                # Doctrine ORM/Migrations CLI (experimental)
├── ccdaservice/        # Node service for CCDA generation/parsing
├── ccr/                # Continuity of Care Record helpers
├── controllers/        # Slim shims; most modern controllers live in src/Controllers/
├── contrib/            # Community add-ons, code-system data (icd9/10, snomed, rxnorm)
├── custom/             # Per-site customizations (mostly empty by default)
├── sites/default/      # Per-instance config + document storage
│   ├── sqlconf.php     # DB credentials
│   ├── documents/      # Patient chart files (organized by patient/encounter)
│   └── logs/
├── modules/            # Holds modules registered with Composer
├── meta/               # Metadata (version, dist info)
├── ci/                 # CI helper scripts
├── docker-version, version.php  # Version constants
├── package.json, composer.json, gulpfile.js  # Build tooling
└── CLAUDE.md           # Coding standards (authoritative)
```

**Multi-site:** OpenEMR can host many practices on one install. Each `sites/<site_id>/sqlconf.php` points to a separate DB. `index.php` resolves `$_SERVER['HTTP_HOST']` → `site_id`.

---

## 3. Technology stack (snapshot)

- **Runtime:** PHP 8.2+, Node 24+ (build only), MySQL/MariaDB
- **Backend frameworks:** Laminas MVC (legacy modules), Symfony components (HttpKernel, EventDispatcher, Console, DI, HttpFoundation), Doctrine DBAL 4.x + Migrations
- **Frontend:** Bootstrap 4.6, jQuery 3.7, Angular 1.8 (yes, AngularJS), SASS via Gulp 4
- **Templates:** Twig 3.x (modern, majority), Smarty 4.5 (legacy, shrinking)
- **DB access:** ADODB legacy surface API in `library/sql.inc.php`; `OpenEMR\Common\Database\QueryUtils` for new code; both ultimately route through Doctrine DBAL 4
- **Testing:** PHPUnit 11, Symfony Panther (E2E), Jest 29
- **Static analysis:** PHPStan level 10 (`max`), Rector, custom rules in `tests/PHPStan/Rules/`
- **API protocols:** REST (proprietary `/api/`), FHIR R4 US Core 3.1.0, SMART-on-FHIR, OAuth2/OIDC, optional CDS Hooks

---

## 4. Modern code (`src/`) — the namespace map

`src/` is the strategic future of the codebase. New code goes here. Everything is PSR-4 under the `OpenEMR\` prefix.

### 4.1 Core infrastructure

| Path | Role |
|---|---|
| `src/Core/Kernel.php` | App kernel: Symfony DI `ContainerBuilder` + `EventDispatcher` + path accessors. |
| `src/Core/OEGlobalsBag.php` | Type-safe replacement for `$GLOBALS`. Use `getString()` / `getInt()` / `getBoolean()` instead of casting. |
| `src/Core/OEHttpKernel.php` | Symfony HttpKernel for HTTP request handling. |
| `src/Core/ModulesApplication.php`, `ModulesClassLoader.php` | Module discovery + PSR-4 autoload registration. |
| `src/Core/AbstractModuleActionListener.php` | Base class modules extend to subscribe to events. |
| `src/BC/ServiceContainer.php` | Static facade used by legacy code to get a logger, DB connection, clock, PSR-7/17 factory, crypto. Bridge to DI without forcing legacy code to know about the container. |
| `src/BC/DatabaseConnectionFactory.php` | Centralized DB connection creation; never `new` a connection directly. |

### 4.2 Service layer (`src/Services/`)

The largest single area in `src/`. ~75+ services, each typically extending `OpenEMR\Services\BaseService`.

`BaseService` provides:
- CRUD against a `TABLE_NAME`
- FHIR search (`FhirSearchWhereClauseBuilder`)
- UUID registry handling (some entities have both `id` and `uuid`)
- Event dispatch hooks (lifecycle: created/updated/deleted/viewed)
- Pagination (`QueryPagination`), field selection, auto-increment

**Service categories you will hit:**
- **Clinical:** `PatientService`, `EncounterService`, `AppointmentService`, `ConditionService`, `AllergyIntoleranceService`, `CarePlanService`, `CareTeamService`, `MedicationService`, `ImmunizationService`, `ObservationService`, `ProcedureService`
- **Documents/Media:** `DocumentService`, `PatientDocumentsService`, `Cda/*` (CCDA generation)
- **Pharmacy/Rx:** `DrugService`, prescription services
- **Billing:** `PaymentProcessingService`, `PaymentGatewayService`, claim builders (most billing logic lives in `src/Billing/`, not `src/Services/`)
- **Auth/User:** `UserService`, `FacilityService`, `InsuranceService`
- **Shared:** `AddressService`, `ContactService`, `CodeTypesService`, `BackgroundService`
- **FHIR export:** `FhirExportServiceLocator` maps a resource type to its exporter

**Pattern — defining a new service:**
```php
namespace OpenEMR\Services;
class ExampleService extends BaseService
{
    public const TABLE_NAME = "example";
    public function __construct() { parent::__construct(self::TABLE_NAME); }
}
```

### 4.3 Common (`src/Common/`)

Cross-cutting infrastructure:

| Subpackage | What it gives you |
|---|---|
| `Database/` | `QueryUtils` (escaping, prepared statements, table introspection), `QueryPagination`, `DatabaseQueryTrait` |
| `Auth/` | `AuthUtils`, OAuth2 key config, OIDC, MFA (`MfaUtils`) |
| `Acl/` | `AclMain::aclCheckCore(...)` — the canonical permission gate |
| `Logging/` | PSR-3-compliant logger; `SystemLoggerAwareTrait`; `EventAuditLogger` for HIPAA audit log |
| `Crypto/` | Encryption wrappers; key management |
| `Http/` | `Psr17Factory`, `HttpRestRequest` |
| `Twig/` | Twig environment setup, custom filters/functions |
| `Session/` | PSR session abstraction |
| `Uuid/` | `UuidRegistry` — maps integer IDs ↔ UUIDs for FHIR |
| `Csrf/` | CSRF token generation/validation |
| `Forms/`, `Utils/`, `System/` | Validation, array/date helpers, settings accessors |

### 4.4 REST and FHIR

- **`src/RestControllers/`** — REST endpoint handlers. `ApiApplication.php` is the Symfony HttpKernel that wires up auth/CORS/exception listeners (`Subscriber/`). Per-resource controllers (`PatientRestController`, `EncounterRestController`, …).
- **`src/FHIR/`** — FHIR R4 resource classes (autogenerated PHPFHIR), `DomainModels/` mapping clinical entities → FHIR, `Export/` serializers, `SMART/` for SMART-on-FHIR launch flows. Service interfaces: `IResourceSearchableService`, `IResourceCreatableService`, `IResourceReadableService`, `IResourceUpdateableService`, `IPatientCompartmentResourceService`, `IFhirExportableResourceService`.
- **Wiring:** REST routes live in `apis/routes/_rest_routes_*.inc.php`; the dispatcher is `apis/dispatch.php`; route handlers delegate to `src/RestControllers/` → `src/Services/` → `src/FHIR/Export/` for FHIR responses.

### 4.5 Events (`src/Events/`)

Symfony EventDispatcher event classes. Domain-grouped: `Appointments/`, `Billing/`, `Encounter/`, `Facility/`, `Patient/`, `PatientDemographics/`, `PatientDocuments/`, `PatientReport/`, `PatientPortal/`, `PatientFinder/`, `PatientSelect/`, `CDA/`, `Codes/`, `Messaging/`, `Globals/`, `Main/`, `Core/`, `Command/`. Plus `AbstractBoundFilterEvent` + `BoundFilter` for dynamic WHERE-clause filters.

**Modules subscribe to these events to add behavior** (audit, alerts, custom validation, menu items). This is the primary extensibility seam — favor it over editing core.

### 4.6 Domain subsystems

| Path | Domain |
|---|---|
| `src/Billing/` | Claims (X12 837), HCFA-1500, ERA (835), payment gateway, AR/daysheet reports |
| `src/Cqm/` | Clinical Quality Measures, QDM 5.5/5.6, QRDA III generation for CMS reporting |
| `src/Encounter/` | Encounter notes, problem lists, assessments |
| `src/Pharmacy/`, `src/Rx/` | Prescription / dispensing / refills |
| `src/Health/` | Health maintenance, immunizations |
| `src/Reminder/` | Clinical reminders & alert rule engine |
| `src/ClinicalDecisionRules/` | CDS Hooks integration |
| `src/Pdf/` | Clinical document PDF rendering |
| `src/Telemetry/` | Anonymized usage metrics (`TelemetryListener`) |
| `src/USPS/` | Address normalization via USPS API |
| `src/Easipro/` | EasiPRO / PROMIS patient-reported outcomes |
| `src/PaymentProcessing/` | Card processing, subscriptions |
| `src/Validators/` | `ProcessingResult` standard wrapper for validation/operation outcomes |
| `src/Gacl/` | OpenEMR's GACL (Group ACL) implementation |
| `src/MedicalDevice/`, `src/Encryption/`, `src/Forms/`, `src/Menu/`, `src/Patient/`, `src/Tabs/`, `src/Tools/`, `src/Console/`, `src/OeUI/`, `src/Controllers/` | (As named.) |

---

## 5. Legacy code (`library/`, `interface/`)

You will read this code daily. Do not extend its patterns; bridge into `src/` instead.

### 5.1 `library/` — procedural helpers

**Files you will hit constantly:**

| File | Role |
|---|---|
| `library/sql.inc.php` | Legacy DB API (ADODB-style: `sqlStatement`, `sqlQuery`, `sqlInsert`, `sqlFetchArray`). Globally available after `interface/globals.php` is required. |
| `library/auth.inc.php` | Session/auth bootstrap. Side-effect: requires login or kicks to `login.php`. |
| `library/acl.inc.php` | Legacy ACL gates. Modern code should call `OpenEMR\Common\Acl\AclMain::aclCheckCore()` instead. |
| `library/options.inc.php` | Generates the giant select/text/codes form-widgets used across UI. Reads `list_options` table. |
| `library/patient.inc.php` | Patient demographics/insurance/contact retrieval. |
| `library/appointments.inc.php` | Calendar appointment CRUD. |
| `library/payment.inc.php` | Payment posting / adjustments. |
| `library/log.inc.php` | Audit log helpers (writes to `log` and `audit_master`). |

**Subdirectories:** `classes/` (legacy OOP — Document, Note, Person, Controller, CouchDB), `ajax/` (XHR endpoints), `admin/`, `ESign/`, `MedEx/`, `smarty/`, `smarty_legacy/`, `validation/`.

### 5.2 `interface/` — legacy web UI

Each subdirectory is a user-facing area. Most files include `interface/globals.php` first to set up session/auth/`$GLOBALS`.

| Subdirectory | Area |
|---|---|
| `login/` | Login screens, password reset |
| `main/` | Dashboard, **`main/calendar/`** (the scheduler), dated reminders |
| `patient_file/` | Patient charts, encounter creation, demographics, history |
| `forms/`, `forms_admin/` | Encounter forms (SOAP, vitals, ROS, custom) and form builder |
| `billing/` | Claims, EOB processing, fee sheet, insurance |
| `practice/` | Facility/insurance/pharmacy admin, address verify |
| `reports/` | Clinical and financial reports |
| `super/` | Superuser admin: ACL, users, global settings |
| `patient_tracker/` | Wait-list / flow board |
| `orders/` | Lab and imaging orders |
| `drugs/`, `code_systems/` | Drug DB and ICD/SNOMED/RxNorm tools |
| `themes/` | Theme SCSS sources (Gulp compiles → `public/themes/`) |
| `fax/`, `batchcom/` | Fax dispatch, batch comms |
| `esign/` | E-signature workflow |
| `usergroup/` | Group / department mgmt |
| `modules/` | Module mount points (see §7) |
| `smart/` | SMART-on-FHIR app launch UI |

### 5.3 `portal/` — patient portal

Mostly independent of `/interface/`. Patients log in here for appointments, secure messaging, record review, document signing. Subdirs: `account/`, `patient/`, `messaging/`, `report/`, `sign/`, `lib/`.

### 5.4 `templates/` — Twig + Smarty

Twig dominates (`*.twig` everywhere). Subfolders: `login/`, `core/`, `portal/`, `emails/`, `interface/`, `documents/`, `reports/`, `encounters/`, `oauth2/`, `api/`. Render tests live in `tests/Tests/Isolated/Common/Twig/fixtures/render/` — **after editing a template with render coverage, run `composer update-twig-fixtures`** and review the diff.

Legacy Smarty templates live under `library/smarty_legacy/` and `library/smarty/`. New templates always Twig.

---

## 6. APIs — REST, FHIR, OAuth2, SMART

### 6.1 Layout

```
apis/
├── dispatch.php                         # Front controller for all REST/FHIR
└── routes/
    ├── _rest_routes_standard.inc.php    # Proprietary OpenEMR REST routes
    ├── _rest_routes_fhir_r4_us_core_3_1_0.inc.php  # FHIR R4 / US Core 3.1.0
    └── _rest_routes_portal.inc.php      # Patient portal endpoints
oauth2/
└── authorize.php                        # OAuth2 authorization server entry
swagger/                                 # Swagger UI for browsing the API
```

### 6.2 Request flow

1. HTTP request hits `apis/dispatch.php`.
2. Routes resolved from `_rest_routes_*.inc.php` (route map: `METHOD path => handler`).
3. `src/RestControllers/ApiApplication.php` (Symfony HttpKernel) runs middleware chain via `Subscriber/`:
   - `AuthorizationListener`, `OAuth2AuthorizationListener` — token validation, scope check
   - `CORSListener` — CORS
   - `ExceptionHandlerListener` — uniform error envelope
   - `ApiResponseLoggerListener`, `TelemetryListener` — observability
4. Controller calls a `OpenEMR\Services\…Service`.
5. For FHIR: response goes through `src/FHIR/Export/` serializers; the resource service returns a `ProcessingResult`.

### 6.3 OAuth2 / SMART

`src/Common/Auth/OpenIDConnect/`, `src/FHIR/SMART/` implement OAuth2 + OIDC + SMART app launch. `oauth_clients`, `oauth_trusted_user`, `jwt_grant_history` tables persist client registration and consents.

### 6.4 Reference docs

`API_README.md` (proprietary REST) and `FHIR_README.md` (FHIR R4 / US Core) at the repo root. Swagger UI under `/swagger/` renders OpenAPI specs from `src/RestControllers/`.

---

## 7. Modules and extensibility

OpenEMR has **two parallel module systems**. New modules should use the modern one.

### 7.1 Modern (Symfony-based) — `interface/modules/custom_modules/`

Pattern: `oe-module-<name>`. Shipping modules:

- `oe-module-claimrev-connect` — claims review
- `oe-module-comlink-telehealth` — telehealth
- `oe-module-dashboard-context` — dashboards
- `oe-module-dorn` — dental specifics
- `oe-module-ehi-exporter` — EHI bulk export
- `oe-module-faxsms` — fax/SMS gateway
- `oe-module-prior-authorizations` — prior auth workflow
- `oe-module-weno` — Weno pharmacy integration

**Module skeleton:**
```
oe-module-foo/
├── openemr.bootstrap.php   # PSR-4 namespace registration
├── moduleConfig.php        # Settings page (rendered in iframe)
└── src/
    └── Bootstrap.php       # Subscribes to events; registers menu/ACL/routes
```

**How the module hooks in:**
- `ModulesClassLoader` registers PSR-4 namespace
- `Bootstrap` constructor receives the `EventDispatcherInterface` and Twig env
- Subscribes to events like `MenuEvent`, `GlobalsInitializedEvent`, `PatientDemographics\RenderEvent`, etc.
- Adds ACL entries via `OpenEMR\Common\Acl\AclMain`
- Adds REST routes by registering against the API route map
- Migrations either via `db/Migrations/` (Doctrine) or inline SQL during install

### 7.2 Legacy (Laminas/Zend) — `interface/modules/zend_modules/module/`

Each module has its own `Module.php` implementing Laminas MVC `onBootstrap(MvcEvent $e)` + `getConfig()` / `getServiceConfig()` / `getAutoloaderConfig()`. Shipping: `Acl`, `Application`, `Carecoordination`, `Ccr`, `CodeTypes`, `Documents`, `FHIR`, `Immunization`, `Installer`, `PatientFilter`, `PatientFlowBoard`, `Patientvalidation`, `PrescriptionTemplates`, `Syndromicsurveillance`. Touch only when fixing existing behavior; do not add new Laminas modules.

### 7.3 `contrib/` and `custom/`

- `contrib/` — community add-ons + code-system data (ICD-9/10, SNOMED, RxNorm) + extra encounter forms
- `custom/` — site-specific overrides; mostly empty in vanilla checkout

---

## 8. Database

### 8.1 Schema location

- **Master:** `sql/database.sql` — 281 `CREATE TABLE` statements; the source-of-truth schema applied by the installer.
- **Version-pair upgrades:** `sql/<from>-to-<to>_upgrade.sql` (e.g., `8_0_0-to-8_1_0_upgrade.sql`). `sql_upgrade.php` walks these in order during version bumps.
- **Doctrine Migrations:** `db/Migrations/Version*.php` — present but **experimental**, not the primary migration mechanism yet (per `db/README.md`). Long-term direction.
- **CLI:** `bin/console` (preferred); `cli/` exposes Doctrine ORM/migrations commands (experimental).

### 8.2 Tables grouped by domain

| Domain | Representative tables |
|---|---|
| Patient demographics | `patient_data`, `addresses`, `history_data`, `insurance_data`, `employer_data`, `person`, `contact`, `contact_relation` |
| Encounters / forms | `form_encounter`, `forms`, `form_soap`, `form_vitals`, `form_vital_details`, `form_clinical_notes`, `form_reviewofs`, `form_ros` |
| Prescriptions / drugs | `drugs`, `drug_inventory`, `drug_sales`, `drug_templates`, `erx_rx_log`, `erx_narcotics` |
| Billing / insurance | `claims`, `billing`, `fee_schedule`, `fee_sheet_options`, `benefit_eligibility`, `insurance_companies` |
| Scheduling | `openemr_postcalendar_events`, `care_teams`, `care_team_member` |
| Audit / logging | `audit_master`, `audit_details`, `api_log`, `direct_message_log`, `log` |
| ACL / users | `users`, `groups`, `gacl_*` (~25 tables) |
| FHIR / OAuth2 | `uuid_registry`, `oauth_clients`, `oauth_trusted_user`, `jwt_grant_history` |
| Codes / lists | `codes`, `lists`, `clinical_plans`, `clinical_rules`, `questionnaire_*`, `form_questionnaire_assessments` |

**Always look up canonical column names by `grep "CREATE TABLE \`<name>\`" sql/database.sql -A 60`.**

### 8.3 Reading data

- Modern: `OpenEMR\Common\Database\QueryUtils::fetchRecords($sql, $bindings)` + `QueryPagination`.
- Legacy: `sqlStatement`, `sqlQuery`, `sqlInsert`, `sqlFetchArray` from `library/sql.inc.php`.
- Both ultimately use Doctrine DBAL 4. **Never** instantiate a connection directly — use `DatabaseConnectionFactory` (`src/BC/`).

### 8.4 UUIDs

Many entities have both an integer `id` and a UUID. The `uuid_registry` table maps them. Use `OpenEMR\Common\Uuid\UuidRegistry` (do not roll your own UUID generation — FHIR exposure depends on the registry).

---

## 9. Auth, ACL, security

- **Login:** `interface/login/login.php` → `library/auth.inc.php`. MFA via `OpenEMR\Common\Auth\MfaUtils`.
- **Session:** PHP session, but **do not write `$_SESSION` directly in new code** — PHPStan rule `ForbiddenDirectSessionWriteRule` will fail the build. Use the framework session abstraction.
- **ACL:** `OpenEMR\Common\Acl\AclMain::aclCheckCore($section, $value, $user, $return_value)`. Backed by GACL (`src/Gacl/`) and the `gacl_*` tables.
- **OAuth2 / OIDC / SMART:** `src/Common/Auth/OpenIDConnect/`, `src/FHIR/SMART/`, `oauth2/authorize.php`. Scopes enforced by `OAuth2AuthorizationListener`.
- **Audit log:** HIPAA audit goes to `audit_master`/`audit_details` via `OpenEMR\Common\Logging\EventAuditLogger`. Touchy patient data → audit it.
- **Crypto:** `OpenEMR\Common\Crypto\CryptoGen` for column/document encryption. Keys live under `sites/<id>/documents/logs_and_misc/methods/` (do not commit).
- **CSRF:** `OpenEMR\Common\Csrf\CsrfUtils::collectCsrfToken()` / `verifyCsrfToken()`.

---

## 10. Coding standards (the parts you'll trip over)

Read [CLAUDE.md](../CLAUDE.md) for the full list. Most-cited rules:

1. **`declare(strict_types=1);`** at the top of every new PHP file.
2. **Native types on every parameter, property, return.** PHPDoc only for things native types can't express.
3. **Use `OEGlobalsBag`** instead of `$GLOBALS`. Use typed getters: `getString`, `getInt`, `getBoolean`.
4. **Use `QueryUtils`** instead of raw `mysqli_*` or fresh `new` connections.
5. **Inject dependencies** through the constructor. No service locators in business logic. No `new Service()` — register in DI container.
6. **Catch `\Throwable`, not `\Exception`.** Custom PHPStan rule enforces this.
7. **PSR-3 logging context arrays** — never interpolate values into the message string. `$logger->error('msg', ['phone' => $phone])`.
8. **No `eval`, no `exec/system/shell_exec`, no direct `curl_*`.** Use Guzzle. Custom rules block these.
9. **`match` on enums without `default`** — preserves PHPStan exhaustiveness.
10. **Domain primitives** for IDs (`PatientId`, `EncounterId`) so `approveOrder($userId, $orderId)` becomes `approveOrder(ClinicalUser $u, OrderId $o)`.
11. **`DateTimeImmutable`** always; `readonly` for value objects.
12. **No `@phpstan-ignore` to silence errors**, no inline `@var` casts. Fix at the source.

### Custom PHPStan rules (`tests/PHPStan/Rules/`)
`ForbidGlobalKeywordRule`, `ForbiddenGlobalsAccessRule`, `ForbiddenCatchTypeRule`, `ForbiddenShellExecutionRule`, `ForbiddenCurlFunctionsRule`, `ForbiddenEvalRule`, `ForbiddenDirectSessionWriteRule`, `ForbiddenRequestGlobalsRule`, `ForbiddenInstantiationsRule`, `OEGlobalsBagTypedGetterRule`, … 18 in total. Registered in `.phpstan/extension.neon`.

---

## 11. Build, test, and CI

### 11.1 Local dev

```bash
cd docker/development-easy
docker compose up --detach --wait
# App:        http://localhost:8300/   (https://localhost:9300/)
# admin/pass
# phpMyAdmin: http://localhost:8310/
```

Other Docker flavors (`docker/`):
- `development-easy` (default), `development-easy-light` (slimmer), `development-easy-redis` (with Redis), `development-insane` (load testing), `production`.

### 11.2 Tests

| Command (run from `docker/development-easy/`) | What |
|---|---|
| `docker compose exec openemr /root/devtools clean-sweep-tests` | All tests |
| `… unit-test` | PHPUnit unit |
| `… api-test` | REST API |
| `… e2e-test` | Symfony Panther E2E |
| `… services-test` | Service layer |
| `composer phpunit-isolated` (host) | Isolated tests, no Docker/DB |
| `composer update-twig-fixtures` (host) | Regenerate Twig render fixtures |
| `npm run test:js` | Jest |

Test layout: `tests/Tests/{Unit,Api,E2e,Services,Isolated,Common,Fixtures,Validators}` plus `tests/PHPStan/Rules/`. See `tests/Tests/README.md` for invocation guidance.

### 11.3 Quality (host-side)

```bash
composer code-quality          # phpcs + phpstan + rector + …
composer phpstan               # level 10 max
composer phpcs / phpcbf        # style check / autofix
composer rector-check / rector-fix
composer require-checker
composer codespell
composer conventional-commits:check
composer php-syntax-check
npm run lint:js / lint:js-fix
npm run stylelint
```

PHPStan **must always run on the full codebase**, then filter for changed files — type inference is whole-program.

### 11.4 Build

```bash
npm run build       # production: Gulp compiles SCSS → public/themes/
npm run dev         # watch
npm run gulp-build  # build only, no watch
```

Gulp sources: `interface/themes/tabs_style_*.scss`, `interface/themes/oe-styles/`, `interface/themes/colors/` → `public/themes/` and `public/assets/`.

### 11.5 CI (`.github/workflows/`, 30+ workflows)

`test.yml`, `api-test.yml`, `isolated-tests.yml`, `e2e-test.yml`, `phpstan.yml`, `phpstan-baseline-diff.yml`, `styling.yml`, `conventional-commits.yml`, `spellcheck.yml`, `shellcheck.yml`, `semgrep.yml`, `database.yml`, `inferno-test.yml` (FHIR/SMART compliance), `build-dev-php-fpm-docker.yml`. Pre-commit hooks via `prek install` (or `pre-commit install`).

### 11.6 Commit messages

Conventional Commits: `<type>(<scope>): <description>` with types `feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert`. AI-assisted commits add an `Assisted-by:` trailer (e.g., `Assisted-by: Claude Code`).

---

## 12. How a feature usually flows (request → response)

A typical "show patient X's allergies via FHIR" walk-through:

1. **HTTP** `GET /apis/default/fhir/AllergyIntolerance?patient=<uuid>` hits `apis/dispatch.php`.
2. Route matched in `apis/routes/_rest_routes_fhir_r4_us_core_3_1_0.inc.php` → handler in `src/RestControllers/FHIR/`.
3. `ApiApplication` runs `OAuth2AuthorizationListener` → validates Bearer token + scope `user/AllergyIntolerance.read`. `AclMain::aclCheckCore` confirms the user can see allergies.
4. Controller calls `OpenEMR\Services\AllergyIntoleranceService::getAll(['patient' => $uuid])`.
5. `BaseService` builds a parameterized SQL query via `QueryUtils`, joining UUID via `UuidRegistry`.
6. Results returned as `ProcessingResult` of domain objects.
7. Controller hands the result to `src/FHIR/Export/FhirAllergyIntoleranceServiceMapper` (or equivalent), which builds `FHIRAllergyIntolerance` resources.
8. Response serialized via PHPFHIR (`PHPFHIRResponseParser`).
9. `ApiResponseLoggerListener` + `TelemetryListener` log the call. `EventAuditLogger` writes to `audit_master`.
10. Response returned. CORS headers applied by `CORSListener`.

A legacy UI flow (e.g., adding a vital):

1. User submits form in `interface/forms/vitals/new.php`.
2. File requires `interface/globals.php` → session/auth/`$GLOBALS` set.
3. CSRF token verified (`CsrfUtils`).
4. ACL checked via `acl_check()` (legacy) or `AclMain::aclCheckCore`.
5. Insert via `sqlInsert(...)` from `library/sql.inc.php`.
6. Audit row written via `library/log.inc.php` helpers.
7. Redirect back to the encounter view in `interface/patient_file/encounter/`.

---

## 13. Where to look for X (cheat sheet)

| You want to … | Look here |
|---|---|
| Add a service | `src/Services/<Foo>Service.php` extending `BaseService` |
| Add a REST endpoint | Route in `apis/routes/_rest_routes_standard.inc.php`; controller in `src/RestControllers/`; service in `src/Services/` |
| Add a FHIR resource | `src/FHIR/Export/`, `src/FHIR/DomainModels/`, route in `_rest_routes_fhir_r4_us_core_3_1_0.inc.php` |
| Add a clinical UI screen | `interface/<area>/`. Reuse Twig layouts in `templates/`. Wire into menu via a module event subscriber. |
| Run on every patient save | Subscribe to a `src/Events/Patient/*` event in a module Bootstrap |
| Schema change | Add a `sql/<from>-to-<to>_upgrade.sql` step (current style); long-term, add a `db/Migrations/Version*.php` Doctrine migration |
| Add a global setting | Define in the globals service; read via `OEGlobalsBag` typed getters |
| ACL-gate an action | `AclMain::aclCheckCore($section, $value)`. Add new permissions via the ACL admin UI / migration |
| Audit a patient-data action | Call `EventAuditLogger` in `src/Common/Logging/` |
| Add a Twig template | Drop under `templates/<area>/`. If it has render-test coverage, run `composer update-twig-fixtures` after edits. |
| Add a CLI command | `src/Console/`, registered in `bin/console` |
| Encrypt a column / document | `OpenEMR\Common\Crypto\CryptoGen` |
| Resolve `$GLOBALS['foo']` | `OEGlobalsBag::getString('foo')` (or `getInt`, etc.) |
| Replace a `new Service()` | Inject through constructor; configure in DI container under `src/Core/` |

---

## 14. Common gotchas

- **Two template engines** — check the file extension. `.twig` = modern, `.tpl` = Smarty. New work uses Twig.
- **Two DB APIs** — `sqlStatement` (legacy) vs `QueryUtils` (modern). Don't mix in the same function.
- **Two module systems** — Laminas (`zend_modules`) vs Symfony (`custom_modules`). New modules use Symfony.
- **`globals.php` side-effects** — many legacy files require `interface/globals.php` first. It sets `$GLOBALS`, starts session, auths the user, and pulls in `library/sql.inc.php`. Removing it breaks the file.
- **PHPStan baseline** — never add new entries; fix the type error. When editing a file, fix existing baseline entries for that file.
- **Twig render fixtures** — silent diffs in `tests/Tests/Isolated/Common/Twig/fixtures/render/`. Run `composer update-twig-fixtures` after Twig edits and review the diff.
- **`prek` / pre-commit** — install once with `prek install`. The hooks (phpstan, rector, phpcs, codespell) catch the issues you'd otherwise hit in CI.
- **Multi-site** — production deployments often run >1 site. `sites/<id>/sqlconf.php` is per-site. Anything you store outside the DB needs to be site-scoped.
- **UUIDs vs IDs** — FHIR speaks UUIDs, internal tables speak ints. Bridge with `UuidRegistry`.
- **Conventional Commits enforced in CI** — get the format right or the build fails.

---

## 15. Reference docs (in this repo)

| File | Topic |
|---|---|
| `CLAUDE.md` | **Authoritative** coding standards (PSR, types, DI, logging, PHPStan rules) |
| `CONTRIBUTING.md` | Setup + contribution workflow |
| `README.md` | Project overview |
| `API_README.md` | Proprietary REST API |
| `FHIR_README.md` | FHIR R4 / US Core implementation |
| `DOCKER_README.md` | Docker setups |
| `README-Isolated-Testing.md` | Isolated (no-Docker) test guide |
| `tests/Tests/README.md` | Testing guide |
| `db/README.md` | Doctrine migrations status |

---

## 16. Mental model summary

Treat OpenEMR as **two codebases stapled together**:

- **Modern half** (`src/`, Twig, Symfony DI, EventDispatcher, PHPStan max, Doctrine DBAL) — this is where you add code. Services extend `BaseService`. Controllers stay thin. Modules subscribe to events. UUIDs flow through the registry. Logging is PSR-3 with context arrays.
- **Legacy half** (`interface/`, `library/`, Smarty, `$GLOBALS`, `$_SESSION`, ADODB, raw SQL) — this is what the user sees. You will read it constantly and patch it surgically, but **never extend its patterns**. When you must edit it, bridge into `src/` for new logic, then call it from the legacy file.

The goal of every change is to **leave the modern half larger and cleaner** while keeping the legacy half functional. PHPStan + custom rules + Rector + the Twig render-test harness are your safety net — run them locally before committing.
