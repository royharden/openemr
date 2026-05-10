# Test Fixtures

Synthetic Maria G. (pid 9001) fixtures live here. Workstreams B and C
populate this directory with per-resource JSON files derived from the
demo seed.

**Naming:** `<resourceCamelCase>_9001.json` — e.g. `patient_9001.json`,
`allergies_9001.json`, `careTeam_9001.json`. Practitioner fixtures may
be named per-practitioner: `practitioner_<id>.json`.

**Rules:**
- Synthetic only — no real PHI, ever.
- Each fixture for a status-filtered resource MUST include at least one
  inactive item, so the adapter-side filter is provably exercised.
- Bundle fixtures should include both `_include`-shaped and
  no-`_include`-shaped variants so both Practitioner-resolution paths
  are tested.
