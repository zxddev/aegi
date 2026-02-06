## ADDED Requirements

### Requirement: Mutating operations MUST emit an Action record
Any API operation that creates or mutates authoritative state MUST create an Action record.

#### Scenario: Creating a case emits Action
- **WHEN** a client creates a Case
- **THEN** an Action is recorded describing the mutation

### Requirement: Mutating requests MUST accept rationale/actor context
Mutating requests MUST accept `actor_id` and `rationale` (may be empty) so that Actions are explainable.

#### Scenario: Case creation accepts rationale
- **WHEN** a client calls `POST /cases` with rationale
- **THEN** the resulting Action stores the rationale
