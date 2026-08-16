"""Reject report rendering (pure): full / concise / suppressed."""

from __future__ import annotations

from cv_agent.domain import (
    CandidateProfile,
    RequirementScore,
    ScoreLevel,
    ScreeningReport,
    Verdict,
)
from cv_agent.graph import RejectReportMode, render_reject_report


def _report():
    return ScreeningReport(
        verdict=Verdict.REJECT,
        reasons=("Unmet must-have: K8s",),
        scores=(RequirementScore(requirement_id="r1", level=ScoreLevel.UNMET, evidence="none"),),
    )


def test_none_mode_suppresses_file():
    assert render_reject_report(_report(), CandidateProfile(name="A"), RejectReportMode.NONE) is None


def test_concise_has_reasons_but_no_scores():
    out = render_reject_report(_report(), CandidateProfile(name="A"), RejectReportMode.CONCISE)
    assert "Unmet must-have: K8s" in out
    assert "Requirement scores" not in out


def test_full_includes_requirement_scores():
    out = render_reject_report(_report(), CandidateProfile(name="A"), RejectReportMode.FULL)
    assert "Requirement scores" in out
    assert "`r1`: unmet" in out


def test_missing_name_falls_back():
    out = render_reject_report(_report(), CandidateProfile(), RejectReportMode.CONCISE)
    assert "Unknown candidate" in out
