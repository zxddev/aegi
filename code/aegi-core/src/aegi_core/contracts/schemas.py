"""Shared contract schemas (Gate-0).

Source: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md
Evidence: All feature changes MUST depend on shared contracts; Foundation MUST
reserve multimodal compatibility fields.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# -- Multimodal enum (task 4.1) ------------------------------------------------

class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


# -- Media time range (task 4.2) -----------------------------------------------

class MediaTimeRange(BaseModel):
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


# -- Core schemas (task 1.1) ----------------------------------------------------

class SourceClaimV1(BaseModel):
    uid: str
    case_uid: str
    artifact_version_uid: str
    chunk_uid: str
    evidence_uid: str
    quote: str
    selectors: list[dict] = Field(default_factory=list)
    attributed_to: Optional[str] = None
    modality: Optional[Modality] = None
    segment_ref: Optional[str] = None
    media_time_range: Optional[MediaTimeRange] = None
    language: Optional[str] = None
    original_quote: Optional[str] = None
    translation: Optional[str] = None
    translation_meta: Optional[dict] = None
    created_at: datetime


class AssertionV1(BaseModel):
    uid: str
    case_uid: str
    kind: str
    value: dict = Field(default_factory=dict)
    source_claim_uids: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    modality: Optional[Modality] = None
    segment_ref: Optional[str] = None
    media_time_range: Optional[MediaTimeRange] = None
    created_at: datetime


class HypothesisV1(BaseModel):
    uid: str
    case_uid: str
    label: str
    supporting_assertion_uids: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    modality: Optional[Modality] = None
    segment_ref: Optional[str] = None
    media_time_range: Optional[MediaTimeRange] = None
    created_at: datetime


class NarrativeV1(BaseModel):
    uid: str
    case_uid: str
    title: str
    assertion_uids: list[str] = Field(default_factory=list)
    hypothesis_uids: list[str] = Field(default_factory=list)
    modality: Optional[Modality] = None
    segment_ref: Optional[str] = None
    media_time_range: Optional[MediaTimeRange] = None
    created_at: datetime
