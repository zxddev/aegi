## ADDED Requirements

### Requirement: System SHALL measure anchor_locate_rate and drift_rate
The regression suite MUST compute:
- `anchor_locate_rate`: fraction of anchors that can be located in the archived artifact
- `drift_rate`: fraction of anchors that are located but drift beyond acceptable thresholds

#### Scenario: Regression outputs anchor metrics
- **WHEN** the anchor regression is executed
- **THEN** the report includes anchor_locate_rate and drift_rate

### Requirement: System SHALL measure claim_grounding_rate
The regression suite MUST compute:
- `claim_grounding_rate`: fraction of Assertions that can be traced to sufficient SourceClaims that are grounded to Evidence selectors

#### Scenario: Regression outputs grounding metrics
- **WHEN** the grounding regression is executed
- **THEN** the report includes claim_grounding_rate

### Requirement: P0 MUST enforce minimum metric thresholds
P0 acceptance MUST fail if any minimum threshold is not met.

Minimum thresholds (P0):
- `anchor_locate_rate` MUST be >= 0.98
- `claim_grounding_rate` MUST be >= 0.95

#### Scenario: Below-threshold run fails acceptance
- **WHEN** anchor_locate_rate is below the minimum threshold
- **THEN** the regression run is marked failed and the report includes failure reasons
