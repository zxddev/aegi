# Author: msq
"""Contract tests for shared schemas (task 5.1).

Evidence: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md
  - Shared contract outputs MUST be file-addressable.
  - Foundation MUST reserve multimodal compatibility fields.
"""

from datetime import datetime, timezone

from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    MediaTimeRange,
    Modality,
    NarrativeV1,
    SourceClaimV1,
)

_NOW = datetime.now(timezone.utc)


# -- SourceClaimV1 -------------------------------------------------------------


def test_source_claim_v1_minimal():
    sc = SourceClaimV1(
        uid="sc-1",
        case_uid="c-1",
        artifact_version_uid="av-1",
        chunk_uid="ch-1",
        evidence_uid="ev-1",
        quote="example",
        created_at=_NOW,
    )
    assert sc.uid == "sc-1"
    assert sc.modality is None
    assert sc.segment_ref is None
    assert sc.media_time_range is None


def test_source_claim_v1_multimodal():
    sc = SourceClaimV1(
        uid="sc-2",
        case_uid="c-1",
        artifact_version_uid="av-1",
        chunk_uid="ch-1",
        evidence_uid="ev-1",
        quote="img",
        modality=Modality.IMAGE,
        segment_ref="frame-42",
        media_time_range=MediaTimeRange(start_ms=0, end_ms=5000),
        created_at=_NOW,
    )
    assert sc.modality == Modality.IMAGE
    assert sc.media_time_range.end_ms == 5000


# -- AssertionV1 ---------------------------------------------------------------


def test_assertion_v1_roundtrip():
    a = AssertionV1(
        uid="a-1",
        case_uid="c-1",
        kind="factual",
        source_claim_uids=["sc-1"],
        confidence=0.9,
        created_at=_NOW,
    )
    data = a.model_dump()
    a2 = AssertionV1.model_validate(data)
    assert a2 == a


# -- HypothesisV1 --------------------------------------------------------------


def test_hypothesis_v1_roundtrip():
    h = HypothesisV1(
        uid="h-1",
        case_uid="c-1",
        label="test hypothesis",
        supporting_assertion_uids=["a-1"],
        created_at=_NOW,
    )
    data = h.model_dump()
    h2 = HypothesisV1.model_validate(data)
    assert h2 == h


# -- NarrativeV1 ---------------------------------------------------------------


def test_narrative_v1_roundtrip():
    n = NarrativeV1(
        uid="n-1",
        case_uid="c-1",
        title="test narrative",
        assertion_uids=["a-1"],
        hypothesis_uids=["h-1"],
        created_at=_NOW,
    )
    data = n.model_dump()
    n2 = NarrativeV1.model_validate(data)
    assert n2 == n


# -- Modality enum covers all required values (task 4.1) -----------------------


def test_modality_enum_values():
    assert set(Modality) == {
        Modality.TEXT,
        Modality.IMAGE,
        Modality.VIDEO,
        Modality.AUDIO,
    }


# -- Multimodal fields are nullable (task 4.2) ---------------------------------


def test_multimodal_fields_nullable():
    sc = SourceClaimV1(
        uid="sc-3",
        case_uid="c-1",
        artifact_version_uid="av-1",
        chunk_uid="ch-1",
        evidence_uid="ev-1",
        quote="q",
        created_at=_NOW,
    )
    assert sc.segment_ref is None
    assert sc.media_time_range is None
