"""LLM I/O schemas that are transport-only (not persisted domain concepts)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from cv_agent.domain.screening import RequirementScore


class ScoreSheet(BaseModel):
    """What the SCREEN node asks the model for: a level per Requirement, no verdict."""

    model_config = ConfigDict(frozen=True)

    scores: tuple[RequirementScore, ...] = ()
