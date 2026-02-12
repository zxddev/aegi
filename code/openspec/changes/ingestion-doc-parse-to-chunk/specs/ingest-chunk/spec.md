# Ingest Chunk Specification

## ADDED Requirements

### REQ-INGEST-001: Document Parsing Integration
The system MUST integrate with the ToolClient.doc_parse method to extract structured chunks from document artifacts.

### REQ-INGEST-002: Chunk Data Persistence
The system SHALL write parsed document chunks to the Chunk table with the following mandatory fields:
- uid: Unique identifier for the chunk
- text: Extracted text content from the document
- ordinal: Sequential ordering of chunks within the document
- anchor_set: Metadata anchors derived from unstructured parsing results

### REQ-INGEST-003: Evidence Record Creation
The system MUST create corresponding Evidence records for each chunk with:
- uid: Unique identifier for the evidence
- kind: Set to "document_chunk"
- case_uid: Associated case identifier
- Proper linkage to the source chunk

### REQ-INGEST-004: Metadata Anchor Mapping
The system SHALL map unstructured metadata to anchor_set with the following transformations:
- page_number → page anchor type
- coordinates → coordinates anchor type  
- filename → filename anchor type
- languages → languages anchor type
- Empty metadata MUST result in empty anchor_set

### REQ-INGEST-005: Response Format Compliance
The ingest endpoint MUST return a response containing:
- action_uid: Unique identifier for the ingestion action
- tool_trace_uid: Unique identifier for the tool execution trace
- chunk_uids: Array of created chunk identifiers
- evidence_uids: Array of created evidence identifiers

### REQ-INGEST-006: Error Handling Protocol
The system SHALL return HTTP 502 status with {"ok": false, "error": "..."} format when ToolClient operations fail.

### REQ-INGEST-007: Empty Content Handling
The system MUST handle empty chunk responses by returning empty arrays for chunk_uids and evidence_uids without error.