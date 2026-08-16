"""Domain models (ubiquitous language — see CONTEXT.md). All models are immutable."""

from __future__ import annotations

from cv_agent.domain.candidate import (
    CandidateProfile,
    Certification,
    Contact,
    Education,
    JobHoppingSignal,
    Project,
    WorkExperience,
)
from cv_agent.domain.enums import (
    CandidateStatus,
    RequirementKind,
    RoleArchetype,
    ScoreLevel,
    Strictness,
    Verdict,
)
from cv_agent.domain.rubric import Requirement, Rubric
from cv_agent.domain.screening import RequirementScore, ScreeningReport

__all__ = [
    "CandidateProfile",
    "Certification",
    "Contact",
    "Education",
    "JobHoppingSignal",
    "Project",
    "WorkExperience",
    "CandidateStatus",
    "RequirementKind",
    "RoleArchetype",
    "ScoreLevel",
    "Strictness",
    "Verdict",
    "Requirement",
    "Rubric",
    "RequirementScore",
    "ScreeningReport",
]
