# OpenEMR Visual Architecture Guide

Audience: novice software engineers who need a clear mental model of how OpenEMR works before reading code.

Scope: this document is based on the local `openemr` codebase and focuses on clarity over exhaustive detail. OpenEMR is a large PHP application with a long-lived legacy layer and newer service/API code living beside it.

## Polished Overview Image

The generated slide-friendly overview image is stored here:

![OpenEMR main architecture overview](assets/openemr-main-architecture-overview.png)

## 1. High-Level System Architecture Overview

This C4-style context/container view shows OpenEMR as one application made of several user-facing entry points. Most requests eventually use shared PHP services, database tables, files under site storage, and optional external healthcare systems.

```mermaid
%% OpenEMR high-level architecture overview
flowchart TB
    %% People and systems outside OpenEMR
    Clinician["Clinician / Staff"]
    Patient["Patient"]
    ExtApp["External Apps<br/>FHIR / SMART / REST clients"]

    %% OpenEMR boundary
    subgraph OpenEMR["OpenEMR Application"]
        direction TB

        subgraph Entry["Entry Points"]
            WebEntrypoints["Web UI entry points<br/>index.php, interface/*"]
            Portal["Patient Portal<br/>portal/*"]
            ApiLayer["API entry points<br/>apis/*"]
            OAuth["OAuth2 / SMART auth<br/>oauth2/*"]
        end

        subgraph AppCore["Application Core"]
            LegacyUI["Legacy clinical UI<br/>interface/* pages"]
            Services["Modern PHP services<br/>src/Services, src/Common"]
            Modules["Module systems<br/>custom modules + Laminas modules"]
            SharedLib["Shared legacy libraries<br/>library/*"]
            Templates["Templates and assets<br/>templates, public, assets"]
            Config["Configuration and globals<br/>sites, globals, OEGlobalsBag"]
        end
    end

    %% Data owned by OpenEMR
    subgraph Data["OpenEMR Data"]
        DB[("MySQL / MariaDB<br/>clinical, billing, auth, config data")]
        Files[("Site files<br/>documents, logs, patient uploads")]
        Cache[("Cache / generated assets<br/>temporary runtime data")]
    end

    %% External integrations
    subgraph External["External Systems"]
        Clearinghouse["Claims clearinghouse<br/>X12 / billing exchange"]
        Labs["Labs and clinical feeds<br/>HL7 / documents"]
        FHIRClients["FHIR servers or clients"]
        Payment["Payment processors"]
        Messaging["Email / SMS / fax systems"]
        Terminology["Terminology and code sets"]
    end

    Clinician -->|"Uses browser"| WebEntrypoints
    Patient -->|"Uses browser"| Portal
    ExtApp -->|"REST, FHIR, SMART"| ApiLayer
    ExtApp -->|"OAuth2 tokens"| OAuth

    WebEntrypoints --> LegacyUI
    Portal --> Services
    ApiLayer --> Services
    OAuth --> Services

    LegacyUI --> Services
    LegacyUI --> SharedLib
    Services --> SharedLib
    Modules --> Services
    Modules --> LegacyUI
    Config --> LegacyUI
    Config --> Services
    Templates --> LegacyUI

    Services --> DB
    SharedLib --> DB
    Services --> Files
    LegacyUI --> Files
    Services --> Cache

    Services --> Clearinghouse
    Services --> Labs
    Services --> FHIRClients
    Services --> Payment
    Services --> Messaging
    Services --> Terminology

    classDef person fill:#f7f1d5,stroke:#9a7b22,color:#222;
    classDef openemr fill:#e8f1ff,stroke:#2b5aa8,color:#111;
    classDef data fill:#e7f6ea,stroke:#2e7d32,color:#111;
    classDef external fill:#f6e8ff,stroke:#7b3fa1,color:#111;

    class Clinician,Patient,ExtApp person;
    class WebEntrypoints,Portal,ApiLayer,OAuth,LegacyUI,Services,Modules,SharedLib,Templates,Config openemr;
    class DB,Files,Cache data;
    class Clearinghouse,Labs,FHIRClients,Payment,Messaging,Terminology external;
```

