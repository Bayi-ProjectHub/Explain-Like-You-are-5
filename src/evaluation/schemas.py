from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class EvaluationLanguage(str, Enum):
    ZH = "zh"
    EN = "en"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: str = Field(description="Exact short quotation from the transcript")
    explanation: str


class DimensionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=0, le=100)
    rationale: str
    evidence: list[Evidence]
    suggestions: list[str]


class KnowledgeEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accuracy: DimensionResult
    completeness: DimensionResult
    logic: DimensionResult
    depth: DimensionResult
    examples: DimensionResult


class SpeakingEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clarity: DimensionResult
    coherence: DimensionResult
    conciseness: DimensionResult
    organization: DimensionResult


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: EvaluationLanguage
    topic: str
    knowledge: KnowledgeEvaluation
    speaking: SpeakingEvaluation
    strengths: list[str]
    priority_improvements: list[str]
    transcription_uncertainties: list[str]
    overall_score: int = Field(ge=0, le=100)
    knowledge_score: int = Field(ge=0, le=100)
    speaking_score: int = Field(ge=0, le=100)
