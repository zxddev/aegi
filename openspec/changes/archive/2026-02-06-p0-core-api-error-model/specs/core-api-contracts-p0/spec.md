## ADDED Requirements

### Requirement: Core SHALL expose APIs needed for the three P0 user flows
The system MUST expose API endpoints that support exactly the three P0 flows:
1) Evidence Vault browsing
2) Citation -> locate (via SourceClaim/Evidence/Chunk)
3) Judgment -> provenance navigation

Minimum endpoints (P0):
- `POST /cases` (create case)
- `GET /cases/{case_uid}`
- `GET /cases/{case_uid}/artifacts` (list artifact versions in case)
- `GET /artifacts/versions/{artifact_version_uid}`
- `GET /evidence/{evidence_uid}` (returns chunk + anchors + artifact_version reference)
- `GET /source_claims/{source_claim_uid}`
- `GET /assertions/{assertion_uid}`
- `GET /judgments/{judgment_uid}` (may be stubbed in P0, but MUST preserve provenance links)

#### Scenario: Evidence Vault can list archived versions
- **WHEN** a client requests `/cases/{case_uid}/artifacts`
- **THEN** the response includes artifact_version_uids and hashes

#### Scenario: Client can navigate from judgment to evidence
- **WHEN** a client fetches a Judgment
- **THEN** the response includes references allowing navigation to Assertions and SourceClaims

### Requirement: Responses MUST include stable identifiers
All API responses MUST include stable UIDs for primary objects.

#### Scenario: Evidence response includes required UIDs
- **WHEN** a client fetches `/evidence/{evidence_uid}`
- **THEN** it includes `evidence_uid`, `chunk_uid`, and `artifact_version_uid`