## 2. Component / Module Breakdown

This view zooms inside the OpenEMR application. The important idea is that OpenEMR has both legacy page-based PHP screens and newer service/API objects. Future updates often need to understand both paths.

```mermaid
%% OpenEMR internal component map
flowchart LR
    subgraph Entry["Request Entrypoints"]
        Root["index.php<br/>main login/front door"]
        Front["interface/*<br/>staff UI pages"]
        Rest["apis/*<br/>REST + FHIR routes"]
        Authz["oauth2/*<br/>OAuth2 / SMART"]
        CLI["bin / scripts<br/>CLI and maintenance tasks"]
    end

    subgraph Bootstrap["Bootstrap and Configuration"]
        Globals["globals.php<br/>legacy environment setup"]
        Kernel["src/Common/Kernel<br/>newer application kernel"]
        Router["routing and request handling"]
        Bag["OEGlobalsBag<br/>runtime config access"]
        ServiceContainer["service container<br/>dependency wiring"]
    end

    subgraph UI["User-Facing PHP UI"]
        MainUI["main screen shell"]
        PatientChart["patient chart and demographics"]
        Forms["clinical forms and encounters"]
        BillingUI["billing and claims screens"]
        ReportsUI["reports"]
        AdminUI["admin, users, globals"]
        PortalUI["patient portal"]
    end

    subgraph API["API Surface"]
        ApiApp["API application bootstrap"]
        Subscribers["API middleware / subscribers"]
        RestControllers["REST controllers"]
        FhirControllers["FHIR controllers"]
        Smart["SMART launch and OAuth flows"]
    end

    subgraph Business["Business Logic"]
        Services["src/Services<br/>clinical and admin services"]
        FhirServices["FHIR services and resources"]
        Billing["billing, claims, payments"]
        CDR["clinical decision rules"]
        CQM["quality measure logic"]
        Common["src/Common<br/>shared infrastructure"]
    end

    subgraph Modules["Extension Points"]
        CustomModules["interface/modules/custom_modules"]
        LaminasModules["interface/modules/zend_modules"]
        Events["event dispatching hooks"]
    end

    subgraph Data["Persistence and Storage"]
        Sql["sql/*<br/>schema, upgrades, reference data"]
        DB["database access helpers<br/>legacy sql* helpers + newer patterns"]
        SiteFiles["sites/*<br/>per-site documents and config"]
        Schema["database migrations<br/>Doctrine migration scaffolding"]
    end

    Root --> Globals
    Front --> Globals
    Rest --> Kernel
    Authz --> Kernel
    CLI --> Globals

    Globals --> Bag
    Kernel --> ServiceContainer
    Kernel --> Router
    ServiceContainer --> Services

    Globals --> MainUI
    MainUI --> PatientChart
    MainUI --> Forms
    MainUI --> BillingUI
    MainUI --> ReportsUI
    MainUI --> AdminUI
    PortalUI --> Services

    Router --> ApiApp
    ApiApp --> Subscribers
    Subscribers --> RestControllers
    Subscribers --> FhirControllers
    Authz --> Smart
    Smart --> FhirControllers

    PatientChart --> Services
    Forms --> Services
    BillingUI --> Billing
    ReportsUI --> Services
    AdminUI --> Services

    RestControllers --> Services
    FhirControllers --> FhirServices
    Services --> Common
    FhirServices --> Common
    Billing --> Common
    CDR --> Services
    CQM --> Services

    CustomModules --> Events
    LaminasModules --> Events
    Events --> Services
    Events --> UI

    Services --> DB
    Billing --> DB
    FhirServices --> DB
    DB --> Sql
    DB --> Schema
    Services --> SiteFiles
    UI --> SiteFiles

    classDef entry fill:#fff3e0,stroke:#ef6c00,color:#111;
    classDef boot fill:#e3f2fd,stroke:#1565c0,color:#111;
    classDef ui fill:#f3e5f5,stroke:#6a1b9a,color:#111;
    classDef api fill:#e0f7fa,stroke:#00838f,color:#111;
    classDef biz fill:#e8f5e9,stroke:#2e7d32,color:#111;
    classDef mod fill:#fce4ec,stroke:#ad1457,color:#111;
    classDef store fill:#eeeeee,stroke:#424242,color:#111;

    class Root,Front,Rest,Authz,CLI entry;
    class Globals,Kernel,Router,Bag,ServiceContainer boot;
    class MainUI,PatientChart,Forms,BillingUI,ReportsUI,AdminUI,PortalUI ui;
    class ApiApp,Subscribers,RestControllers,FhirControllers,Smart api;
    class Services,FhirServices,Billing,CDR,CQM,Common biz;
    class CustomModules,LaminasModules,Events mod;
    class Sql,DB,SiteFiles,Schema store;
```

