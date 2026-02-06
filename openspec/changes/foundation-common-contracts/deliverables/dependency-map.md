# Dependency Map: Feature → Contract (Task 6.1)

Source: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md

All downstream feature changes MUST import from the shared contracts package
(`aegi_core.contracts.*`). They MUST NOT redefine the core schemas.

| Feature Change | Required Contract Imports |
|---|---|
| automated-claim-extraction-fusion | `schemas.SourceClaimV1`, `schemas.AssertionV1`, `audit.ActionV1`, `audit.ToolTraceV1`, `errors.ProblemDetail`, `llm_governance.*` |
| multilingual-evidence-chain | `schemas.SourceClaimV1`, `schemas.Modality`, `audit.ActionV1`, `errors.ProblemDetail`, `llm_governance.*` |
| conversational-analysis-evidence-qa | `schemas.SourceClaimV1`, `schemas.AssertionV1`, `audit.ActionV1`, `errors.ProblemDetail`, `llm_governance.*` |
| knowledge-graph-ontology-evolution | `schemas.SourceClaimV1`, `schemas.AssertionV1`, `schemas.HypothesisV1`, `errors.ProblemDetail` |
| ach-hypothesis-analysis | `schemas.SourceClaimV1`, `schemas.AssertionV1`, `schemas.HypothesisV1`, `errors.ProblemDetail`, `llm_governance.*` |
| narrative-intelligence-detection | `schemas.SourceClaimV1`, `schemas.NarrativeV1`, `errors.ProblemDetail`, `llm_governance.*` |
| predictive-causal-scenarios | `schemas.*`, `errors.ProblemDetail`, `llm_governance.*` |
| meta-cognition-quality-scoring | `schemas.*`, `audit.*`, `errors.ProblemDetail`, `llm_governance.*` |
