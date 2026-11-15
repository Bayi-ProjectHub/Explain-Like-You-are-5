
import json
import os

from openai import OpenAI
from pydantic import ValidationError

from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schemas import EvaluationResult


class EvaluationConfigurationError(RuntimeError):
    pass


class TextEvaluator:
    """Evaluate transcripts using the DeepSeek API."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv(
            "EVALUATION_MODEL", "deepseek-flash"
        )

    def evaluate(
        self,
        *,
        topic: str,
        transcript: str,
        language: str = "zh",
        audience: str = "初学者 / beginners",
        key_points: list[str] | None = None,
        reference_notes: str = "",
    ) -> EvaluationResult:
        if not self.api_key:
            raise EvaluationConfigurationError(
                "DEEPSEEK_API_KEY is missing. Set it in your local .env file."
            )

        if not transcript.strip():
            raise ValueError("transcript must not be empty")

        client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com",
            timeout=120.0,
            max_retries=2,
        )

        user_prompt = build_user_prompt(
            topic=topic,
            transcript=transcript,
            language=language,
            audience=audience,
            key_points=key_points or [],
            reference_notes=reference_notes,
        )

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        SYSTEM_PROMPT
                        + "\n\nYou must return a JSON object matching "
                        "the following Pydantic JSON Schema exactly."
                        + "\nDo not add, remove, or rename fields."
                        + "\nDo not use a flat structure."
                        + "\nEvery evaluation dimension must be a DimensionResult "
                        "with score, rationale, evidence, and suggestions."
                        + "\nAll required fields must be included."
                        + "\nReturn JSON only, without Markdown fences."
                        + "\n\nRequired JSON Schema:\n"
                        + json.dumps(
                            EvaluationResult.model_json_schema(),
                            ensure_ascii=False,
                            indent=2,
                        )
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=16384,
            extra_body={"thinking": {"type": "disabled"}},
        )

        content = response.choices[0].message.content

        if not content or not content.strip():
            raise RuntimeError("DeepSeek returned an empty response.")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            print("DeepSeek JSON parsing failed:")
            print(f"Error position: {exc.pos}")
            print(f"Content length: {len(content)}")
            print(
                "Content around error:",
                content[max(0, exc.pos - 300):exc.pos + 300],
            )
            print("Response finish reason:", response.choices[0].finish_reason)
            raise RuntimeError(
                f"DeepSeek returned invalid JSON: {exc}"
            ) from exc

        try:
            return EvaluationResult.model_validate(data)
        except ValidationError as exc:
            raise RuntimeError(
                f"DeepSeek returned invalid evaluation structure: {exc}"
            ) from exc