## 3. Data Flow and Key Processes

This diagram shows the common path for a request: choose the site, bootstrap configuration, authenticate if needed, route to either legacy UI or API code, use services/libraries, then write data and return a response.

```mermaid
%% Common request and data flow through OpenEMR
flowchart TD
    Start["Request arrives<br/>browser, portal, API client, or script"]
    SiteDecision{"Which OpenEMR site?"}
    Installed{"Is the site installed<br/>and configured?"}
    Setup["Setup or upgrade workflow"]
    Bootstrap["Load globals, paths, autoloaders,<br/>configuration, and site settings"]
    AuthDecision{"Does this route need<br/>authentication or authorization?"}
    Login["Login, session, OAuth2,<br/>or SMART authorization"]
    AuthOK{"Access allowed?"}
    Deny["Return login screen,<br/>401, 403, or error"]

    RouteDecision{"What kind of request?"}
    UIPage["Legacy staff UI page<br/>interface/*"]
    PortalPage["Patient portal page"]
    APIKernel["REST / FHIR API kernel"]
    ModuleBootstrap["Module hook or module route"]

    FormFlow["Read request fields<br/>validate and normalize input"]
    ServiceCall["Call service layer<br/>or shared library functions"]
    LegacyLib["Legacy library helpers<br/>database, ACL, forms, billing"]
    Controller["API controller or FHIR handler"]
    ResponseRender["Render HTML, JSON,<br/>FHIR resource, redirect, or file"]

    DB[("Database")]
    Files[("Site files and documents")]
    Audit[("Audit / logs")]
    Events["Module events and hooks"]
    End["Response returned to caller"]

    Start --> SiteDecision
    SiteDecision --> Installed
    Installed -- "No" --> Setup
    Setup --> Bootstrap
    Installed -- "Yes" --> Bootstrap
    Bootstrap --> AuthDecision
    AuthDecision -- "Yes" --> Login
    AuthDecision -- "No" --> RouteDecision
    Login --> AuthOK
    AuthOK -- "No" --> Deny
    AuthOK -- "Yes" --> RouteDecision

    RouteDecision -- "Staff UI" --> UIPage
    RouteDecision -- "Portal" --> PortalPage
    RouteDecision -- "API / FHIR" --> APIKernel
    RouteDecision -- "Module" --> ModuleBootstrap

    UIPage --> FormFlow
    PortalPage --> FormFlow
    APIKernel --> Controller
    ModuleBootstrap --> Events
    Events --> ServiceCall

    FormFlow --> ServiceCall
    ServiceCall --> LegacyLib
    Controller --> ServiceCall

    ServiceCall --> DB
    LegacyLib --> DB
    ServiceCall --> Files
    ServiceCall --> Audit
    DB --> ResponseRender
    Files --> ResponseRender
    Audit --> ResponseRender
    ResponseRender --> End
    Deny --> End

    classDef decision fill:#fff9c4,stroke:#f9a825,color:#111;
    classDef process fill:#e3f2fd,stroke:#1565c0,color:#111;
    classDef store fill:#e8f5e9,stroke:#2e7d32,color:#111;
    classDef stop fill:#ffebee,stroke:#c62828,color:#111;

    class SiteDecision,Installed,AuthDecision,AuthOK,RouteDecision decision;
    class Start,Setup,Bootstrap,Login,UIPage,PortalPage,APIKernel,ModuleBootstrap,FormFlow,ServiceCall,LegacyLib,Controller,ResponseRender,Events,End process;
    class DB,Files,Audit store;
    class Deny stop;
```

