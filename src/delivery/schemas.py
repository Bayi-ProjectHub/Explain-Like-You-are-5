"""Timestamped evidence and the local video report."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

from ..audio.schemas import TranscriptionResult

VisualKind = Literal["gaze", "posture", "gesture", "face"]


class Evidence(BaseModel):
    id: str
    start: float
    end: float
    metrics: dict[str, float | int]
    transcript_ids: list[int] = Field(default_factory=list)


class VisualEvent(Evidence):
    kind: VisualKind
    measurements: list[MotionMeasurement] = Field(default_factory=list)


class MotionMeasurement(BaseModel):
    target: Literal["left_wrist", "right_wrist", "shoulder_center", "torso_lean",
                    "jawOpen", "browInnerUp", "eyeBlinkLeft", "eyeBlinkRight", "mouthSmileLeft", "mouthSmileRight"]
    axis: Literal["x", "y", "roll", "coefficient"]
    unit: Literal["shoulder_width", "degree", "blendshape_coefficient"]
    start_value: float
    end_value: float
    delta: float
    span: float
    peak_speed: float

    @computed_field
    @property
    def direction(self) -> str:
        if self.axis == "y":
            return "down" if self.delta > 0 else "up"
        if self.axis == "coefficient":
            return "increase" if self.delta > 0 else "decrease"
        return "frame_right" if self.delta > 0 else "frame_left"


class PlaybackRange(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("End must be after start.")
        return self


class VisualEvidence(BaseModel):
    schema_version: Literal[2] = 2
    model: Literal["mediapipe_holistic"] = "mediapipe_holistic"
    sample_hz: float
    video_offset_seconds: float = 0
    sampled_frames: int = 0
    tracking_sources: dict[str, int] = Field(default_factory=dict)
    selected_playback_ranges: list[PlaybackRange] = Field(default_factory=list)
    coverage_target: float = 0.85
    # Coverage is relative to sampled frames. Missing metrics stay absent.
    coverage: dict[str, float]
    windows: list[Evidence]
    events: list[VisualEvent] = Field(default_factory=list)


class DeliveryEvidence(BaseModel):
    audio_offset_seconds: float
    visual: VisualEvidence | None = None
    audio: list[Evidence] = Field(default_factory=list)
    audio_levels: list[Evidence] = Field(default_factory=list)


class SpeechExcerpt(BaseModel):
    segment_id: int
    start: float
    end: float
    text: str
    precision: Literal["segment"] = "segment"


class ReportMoment(BaseModel):
    id: str
    start: float
    end: float
    kind: VisualKind | Literal["quiet", "pace"]
    metrics: dict[str, float | int]
    speech: list[SpeechExcerpt]
    measurements: list[MotionMeasurement] = Field(default_factory=list)
    audio_refs: list[str] = Field(default_factory=list)


class TimelineSync(BaseModel):
    audio_to_playback_seconds: float
    video_to_playback_seconds: float


class DeliveryReport(BaseModel):
    schema_version: Literal[2] = 2
    sync: TimelineSync
    video: list[ReportMoment]
    audio: list[ReportMoment]
    audio_levels: list[Evidence]
    transcript: TranscriptionResult
