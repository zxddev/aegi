<!-- Author: msq -->

# Schema Change Request: Foundation Gate-0 Shared Fields

- Status: ✅ COMPLETED
- Requested by: foundation-common-contracts
- Implemented by: coord/schema-owner
- Alembic revision: `1dda8adf4f9b`

## New Columns (9 total)

### source_claims

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| segment_ref | String(128) | Yes | NULL |
| media_time_range | JSONB | Yes | NULL |

### assertions

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| modality | String(32) | Yes | NULL |
| segment_ref | String(128) | Yes | NULL |
| media_time_range | JSONB | Yes | NULL |

### actions

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| trace_id | String(64) | Yes | NULL |
| span_id | String(64) | Yes | NULL |

### tool_traces

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| trace_id | String(64) | Yes | NULL |
| span_id | String(64) | Yes | NULL |
