import logging
logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from openai import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel, Field

from .evaluator import EvaluationConfigurationError, TextEvaluator
from .schemas import EvaluationLanguage, EvaluationResult

router = APIRouter(prefix="/evaluations", tags=["text-evaluation"])


class EvaluationRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    transcript: str = Field(min_length=1)
    language: EvaluationLanguage = EvaluationLanguage.ZH
    audience: str = "初学者 / beginners"
    key_points: list[str] = Field(default_factory=list)
    reference_notes: str = ""


@router.post("", response_model=EvaluationResult)
def evaluate_text(request: EvaluationRequest) -> EvaluationResult:
    try:
        evaluator = TextEvaluator()
        return evaluator.evaluate(
            topic=request.topic,
            transcript=request.transcript,
            language=request.language.value,
            audience=request.audience,
            key_points=request.key_points,
            reference_notes=request.reference_notes,
        )
    except EvaluationConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail="LLM provider rate limit reached.") from exc
    except APIConnectionError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to the LLM provider.") from exc
    except APIStatusError as exc:
        raise HTTPException(status_code=502, detail=f"LLM provider returned status {exc.status_code}.") from exc
    except Exception as exc:
       logger.exception("Text evaluation failed")
       raise HTTPException(
           status_code=502,
           detail=f"Text evaluation failed: {type(exc).__name__}: {exc}"
       ) from exc
