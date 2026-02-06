## ADDED Requirements

### Requirement: Archive-first ingestion produces immutable ArtifactVersion
The system MUST create an `ArtifactIdentity` and an immutable `ArtifactVersion` for any ingested external source (URL or search result). An `ArtifactVersion` MUST include a content hash (e.g., SHA-256) and an object storage reference so the exact bytes can be retrieved later.

#### Scenario: Ingest URL creates ArtifactIdentity and ArtifactVersion
- **WHEN** a user ingests a URL into a Case
- **THEN** the system creates an `ArtifactIdentity`
- **THEN** the system creates an `ArtifactVersion` linked to that identity with `content_sha256` and `storage_ref`

#### Scenario: Re-ingest creates a new ArtifactVersion, not overwrite
- **WHEN** the same URL is ingested again at a later time
- **THEN** the system creates a new `ArtifactVersion` with a different UID
- **THEN** the previous `ArtifactVersion` remains addressable and unchanged

### Requirement: Parsing and extraction operate only on archived bytes
The system MUST run parsing, chunking, and extraction only on the bytes referenced by an `ArtifactVersion` (object storage), never on live network responses.

#### Scenario: Parse request requires an ArtifactVersion reference
- **WHEN** a parse operation is requested without an `artifact_version_uid`
- **THEN** the system rejects the request with a structured error

#### Scenario: Core never fetches the internet directly
- **WHEN** `aegi-core` needs external content
- **THEN** it MUST call `aegi-mcp-gateway` tools to obtain an `ArtifactVersion`
- **THEN** `aegi-core` MUST parse from the stored artifact referenced by that version

### Requirement: Evidence chain links Chunk anchors to ArtifactVersion
The system MUST create `Chunk` records that include `anchor_set` and `anchor_health`. `Evidence` MUST link to the specific `Chunk` and the specific `ArtifactVersion` used.

#### Scenario: Chunk creation stores anchors
- **WHEN** an `ArtifactVersion` is chunked
- **THEN** each Chunk has a non-empty `anchor_set`
- **THEN** each Chunk has an `anchor_health` object

#### Scenario: Evidence references the exact version and chunk
- **WHEN** the system records evidence for a claim
- **THEN** the Evidence record links to `artifact_version_uid` and `chunk_uid`
