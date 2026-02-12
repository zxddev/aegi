# E2E Pipeline Specification

## ADDED Requirements

### REQ-E2E-001: End-to-End Pipeline Integration
The system MUST support complete end-to-end processing from document ingestion through claim extraction to assertion fusion.

### REQ-E2E-002: Ingestion Stage Execution
The system SHALL execute the ingest pipeline stage that:
- Processes document artifacts through ToolClient.doc_parse
- Creates Chunk and Evidence records in the database
- Returns chunk_uids for downstream processing

### REQ-E2E-003: Claim Extraction Stage Execution  
The system MUST execute the claim_extract pipeline stage that:
- Processes each chunk using LLM client for claim identification
- Creates SourceClaim records linked to source chunks
- Returns source_claim_uids for fusion processing

### REQ-E2E-004: Assertion Fusion Stage Execution
The system SHALL execute the assertion_fuse pipeline stage that:
- Processes multiple source claims for consolidation
- Creates Assertion records representing fused claims
- Returns assertion_uids as final pipeline output

### REQ-E2E-005: Data Flow Continuity
The system MUST maintain data flow continuity where:
- chunk_uids from ingest stage feed into claim_extract stage
- source_claim_uids from claim_extract stage feed into assertion_fuse stage
- Each stage MUST be able to retrieve required data from previous stages

### REQ-E2E-006: Database Consistency Verification
The system SHALL ensure database consistency across the pipeline where:
- All created Chunk records MUST contain text matching original document elements
- All SourceClaim records MUST be properly linked to their source chunks
- All Assertion records MUST be traceable to their constituent source claims

### REQ-E2E-007: Mock Integration Support
The system MUST support mock integrations for:
- External HTTP calls (file downloads, Unstructured API)
- LLM client responses for claim extraction
- Gateway ASGI transport for tool client operations

### REQ-E2E-008: Pipeline Stage Validation
The system SHALL validate that each pipeline stage:
- Returns HTTP 200 status on successful execution
- Produces non-empty result sets when processing valid input data
- Maintains referential integrity between pipeline stages