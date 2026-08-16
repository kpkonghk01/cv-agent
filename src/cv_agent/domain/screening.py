"""Screening Report — the Filter's raw output for one Candidate against one JD.

Internal only: persisted in SQLite, never written to the ReportSink (see AGENT.md).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cv_agent.domain.enums import ScoreLevel, Verdict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class RequirementScore(_Frozen):
    """Evidence-based score for one Requirement (see ADR 0004)."""

    requirement_id: str
    level: ScoreLevel
    evidence: str | None = None
    confidence: float | None = None


class ScreeningReport(_Frozen):
    scores: tuple[RequirementScore, ...] = ()
    verdict: Verdict = Verdict.REJECT
    borderline: bool = False
    score: float = 0.0
    reasons: tuple[str, ...] = ()

    @property
    def is_pass(self) -> bool:
        return self.verdict is Verdict.PASS
