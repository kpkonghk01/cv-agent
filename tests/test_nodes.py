"""Node contract tests: input→output mapping with a mocked client (no network)."""

from __future__ import annotations

from cv_agent.domain import (
    CandidateProfile,
    RoleArchetype,
    Strictness,
    Verdict,
)
from cv_agent.nodes import interview_brief, jd_to_rubric, screen, structure_cv


class FakeClient:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[list[dict]] = []

    def complete(self, messages):
        self.calls.append([dict(m) for m in messages])
        return self._response


def _user_text(calls) -> str:
    return "\n".join(m["content"] for m in calls[0] if m["role"] == "user")


# --- structure_cv ---------------------------------------------------------


def test_structure_cv_maps_and_attaches_source_markdown():
    client = FakeClient('{"name": "Alice", "skills": ["Go"]}')
    profile = structure_cv(client, "# Alice\nGo dev", ocr_confidence=0.42)
    assert profile.name == "Alice"
    assert profile.skills == ("Go",)
    assert profile.source_markdown == "# Alice\nGo dev"  # attached by the node, not the LLM
    assert profile.ocr_confidence == 0.42
    assert "# Alice\nGo dev" in _user_text(client.calls)


# --- jd_to_rubric ---------------------------------------------------------


RUBRIC_JSON = (
    '{"role_archetype": "technical", "requirements": ['
    '{"id": "x", "text": "5y backend", "kind": "must_have"},'
    '{"id": "y", "text": "Go", "kind": "nice_to_have"}]}'
)


def test_jd_to_rubric_reids_requirements_sequentially():
    rubric = jd_to_rubric(FakeClient(RUBRIC_JSON), "JD text")
    assert tuple(r.id for r in rubric.requirements) == ("r1", "r2")
    assert rubric.role_archetype is RoleArchetype.TECHNICAL


def test_jd_to_rubric_applies_role_override():
    rubric = jd_to_rubric(
        FakeClient(RUBRIC_JSON), "JD text", role_override=RoleArchetype.MANAGEMENT
    )
    assert rubric.role_archetype is RoleArchetype.MANAGEMENT


# --- screen ---------------------------------------------------------------


def test_screen_uses_deterministic_rule_over_llm_scores():
    rubric = jd_to_rubric(FakeClient(RUBRIC_JSON), "JD")  # r1 must, r2 nice
    sheet = (
        '{"scores": ['
        '{"requirement_id": "r1", "level": "met"},'
        '{"requirement_id": "r2", "level": "unmet"}]}'
    )
    report = screen(FakeClient(sheet), _profile(), rubric, strictness=Strictness.LOOSE)
    assert report.verdict is Verdict.PASS  # must-have met
    assert report.score == 0.0  # nice-to-have unmet
    assert report.borderline is True


def test_screen_rejects_when_llm_marks_must_have_unmet():
    rubric = jd_to_rubric(FakeClient(RUBRIC_JSON), "JD")
    sheet = '{"scores": [{"requirement_id": "r1", "level": "unmet"}]}'
    report = screen(FakeClient(sheet), _profile(), rubric)
    assert report.verdict is Verdict.REJECT


# --- interview_brief ------------------------------------------------------


def test_interview_brief_returns_markdown_and_includes_context():
    client = FakeClient("# Interview Brief\n...")
    out = interview_brief(
        client,
        _profile(),
        jd_to_rubric(FakeClient(RUBRIC_JSON), "JD"),
        _pass_report(),
        minutes=45,
        interview_format="technical",
        output_language="zh-Hant",
    )
    assert out == "# Interview Brief\n..."
    text = _user_text(client.calls)
    assert "Alice" in text
    assert "45" in text
    assert "technical" in text


def test_interview_brief_includes_prev_scorecard_when_given():
    client = FakeClient("brief")
    interview_brief(
        client,
        _profile(),
        jd_to_rubric(FakeClient(RUBRIC_JSON), "JD"),
        _pass_report(),
        minutes=30,
        interview_format="mixed",
        output_language="zh-Hant",
        prev_scorecard="Round 1: strong on Go, weak on architecture.",
    )
    assert "Round 1: strong on Go" in _user_text(client.calls)


# --- helpers --------------------------------------------------------------


def _profile() -> CandidateProfile:
    return CandidateProfile(name="Alice", skills=("Go",), source_markdown="# Alice")


def _pass_report():
    from cv_agent.domain import ScreeningReport

    return ScreeningReport(verdict=Verdict.PASS, borderline=True, score=0.0)
