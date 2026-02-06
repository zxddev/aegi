# Schema Change Request: Multilingual Evidence Chain Fields

- Status: ⏳ PENDING
- Requested by: feat/multilingual-evidence-chain (via foundation AI)
- Target: coord/schema-owner

## New Columns (4 total)

### source_claims

| Column | Type | Nullable | Default | Justification |
|--------|------|----------|---------|---------------|
| language | String(16) | Yes | NULL | ISO 639 language code (task 1.1) |
| original_quote | Text | Yes | NULL | Preserve original language quote (task 1.1) |
| translation | Text | Yes | NULL | Translated text (task 1.1) |
| translation_meta | JSONB | Yes | NULL | Translation metadata: model, confidence, etc. (task 1.1) |

## Contract Schema Update

SourceClaimV1 in `contracts/schemas.py` has been updated with these 4 Optional fields.
ORM in `db/models/source_claim.py` already has these columns (added by AI-2).
Only the Alembic migration is needed.
