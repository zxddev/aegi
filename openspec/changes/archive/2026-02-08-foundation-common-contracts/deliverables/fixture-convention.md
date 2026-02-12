# Fixture Naming Convention & Usage Map (Tasks 7.1 / 7.4)

Source: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md

## Naming Convention (Task 7.1)

Pattern: `defgeo-<domain>-<scenario>-<nnn>`

- `<domain>`: kebab-case domain identifier (e.g. `defense-geopolitics`)
- `<scenario>`: kebab-case scenario descriptor (e.g. `html`, `pdf`, `multilingual`)
- `<nnn>`: zero-padded 3-digit sequence number

Legacy IDs (`defgeo-001`, `defgeo-002`) remain valid via the `aliases` field.

## Manifest Extensions (Task 7.2)

New optional fields per fixture entry:

| Field | Type | Description |
|---|---|---|
| `scenario_type` | string | Category of the test scenario |
| `aliases` | string[] | Alternative fixture IDs (for backward compat) |

## Backward Compatibility (Task 7.3)

- `defgeo-001` and `defgeo-002` retain their original `fixture_id`.
- New-style IDs are added as `aliases` entries.
- All existing path fields (`chunks_path`, `source_claims_path`, etc.) are unchanged.
- Manifest `version` bumped from 1 → 2; consumers MUST accept both.

## Fixture Usage Map (Task 7.4)

| OpenSpec Scenario | fixture_id |
|---|---|
| HTML artifact extraction (P0 baseline) | `defgeo-001` |
| PDF artifact extraction (P0 baseline) | `defgeo-002` |
