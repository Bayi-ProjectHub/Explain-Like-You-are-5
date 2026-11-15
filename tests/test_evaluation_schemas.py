from src.evaluation.schemas import (
    DimensionResult, Evidence, EvaluationLanguage, EvaluationResult,
    KnowledgeEvaluation, SpeakingEvaluation,
)


def dimension():
    return DimensionResult(
        score=80, rationale="Reason", evidence=[Evidence(quote="exact words", explanation="Evidence")],
        suggestions=["Improve this"],
    )


def test_evaluation_result_schema_accepts_bilingual_result():
    result = EvaluationResult(
        language=EvaluationLanguage.EN,
        topic="Example topic",
        knowledge=KnowledgeEvaluation(
            accuracy=dimension(), completeness=dimension(), logic=dimension(),
            depth=dimension(), examples=dimension(),
        ),
        speaking=SpeakingEvaluation(
            clarity=dimension(), coherence=dimension(), conciseness=dimension(),
            organization=dimension(),
        ),
        strengths=["Good example"],
        priority_improvements=["Add a definition"],
        transcription_uncertainties=[],
        overall_score=80,
        knowledge_score=80,
        speaking_score=80,
    )
    assert result.language == EvaluationLanguage.EN
    assert result.knowledge.accuracy.score == 80
