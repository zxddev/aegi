# Schema Migration Ownership Policy (Task 3.2 / 3.3)

Source: openspec/changes/foundation-common-contracts/specs/schema-migration-ownership/spec.md

## Rule: Post-foundation feature branches MUST NOT add Alembic revisions

After the foundation Gate-0 migration is merged, **no feature branch may create
new Alembic revision files**. This prevents `down_revision` forks.

## Schema-Change-Request Process (Task 3.3)

1. Feature AI discovers a schema gap during implementation.
2. Feature AI creates a file `openspec/schema-change-requests/<change-id>.md` with:
   - Requesting branch
   - Table(s) affected
   - Column(s) / index(es) to add/modify
   - Justification (link to openspec requirement)
3. Schema 协调者 reviews, merges into `coord/schema-owner`, generates the
   unified Alembic revision, and notifies the requesting branch.
4. Feature branch rebases onto the updated migration head.

## CI Enforcement

Any PR that contains files matching `alembic/versions/*.py` from a `feat/*`
branch MUST be rejected by CI unless the author is the schema coordinator.
