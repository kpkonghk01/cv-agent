"""Reject report rendering (pure): full / concise / suppressed."""

from __future__ import annotations

from cv_agent.domain import (
    CandidateProfile,
    Requirement,
    RequirementKind,
    RequirementScore,
    Rubric,
    ScoreLevel,
    ScreeningReport,
    Verdict,
)
from cv_agent.graph import RejectReportMode, render_reject_report, render_scorecard


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
    assert "`r1`" in out and "**unmet**" in out  # falls back to id without a rubric


def test_full_with_rubric_shows_requirement_text_and_kind():
    rubric = Rubric(
        requirements=(Requirement(id="r1", text="精通 Python", kind=RequirementKind.MUST_HAVE),)
    )
    out = render_reject_report(
        _report(), CandidateProfile(name="A"), RejectReportMode.FULL, rubric=rubric
    )
    assert "精通 Python" in out          # the actual requirement, not just `r1`
    assert "must-have" in out
    assert "**unmet**" in out


def test_scorecard_shows_text_kind_level_and_evidence():
    rubric = Rubric(
        requirements=(Requirement(id="r1", text="精通 Python", kind=RequirementKind.MUST_HAVE),)
    )
    card = render_scorecard(_report(), rubric)
    assert "精通 Python" in card
    assert "must-have" in card
    assert "**unmet**" in card
    assert "none" in card  # evidence


def test_scorecard_falls_back_to_id_without_rubric():
    assert "`r1`" in render_scorecard(_report(), None)


def test_missing_name_falls_back():
    out = render_reject_report(_report(), CandidateProfile(), RejectReportMode.CONCISE)
    assert "Unknown candidate" in out
