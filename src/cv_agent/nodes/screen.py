"""SCREEN node: LLM scores each Requirement; the deterministic rule decides the verdict."""

from __future__ import annotations

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.enums import Strictness
from cv_agent.domain.rubric import Rubric
from cv_agent.domain.screening import ScreeningReport
from cv_agent.llm.structured import LLMClient, structured_call
from cv_agent.nodes.prompts import screen_messages
from cv_agent.nodes.schemas import ScoreSheet
from cv_agent.screening_rule import decide_verdict


def screen(
    client: LLMClient,
    profile: CandidateProfile,
    rubric: Rubric,
    *,
    strictness: Strictness = Strictness.LOOSE,
    max_retries: int = 2,
) -> ScreeningReport:
    """Get evidence-based scores from the model, then apply the deterministic rule."""
    sheet = structured_call(
        client, ScoreSheet, screen_messages(profile, rubric), max_retries=max_retries
    )
    return decide_verdict(rubric, sheet.scores, strictness=strictness)