## 4. Core Object and Dependency Relationships

OpenEMR is not purely object-oriented; it mixes procedural PHP pages, shared functions, and newer classes. This class-style diagram highlights the objects and dependencies that future code changes often touch.

```mermaid
%% Core object and dependency relationships
classDiagram
    direction LR

    class GlobalsPHP {
        +loads configuration
        +sets legacy globals
        +starts app environment
    }

    class OEGlobalsBag {
        +reads global settings
        +normalizes config access
    }

    class Kernel {
        +boots modern runtime
        +connects services
        +handles API-oriented requests
    }

    class ModulesApplication {
        +discovers modules
        +registers hooks
        +connects event listeners
    }

    class EventDispatcher {
        +publishes events
        +calls module listeners
    }

    class ServiceContainer {
        +creates services
        +shares dependencies
    }

    class QueryUtils {
        +executes SQL helpers
        +wraps database access
    }

    class BaseService {
        +common service behavior
        +validation patterns
    }

    class PatientService {
        +patient demographics
        +patient search
    }

    class EncounterService {
        +encounter data
        +clinical visit context
    }

    class AppointmentService {
        +calendar appointments
        +schedule data
    }

    class DocumentService {
        +patient documents
        +file metadata
    }

    class FhirServiceLayer {
        +maps OpenEMR records
        +returns FHIR resources
    }

    class ApiApplication {
        +routes API requests
        +uses auth middleware
    }

    class RestController {
        +handles REST endpoints
    }

    class FhirController {
        +handles FHIR endpoints
    }

    class LegacyController {
        +bridges older UI patterns
    }

    class LegacyPages {
        +procedural screen scripts
        +form handlers
    }

    class CustomModule {
        +custom feature package
        +hooks into UI/events
    }

    class LaminasModule {
        +module MVC package
        +module configuration
    }

    GlobalsPHP --> OEGlobalsBag
    GlobalsPHP --> LegacyPages
    GlobalsPHP --> ModulesApplication
    Kernel --> ServiceContainer
    Kernel --> ApiApplication
    ServiceContainer --> BaseService
    BaseService <|-- PatientService
    BaseService <|-- EncounterService
    BaseService <|-- AppointmentService
    BaseService <|-- DocumentService
    PatientService --> QueryUtils
    EncounterService --> QueryUtils
    AppointmentService --> QueryUtils
    DocumentService --> QueryUtils
    FhirServiceLayer --> PatientService
    FhirServiceLayer --> EncounterService
    ApiApplication --> RestController
    ApiApplication --> FhirController
    RestController --> PatientService
    FhirController --> FhirServiceLayer
    LegacyPages --> LegacyController
    LegacyController --> PatientService
    LegacyController --> QueryUtils
    ModulesApplication --> EventDispatcher
    CustomModule --> EventDispatcher
    LaminasModule --> EventDispatcher
    EventDispatcher --> ServiceContainer
```

## 5. Sequence Diagram: Staff Opens a Patient Chart

This is one of the most important end-to-end flows: a staff user logs in, enters the main UI, opens a patient chart, and OpenEMR loads patient data from services, legacy helpers, modules, templates, and the database.

