"""Timestamped evidence and the optional coaching report."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Dimension = Literal["gaze", "posture", "gesture", "face", "voice", "structure", "coordination"]
DIMENSIONS: tuple[Dimension, ...] = (
    "gaze", "posture", "gesture", "face", "voice", "structure", "coordination",
)


class Evidence(BaseModel):
    id: str
    start: float
    end: float
    metrics: dict[str, float | int]
    transcript_ids: list[int] = Field(default_factory=list)


class VisualEvidence(BaseModel):
    schema_version: Literal[1] = 1
    model: Literal["mediapipe_holistic"] = "mediapipe_holistic"
    sample_hz: float
    # Coverage is relative to sampled frames. Missing metrics stay absent.
    coverage: dict[str, float]
    windows: list[Evidence]


class DeliveryEvidence(BaseModel):
    audio_offset_seconds: float
    visual: VisualEvidence | None = None
    audio: list[Evidence] = Field(default_factory=list)


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dimension: Dimension
    status: Literal["observed", "insufficient_evidence"]
    evidence_ids: list[str] = Field(max_length=3)
    observation: str = Field(max_length=400)
    suggestion: str = Field(max_length=400)


class DeliveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=600)
    feedback: list[Feedback] = Field(min_length=7, max_length=7)
