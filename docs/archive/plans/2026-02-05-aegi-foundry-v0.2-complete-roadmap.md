<!-- Author: msq -->

# AEGI Foundry v0.2 Complete Roadmap (Requirements -> P0 -> P3)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this roadmap task-by-task.

**Goal:** Build an OSINT workbench where conclusions are always traceable, replayable, and audit-ready.
The core product is **not** report generation; it is an evidence-first object platform:
`Judgment → Assertion → SourceClaim → Evidence → Chunk(anchor_set/health) → ArtifactVersion → ArtifactIdentity`.

**Non-negotiable invariants (must hold at all times):**
- Evidence-first + Archive-first (no “read page -> write conclusion”)
- Action-only writes (every state change is an Action)
- Strong anchors with health + drift detection (citations are contracts)
- Deny-by-default policies on tools/models/exports
- Derived indexes are rebuildable from Postgres + object storage

**Repo layout (monorepo):**
- `code/aegi-core/` (src layout): control/data plane + pipelines + API
- `code/aegi-mcp-gateway/` (src layout): tool plane gateway + adapters + tool audit
- `code/aegi-web/` (later): analyst workbench UI

**Port segment:** Reserve `87xx` for this repo.
- App: `8700` (aegi-core), `8704` (aegi-mcp-gateway)
- Infra (docker-mapped): `8710` Postgres, `8711` MinIO API, `8712` MinIO console
- Optional later: `8701` SearxNG, `8702` ArchiveBox, `8703` Unstructured, `8707` OpenSearch

**Primary references:**
- Product/constraints: `docs/foundry/v0.2/technical-architecture.md`
- Implementation blueprint: `docs/foundry/v0.2/implementation-architecture.md`
- Research + OSS mapping: `docs/archive/需求研究/参考开源项目与论文基础.md`

---

## Part A: Requirements Research (make PRD executable)

**Deliverables (documents):**
- Updated PRD with concrete acceptance criteria: `docs/foundry/v0.2/prd.md`
- “Definition of Done” for P0/P1: `docs/foundry/v0.2/prd.md` (Milestones section)
- Data contracts (schemas + invariants): `docs/foundry/v0.2/implementation-architecture.md` (appendix)

### Task A1: Define the 3 P0 User Flows (MVP)

**Outcome:** 3 flows that can be demoed end-to-end, offline.
- Flow 1 (Search -> Evidence Vault): given a query, show archived sources with immutable IDs.
- Flow 2 (Cite -> SourceClaim): click a claim and jump to anchored snippet; show anchor health.
- Flow 3 (Explain -> Judgment): a judgment rendered from assertions with explicit confidence + gaps.

**Acceptance:** each flow must be executable with fixtures only (no live internet).

### Task A2: Scope Boundaries + Compliance Rules

**Outcome:** explicit rules for:
- OSINT-only boundary, robots/ToS handling (gateway-enforced)
- copyright/license handling (license_note + export restrictions)
- PII minimization + retention policy per case

**Acceptance:** every tool output path in the pipeline produces:
- `tool_trace` (inputs/outputs/latency/errors)
- `license_note` where relevant

### Task A3: Decide “MVP Ontology” (minimal entity/event types)

**Outcome:** the minimal entity/event/relation set needed for P0 and how it maps to:
- internal JSON schema
- optional export (STIX/MISP) later

**Acceptance:** the chosen ontology must support the 3 P0 user flows without overfitting.

---

## Part B: Platform P0 (end-to-end evidence loop, offline-testable)

**Status:**
- Skeletons exist: `code/aegi-core/`, `code/aegi-mcp-gateway/` (src layout)
- Infra compose exists: `docker-compose.yml` + `.env.example`

### Task B1: Authoritative Store + IDs (Postgres + MinIO)

**Outcome:** Postgres holds authoritative records; MinIO stores immutable artifacts; both are reachable via `87xx` ports.

**Acceptance:**
- `docker compose up -d postgres minio` is green
- `aegi-core` has DB smoke test passing

### Task B2: P0 Data Model (tables + invariants)

