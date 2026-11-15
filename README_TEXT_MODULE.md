# Text Evaluation MVP

## Scope
This MVP evaluates both knowledge content and transcript-visible spoken expression.
It does not evaluate pronunciation, accent, loudness, pace, intonation, gestures,
or other audio/video-only signals.

## Dimensions and weights

| Area | Dimension | Weight |
|---|---|---:|
| Knowledge | Accuracy | 20 |
| Knowledge | Completeness | 15 |
| Knowledge | Logic | 15 |
| Knowledge | Depth | 10 |
| Knowledge | Examples | 10 |
| Speaking | Clarity | 10 |
| Speaking | Coherence | 10 |
| Speaking | Conciseness | 5 |
| Speaking | Organization | 5 |

Completeness is provisional unless `key_points` are supplied. Accuracy is
not equivalent to external fact-checking: provide trusted `reference_notes`
when the project has them.

## Install

```powershell
uv add openai
```

Add these lines to local `.env` (never commit `.env`):

```dotenv
OPENAI_API_KEY=your_key_here
ELY5_EVALUATION_MODEL=gpt-6.1-terra
```

The model identifier is configurable. Confirm model availability for the API
project before use.

## Integrate router

In `src/serve.py`, add:

```python
from src.evaluation.router import router as evaluation_router
app.include_router(evaluation_router)
```

Put the import with the other imports, and the `include_router` beside
`app.include_router(audio_router)`.

## Run

```powershell
uv run uvicorn src.serve:app --reload --env-file .env --port 8000
```

Open `http://127.0.0.1:8000/docs` and try `POST /evaluations`.

Example request:

```json
{
  "topic": "Goodhart's law",
  "transcript": "Paste the transcript here.",
  "language": "en",
  "audience": "beginner",
  "key_points": [
    "Explain the core idea",
    "Explain why a measure can stop being useful when optimized",
    "Give a relevant example"
  ],
  "reference_notes": ""
}
```

## Test

```powershell
uv run pytest -q
```

The schema test does not call the paid API. For an end-to-end test, use the
Swagger UI with a short transcript and monitor API usage.

## Important limitations

- LLM scores are estimates, not objective ground truth.
- Evidence quotations are expected to be exact; validate them against the
  transcript in later hardening.
- Transcript-only evaluation cannot judge acoustic delivery.
- The model may misjudge factual claims without trusted reference material.
- Keep API keys in `.env`; never paste them into chat or commit them.
