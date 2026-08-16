"""Concrete OpenAI-compatible client (BYOK — ADR 0002).

The ``openai`` SDK is imported lazily inside ``__init__`` so the rest of the package
(and its unit tests) can run without the dependency installed; only constructing a
real client needs it. This is real IO, validated by offline evals, not unit tests.
"""

from __future__ import annotations

from collections.abc import Sequence

from cv_agent.config import LLMConfig
from cv_agent.llm.structured import Message


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig, *, temperature: float = 0.2) -> None:
        from openai import OpenAI  # lazy: keeps openai optional for tests

        self._client = OpenAI(base_url=config.base_url, api_key=config.api_key)
        self._model = config.model
        self._temperature = temperature

    def complete(self, messages: Sequence[Message]) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=list(messages),
            temperature=self._temperature,
        )
        return resp.choices[0].message.content or ""
