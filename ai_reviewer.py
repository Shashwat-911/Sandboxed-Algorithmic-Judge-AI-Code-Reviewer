"""
ai_reviewer.py — Calls the local Ollama instance with a structured prompt
designed for code-specific models (qwen2.5-coder / codellama).

The review is best-effort: any HTTP or model error returns a graceful
fallback string rather than crashing the worker.
"""

import logging

import httpx

from config import settings

log = logging.getLogger(__name__)

# Prompt template — designed to elicit structured, technical critique
_REVIEW_PROMPT = """\
You are an expert competitive-programming judge and algorithm analyst. \
A user submitted the following code for automated evaluation. \
Provide a concise but technically rigorous review.

=== SUBMISSION DETAILS ===
Language      : {language}
Execution Time: {execution_time_ms:.2f} ms
Exit Code     : {exit_code}
Stdout        : {stdout}

=== SOURCE CODE ===
```{language}
{code}
```

=== REQUIRED ANALYSIS (use these exact headers) ===

## 1. Time Complexity
State the Big-O time complexity with a brief justification referencing specific \
code constructs (loops, recursion, library calls).

## 2. Space Complexity
State the Big-O space complexity including auxiliary space.

## 3. Algorithm Assessment
Is this the most efficient algorithm for this problem class? \
If not, name the optimal approach and its complexity.

## 4. Code Quality & Edge Cases
Identify up to three code-quality issues or unhandled edge cases.

## 5. Concrete Optimization
Provide ONE specific, actionable improvement with a short code snippet.

Be direct and precise. Do not repeat the code in full.
"""

# Ollama /api/generate request timeout (seconds)
_HTTP_TIMEOUT = 120.0


def get_ai_review(
    *,
    code: str,
    language: str,
    stdout: str,
    exit_code: int,
    execution_time_ms: float,
) -> str:
    """
    Send the submission to the local Ollama HTTP API and return the model's
    critique as a plain string.

    Returns a fallback message on any network / model error so the worker
    can still finalise the DB record.
    """
    prompt = _REVIEW_PROMPT.format(
        language=language,
        execution_time_ms=execution_time_ms,
        exit_code=exit_code,
        stdout=stdout[:2000],   # Guard against huge outputs in the prompt
        code=code[:8000],       # Guard against very large source files
    )

    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,     # Low temperature for deterministic analysis
            "num_predict": 1024,    # Sufficient for structured review
        },
    }

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            review_text: str = data.get("response", "").strip()

        if not review_text:
            return "AI review returned an empty response."
        return review_text

    except httpx.ConnectError:
        log.warning("Ollama service unreachable at %s", settings.OLLAMA_BASE_URL)
        return "AI review unavailable: Ollama service is not reachable."
    except httpx.TimeoutException:
        log.warning("Ollama request timed out after %.0f s", _HTTP_TIMEOUT)
        return "AI review unavailable: model inference timed out."
    except Exception as exc:
        log.exception("Unexpected error calling Ollama: %s", exc)
        return f"AI review unavailable: {exc}"
