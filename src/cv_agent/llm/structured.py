"""Schema-validated LLM calls with retry-on-invalid feedback (ADR 0002).

The product is model-agnostic and must not trust any single model's JSON discipline,
so every structured node goes through here: call → extract JSON → validate against a
Pydantic schema → on failure, feed the error back and retry → give up after N retries.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

Message = dict[str, str]
T = TypeVar("T", bound=BaseModel)


class LLMOutputError(RuntimeError):
    """The model never produced output matching the required schema."""


class LLMClient(Protocol):
    def complete(self, messages: Sequence[Message]) -> str: ...


def _extract_json(text: str) -> str:
    """Best-effort: unwrap ```code fences``` or a JSON object embedded in prose."""
    stripped = text.strip()
    if "```" in stripped:
        # take the content of the first fenced block
        parts = stripped.split("```")
        if len(parts) >= 3:
            block = parts[1]
            if block.lstrip().lower().startswith("json"):
                block = block.lstrip()[4:]
            stripped = block.strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def structured_call(
    client: LLMClient,
    schema: type[T],
    messages: Sequence[Message],
    *,
    max_retries: int = 2,
) -> T:
    """Return an instance of ``schema`` parsed from the model, retrying on bad output."""
    convo: list[Message] = [dict(m) for m in messages]
    last_error: Exception | None = None

    for _ in range(max_retries + 1):
        raw = client.complete(convo)
        try:
            return schema.model_validate_json(_extract_json(raw))
        except (ValidationError, ValueError) as err:
            last_error = err
            convo = convo + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        "Your previous reply did not match the required JSON schema: "
                        f"{err}. Reply with ONLY valid JSON matching the schema, no prose."
                    ),
                },
            ]

    raise LLMOutputError(
        f"Model failed to satisfy {schema.__name__} after {max_retries + 1} attempts: "
        f"{last_error}"
    )
