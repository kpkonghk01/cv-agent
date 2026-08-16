"""INTERVIEW node: draft the pre-interview brief (Markdown) for a passing candidate."""

from __future__ import annotations

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.rubric import Rubric
from cv_agent.domain.screening import ScreeningReport
from cv_agent.llm.structured import LLMClient
from cv_agent.nodes.prompts import brief_messages


def interview_brief(
    client: LLMClient,
    profile: CandidateProfile,
    rubric: Rubric,
    report: ScreeningReport,
    *,
    minutes: int,
    interview_format: str,
    output_language: str,
    prev_scorecard: str | None = None,
) -> str:
    """Return the interview brief as Markdown (a document, not a strict schema)."""
    messages = brief_messages(
        profile,
        rubric,
        report,
        minutes=minutes,
        interview_format=interview_format,
        output_language=output_language,
        prev_scorecard=prev_scorecard,
    )
    return client.complete(messages)
