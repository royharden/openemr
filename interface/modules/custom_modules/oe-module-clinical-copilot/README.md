# oe-module-clinical-copilot

Read-only clinical co-pilot panel embedded in the OpenEMR patient chart.

- **Renders** a card on the demographics page via `PatientDemographics\RenderEvent::EVENT_SECTION_LIST_RENDER_AFTER`.
- **Gateway** at `public/api/brief.php` enforces session, CSRF (subject `ClinicalCopilot`), ACL (`patients/med`), and server-side pid binding.
- **Builds** identity / active-problems / active-medications source packets.
- **Calls** the FastAPI sidecar (private network) when `COPILOT_API_BASE_URL` and `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET` are set; otherwise renders raw packets as fallback claims.
- **Audits** every turn via `EventAuditLogger` (event `agent_turn`, joinable to Langfuse via `trace_id`).

## Enable on a fresh database

```sql
INSERT INTO modules
(mod_name, mod_directory, mod_active, mod_ui_name, mod_ui_active, mod_description, mod_nick_name, mod_enc_menu, directory, date, sql_run, type, sql_version, acl_version)
VALUES
('Clinical Co-Pilot', 'oe-module-clinical-copilot', 1, 'Clinical Co-Pilot', 1, 'Read-only AI co-pilot embedded in patient chart', 'copilot', 'no', 'oe-module-clinical-copilot', NOW(), 1, 0, '0', '0');
```

`mod_active = 1` and `type = 0` (custom module) are the load-bearing fields — `ModulesApplication::bootstrapCustomModules()` filters on those.

## Configure the sidecar link (optional)

Set on the OpenEMR PHP environment (Railway service env vars, or a `.env` for local):

```text
COPILOT_API_BASE_URL=http://copilot-api:8000
COPILOT_OPENEMR_GATEWAY_SHARED_SECRET=<shared with sidecar>
```

If unset, the gateway returns un-verified packet-derived claims and `verifier_status=no_sidecar` — useful for local development without an Anthropic API key.

## Verify

1. Log in at `https://localhost:9300/` (admin / pass).
2. Open a demo patient chart — the card renders with `Co-Pilot loading…`.
3. Card populates with claims + a `trace: <uuid>` chip.
4. Confirm an `agent_turn` row in `audit_master` matching the `trace_id`.

## Files

```
oe-module-clinical-copilot/
├── composer.json
├── info.txt
├── version.php
├── openemr.bootstrap.php           # event dispatcher subscription
├── public/
│   ├── api/brief.php               # gateway endpoint
│   └── assets/{js,css}             # client-side panel
└── src/
    ├── Bootstrap.php
    ├── Controller/PanelController.php
    ├── SourcePackets/
    │   ├── PacketBuilder.php (interface)
    │   ├── PacketDto.php (readonly value object)
    │   ├── IdentityPacketBuilder.php
    │   ├── ActiveProblemsPacketBuilder.php
    │   └── ActiveMedicationsPacketBuilder.php
    ├── Gateway/
    │   ├── TaskToken.php           # 15-min HMAC token
    │   └── SidecarClient.php       # Guzzle POST to sidecar
    └── Audit/
        └── AgentTurnAuditor.php    # writes audit_master row
```
