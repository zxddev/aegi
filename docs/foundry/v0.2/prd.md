<!-- Author: msq -->

# AEGI Foundry PRD (v0.2)

Status: draft

This document is the product requirements for AEGI Foundry v0.2.

## Naming & Positioning

- Platform: AEGI (Agentic Evidence Graph Intelligence)
- Workbench/product line: AEGI Foundry
- Vertical agents: e.g. GDIA (Global Defense Insight Agent) as a domain-specific profile/skill set on top of AEGI (not the platform name)
- Service/repo naming (suggested): `aegi-core`, `aegi-mcp-gateway`, `aegi-web`
- Python packages (suggested): `aegi_core`, `aegi_mcp_gateway`
- Monorepo layout (this repo): `code/aegi-core/`, `code/aegi-mcp-gateway/`, `code/aegi-web/`

Related docs:
- `docs/foundry/v0.2/technical-architecture.md`
- `docs/foundry/v0.2/implementation-architecture.md`

## Scope

P0 scope is intentionally small and acceptance-driven.

### P0 Product Goal

Deliver an OSINT evidence workbench where every conclusion is traceable and replayable through the evidence chain:
`Judgment → Assertion → SourceClaim → Evidence → Chunk(anchor_set/health) → ArtifactVersion → ArtifactIdentity`.

### P0 Strategy

- Acceptance is `fixtures-only`: P0 MUST be demonstrable and regression-testable offline (no live internet, no third-party services required).
- Domain focus for examples/fixtures: international defense & geopolitics.
- Ontology: minimal general set + extension points (no defense-specific ontology types required in P0).

### P0 In-Scope Capabilities

- Evidence-first + Archive-first ingestion pipeline (offline fixtures)
- Immutable ArtifactIdentity/ArtifactVersion + content hashes
- Chunk anchors (`anchor_set`) + anchor health (`anchor_health`) stored and inspectable
- SourceClaim-first extraction: SourceClaims MUST carry selectors grounding them to evidence
- Assertions derived from SourceClaims (conflicts allowed)
- Action-only writes: state-changing operations emit Action records
- Tool governance boundary: external tools are only reachable via `aegi-mcp-gateway` (even if stubbed in P0)

### P0 User Flows (exactly three)

1) Evidence Vault (offline)
   - Given a Case and a fixture “ingest”, user can browse ArtifactVersions and see hashes/storage refs.
2) Citation → Locate
   - Given a SourceClaim, user can jump to the exact anchored snippet and see `anchor_health`.
3) Judgment → Provenance
   - Given a Judgment rendered from Assertions, user can navigate back to SourceClaims/Evidence/ArtifactVersion.

## Non-goals

- No live crawling/scraping integrations required for P0 (SearxNG/ArchiveBox/Unstructured/Tika can be P0.1/P1).
- No “full workbench UI” beyond the three P0 flows.
- No production-grade auth/RBAC/ABAC in P0 (design only).
- No derived indexes requirement (OpenSearch/Neo4j/Qdrant) in P0.
- No attempt to fully model STIX/MISP in P0.

## User Stories

- As an analyst, I can review archived sources (versions) for a case and verify integrity (hash).
- As an analyst, I can click a claim and see the exact quoted context via anchors.
- As an analyst, I can read a judgment and trace every supporting statement back to its original sources.

## Functional Requirements

- The system SHALL store archived artifacts as immutable versions with content hashes.
- The system SHALL store chunks with redundant anchors and anchor health metadata.
- The system SHALL represent extracted statements as SourceClaims grounded by selectors.
- The system SHALL derive Assertions only from SourceClaims and keep conflicts as first-class.
- The system SHALL record Actions for state-changing operations and store tool traces for tool invocations.

## Non-functional Requirements

- Offline regression: P0 MUST run without internet access using fixtures.
- Compliance: robots/ToS, license_note, PII minimization, retention policies MUST be expressible and auditable (P0: documented + stub enforcement; P1: enforced).
- Auditability: every state change and tool invocation must be traceable.
- Determinism: IDs and transformations should be reproducible for fixtures.

## Milestones

### P0 (Freeze + Offline MVP)

DoD:
- PRD sections complete (no TODOs) and reviewed
- Exactly 3 P0 user flows implemented and demoable offline
- Offline regression suite exists with fixtures pack
- Offline regression thresholds met (fixtures-only):
  - anchor_locate_rate >= 0.98
  - claim_grounding_rate >= 0.95
  - report.json + report.txt produced
- Evidence chain navigation works end-to-end for fixtures

### P0.1 (Optional Integrations)

- Add real tool adapters in gateway (SearxNG/ArchiveBox/Unstructured) without changing P0 contracts

### P1 (Anchors + Claims + Fusion)

- Strong anchors and drift/health gating
- SourceClaim extraction and Assertion fusion/conflict UX
