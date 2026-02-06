# Schema Change Request: Foundation Gate-0 Shared Fields

- **Requesting branch**: `feat/foundation-common-contracts`
- **Priority**: Gate-0 (blocks all Layer-1+ branches)

## Tables affected

All existing tables already have the required columns per the current DB models.
The following fields are confirmed present and compatible with the contract schemas:

| Table | Existing columns | Status |
|---|---|---|
| `source_claims` | `modality` (String(32), nullable) | ✅ Already present |
| `assertions` | `kind`, `value`, `source_claim_uids`, `confidence` | ✅ Already present |
| `actions` | `action_type`, `actor_id`, `inputs`, `outputs` | ✅ Already present |
| `tool_traces` | `tool_name`, `request`, `response`, `status`, `policy` | ✅ Already present |

## New columns requested (for schema coordinator)

| Table | Column | Type | Nullable | Justification |
|---|---|---|---|---|
| `source_claims` | `segment_ref` | String(128) | YES | Multimodal segment reference (task 4.2) |
| `source_claims` | `media_time_range` | JSONB | YES | Multimodal time range (task 4.2) |
| `assertions` | `modality` | String(32) | YES | Multimodal compatibility (task 4.1) |
| `assertions` | `segment_ref` | String(128) | YES | Multimodal segment reference (task 4.2) |
| `assertions` | `media_time_range` | JSONB | YES | Multimodal time range (task 4.2) |
| `actions` | `trace_id` | String(64) | YES | Trace propagation (audit contract) |
| `actions` | `span_id` | String(64) | YES | Trace propagation (audit contract) |
| `tool_traces` | `trace_id` | String(64) | YES | Trace propagation (audit contract) |
| `tool_traces` | `span_id` | String(64) | YES | Trace propagation (audit contract) |

## Note

The Pydantic contract schemas in `aegi_core.contracts.*` define the full target
shape. The schema coordinator should generate a single Alembic revision adding
all new columns listed above.
