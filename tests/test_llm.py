"""structured_call: parse → validate → retry-with-feedback → fail. Mocked client, no network."""

from __future__ import annotations

import pytest

from cv_agent.config import LLMConfig  # a simple 3-field frozen model, reused as a schema
from cv_agent.llm import LLMOutputError, structured_call

VALID = '{"base_url": "u", "api_key": "k", "model": "m"}'


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete(self, messages):
        self.calls.append([dict(m) for m in messages])
        assert self._responses, "FakeClient ran out of scripted responses"
        return self._responses.pop(0)


def _msgs():
    return [{"role": "user", "content": "give me config"}]


def test_valid_json_is_parsed_into_the_schema():
    client = FakeClient([VALID])
    out = structured_call(client, LLMConfig, _msgs())
    assert out == LLMConfig(base_url="u", api_key="k", model="m")
    assert len(client.calls) == 1


def test_strips_markdown_code_fences():
    client = FakeClient([f"```json\n{VALID}\n```"])
    assert structured_call(client, LLMConfig, _msgs()).model == "m"


def test_extracts_json_embedded_in_prose():
    client = FakeClient([f"Sure, here it is: {VALID} — hope that helps!"])
    assert structured_call(client, LLMConfig, _msgs()).api_key == "k"


def test_retries_on_unparseable_json_then_succeeds():
    client = FakeClient(["not json at all", VALID])
    out = structured_call(client, LLMConfig, _msgs())
    assert out.base_url == "u"
    assert len(client.calls) == 2
    # the retry must feed the failure back to the model
    retry_convo = client.calls[1]
    assert any("json" in m["content"].lower() for m in retry_convo if m["role"] == "user")
    assert any(m["role"] == "assistant" for m in retry_convo)


def test_retries_on_schema_violation():
    client = FakeClient(['{"base_url": "only-this"}', VALID])
    assert structured_call(client, LLMConfig, _msgs()).model == "m"
    assert len(client.calls) == 2


def test_raises_after_exhausting_retries():
    client = FakeClient(["bad", "bad", "bad"])
    with pytest.raises(LLMOutputError):
        structured_call(client, LLMConfig, _msgs(), max_retries=2)
    assert len(client.calls) == 3


def test_max_retries_zero_means_single_attempt():
    client = FakeClient(["bad"])
    with pytest.raises(LLMOutputError):
        structured_call(client, LLMConfig, _msgs(), max_retries=0)
    assert len(client.calls) == 1


def test_schema_is_injected_into_the_prompt():
    # A model in JSON mode needs to know WHICH fields to emit, not just "valid JSON".
    client = FakeClient([VALID])
    structured_call(client, LLMConfig, _msgs())
    sent = " ".join(m["content"] for m in client.calls[0])
    assert "JSON Schema" in sent
    assert "base_url" in sent and "model" in sent  # schema field names reach the model


def test_original_messages_are_not_mutated():
    msgs = _msgs()
    structured_call(FakeClient([VALID]), LLMConfig, msgs)
    assert msgs == [{"role": "user", "content": "give me config"}]