**Outcome:** tables (minimum):
- `cases`
- `artifact_identities`, `artifact_versions`
- `chunks` (anchor_set + anchor_health)
- `evidence` (license_note + pii_flags + retention_policy)
- `source_claims`
- `assertions` + join table
- `actions`
- `tool_traces`

**Acceptance:**
- Alembic migration creates tables
- FK indexes exist on all FK columns
- Basic round-trip tests exist for each table (insert/select)

### Task B3: Gateway Tool Contracts (no live internet required)

**Outcome:** `aegi-mcp-gateway` exposes stable tool endpoints:
- `/tools/meta_search`
- `/tools/archive_url`
- `/tools/doc_parse`

**Acceptance:**
- Contract tests assert output schema keys and error shape
- Every tool call generates a `tool_trace` record (store can be Postgres later; start with structured logs if needed)

### Task B4: Core -> Gateway ToolClient + Action-only writes

**Outcome:** `aegi-core` calls tools only through gateway and writes:
- `Action(action_type=...)`
- `ToolTrace(tool_name=...)` linked to Action

**Acceptance:** offline tests using dependency overrides (fake tool client) cover:
- tool call path
- action record creation

### Task B5: Offline Fixtures (non-negotiable)

**Outcome:** a fixtures pack under `code/aegi-core/tests/fixtures/`:
- archived HTML/PDF snapshots
- expected parse output
- expected chunk anchors

**Acceptance:** CI-like local run can validate:
- anchor locate rate
- drift detection alerts (simulated)

---

## Part C: Platform P1 (SourceClaim-first extraction + analyst UX core)

### Task C1: Chunking + Anchor Health

**Outcome:** deterministic chunking for HTML/PDF with redundant selectors:
- HTML: TextQuote + TextPosition + XPath/CSS
- PDF: page + bbox + quote

**Acceptance:**
- anchor health computed + stored
- “click citation -> locate” success rate reported

### Task C2: SourceClaim Extractor (structured output)

**Outcome:** extraction pipeline that produces SourceClaims from chunks:
- quote + selectors + attribution + modality

**Acceptance:**
- regression fixtures for at least 20 claims
- output rejects ungrounded claims (must contain selectors linking to evidence)

### Task C3: Assertion Fusion + Conflict Model

**Outcome:** from multiple SourceClaims, produce Assertions with:
- conflict sets
- confidence + gaps

**Acceptance:** UI/API can show “sources disagree” without forcing a single truth.

### Task C4: Minimal Workbench (read-only first)

**Outcome:** `code/aegi-web/` (or a thin client) provides:
- Evidence Vault
- Claim Compare
- Timeline (basic)

**Acceptance:** each view is backed by stable API and clickable provenance.

---

## Part D: Platform P2 (monitoring, import/export, evaluation as product)

### Task D1: Watchlist + Scheduled Ingest

**Outcome:** recurring jobs that:
- re-run collection
- detect new versions
- trigger re-extraction + diffs

### Task D2: Interop (MISP/OpenCTI/STIX)

**Outcome:**
- Import: MISP event -> Evidence/SourceClaim
- Export: STIX bundle/MISP mapping from internal assertions

### Task D3: Eval-as-a-Product

**Outcome:** metrics tracked per release:
- anchor locate rate/drift rate
- claim grounding rate
- extraction precision/recall on fixtures
- latency/cost per pipeline stage

---

## Part E: Platform P3 (collaboration + scale)

### Task E1: Permissions (RBAC/ABAC) + Case-scoped Tokens

### Task E2: Derived Indexes (rebuildable)

**Outcome:** optional services (OpenSearch/Neo4j/Qdrant) that are always rebuildable.

---

## Execution Order (recommended)

1) Freeze P0 PRD (Part A)
2) Complete P0 pipeline + fixtures (Part B)
3) Only then: SourceClaim/Assertion (Part C)
4) Only then: Workbench UX beyond evidence/claims/timeline

---

## Immediate Next Steps

- Keep executing the concrete P0 plan: `docs/archive/plans/2026-02-05-aegi-foundry-v0.2-p0.md`
- Create the next focused plan file: P0 Data Model + migrations + tests (B2) as its own plan doc once PRD flows are frozen.
