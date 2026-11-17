"""Timestamped evidence and the local video report."""

from typing import Literal

from pydantic import BaseModel, Field

VisualKind = Literal["gaze", "posture", "gesture", "face"]


class Evidence(BaseModel):
    id: str
    start: float
    end: float
    metrics: dict[str, float | int]
    transcript_ids: list[int] = Field(default_factory=list)


class VisualEvent(Evidence):
    kind: VisualKind


class VisualEvidence(BaseModel):
    schema_version: Literal[1] = 1
    model: Literal["mediapipe_holistic"] = "mediapipe_holistic"
    sample_hz: float
    # Coverage is relative to sampled frames. Missing metrics stay absent.
    coverage: dict[str, float]
    windows: list[Evidence]
    events: list[VisualEvent] = Field(default_factory=list)


class DeliveryEvidence(BaseModel):
    audio_offset_seconds: float
    visual: VisualEvidence | None = None
    audio: list[Evidence] = Field(default_factory=list)


class SpeechExcerpt(BaseModel):
    segment_id: int
    start: float
    end: float
    text: str
    precision: Literal["word", "segment"]


class ReportMoment(BaseModel):
    start: float
    end: float
    kind: VisualKind | Literal["quiet", "pace"]
    metrics: dict[str, float | int]
    speech: list[SpeechExcerpt]


class DeliveryReport(BaseModel):
    timeline: list[ReportMoment]