```mermaid
%% Main staff user flow: open a patient chart
sequenceDiagram
    autonumber
    actor Staff as Staff User
    participant Browser
    participant Index as index.php
    participant Login as Login / Session
    participant Globals as globals.php
    participant Auth as ACL / Auth Helpers
    participant Main as Main UI Shell
    participant PatientUI as Patient Chart Page
    participant Services as Patient / Encounter Services
    participant SQL as Database Helpers
    participant DB as MySQL / MariaDB
    participant Modules as Module Hooks
    participant Templates as Templates / Assets

    Staff->>Browser: Open OpenEMR URL
    Browser->>Index: GET /
    Index->>Globals: Load environment and site config
    Globals->>Login: Check current session

    alt User is not logged in
        Login-->>Browser: Render login page
        Staff->>Browser: Submit username, password, site
        Browser->>Login: POST credentials
        Login->>Auth: Validate user and permissions
        Auth->>SQL: Query user, ACL, session data
        SQL->>DB: Read auth records
        DB-->>SQL: Auth data
        SQL-->>Auth: Auth result
        Auth-->>Login: Success or failure
    end

    Login-->>Index: Authenticated session
    Index->>Main: Load staff UI frame
    Main->>Modules: Trigger UI/module hooks
    Modules-->>Main: Optional menu items or scripts
    Main-->>Browser: Render main navigation

    Staff->>Browser: Select a patient
    Browser->>PatientUI: GET patient chart
    PatientUI->>Globals: Reuse site config and runtime globals
    PatientUI->>Auth: Check patient/chart permissions
    Auth-->>PatientUI: Allowed
    PatientUI->>Services: Request demographics, encounters, documents
    Services->>SQL: Build and execute queries
    SQL->>DB: Read patient-related tables
    DB-->>SQL: Patient chart data
    SQL-->>Services: Rows and mapped records
    Services-->>PatientUI: Patient model data
    PatientUI->>Modules: Trigger patient chart hooks
    Modules-->>PatientUI: Optional additions
    PatientUI->>Templates: Render HTML and assets
    Templates-->>Browser: Patient chart response
```

## 6. Sequence Diagram: API / FHIR Request

This second sequence shows how an external application talks to OpenEMR. API requests rely more heavily on newer routing, authorization, services, and JSON/FHIR responses than the older staff UI pages do.

```mermaid
%% External API or FHIR request flow
sequenceDiagram
    autonumber
    actor Client as External Client
    participant API as apis/* Entry
    participant Request as HTTP Request
    participant App as API Application
    participant Kernel as Modern Kernel
    participant Site as Site Resolver
    participant OAuth as OAuth2 / SMART
    participant Authz as Authorization Checks
    participant Routes as API / FHIR Routes
    participant Controller as REST or FHIR Controller
    participant Service as Service Layer
    participant DB as Database
    participant View as JSON / FHIR Response
    participant Logger as Audit / Error Logs

    Client->>API: Send request with token
    API->>Request: Normalize HTTP request
    API->>Site: Resolve target OpenEMR site
    Site-->>API: Site config
    API->>Kernel: Bootstrap API runtime
    Kernel->>App: Build API application
    App->>OAuth: Validate access token or SMART context
    OAuth->>Authz: Check scopes, user, patient context

    alt Token or scope invalid
        Authz-->>View: 401 or 403 error
        View-->>Client: Error response
    else Token and scope valid
        Authz-->>Routes: Continue
        Routes->>Controller: Match endpoint
        Controller->>Service: Request OpenEMR business data
        Service->>DB: Read or write records
        DB-->>Service: Result
        Service-->>Controller: Domain data
        Controller->>View: Format JSON or FHIR resource
        Controller->>Logger: Write audit or error details if needed
        View-->>Client: Response body and status
    end
```

## How To Read These Diagrams

1. Start with the high-level overview. It tells you who uses OpenEMR and which big pieces exist.
2. Move to the component breakdown. This explains where code lives and why both `interface/*` and `src/*` matter.
3. Use the data flow diagram when tracing a bug. Find the request type, then follow arrows toward services, database, files, and response rendering.
4. Use the object/dependency diagram to identify likely code owners. For example, API changes often touch controllers plus services; legacy UI changes often touch `interface/*`, `library/*`, and services together.
5. Use sequence diagrams when you need the order of operations. They show timing: bootstrap first, auth next, routing/controllers after that, then data access and response.

## Additional Views Worth Creating Later

1. Entity relationship diagram for core clinical tables: patient, encounter, form, document, billing, users, roles, and audit data.
2. Module extension lifecycle diagram: how custom modules are discovered, enabled, hooked into events, rendered in UI, and upgraded.
3. FHIR and SMART security diagram: token creation, scopes, patient context, authorization enforcement, and FHIR resource mapping.

