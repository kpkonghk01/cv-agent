"""The deterministic screening rule (AGENT.md): must-have gating, loose default, borderline."""

from __future__ import annotations

from cv_agent.domain import (
    Requirement,
    RequirementKind,
    RequirementScore,
    Rubric,
    ScoreLevel,
    Strictness,
    Verdict,
)
from cv_agent.screening_rule import decide_verdict

MUST_A = Requirement(id="m1", text="5y backend", kind=RequirementKind.MUST_HAVE)
MUST_B = Requirement(id="m2", text="K8s", kind=RequirementKind.MUST_HAVE)
NICE_A = Requirement(id="n1", text="Go", kind=RequirementKind.NICE_TO_HAVE)
NICE_B = Requirement(id="n2", text="gRPC", kind=RequirementKind.NICE_TO_HAVE)


def _rubric(*reqs) -> Rubric:
    return Rubric(requirements=tuple(reqs))


def _score(rid, level) -> RequirementScore:
    return RequirementScore(requirement_id=rid, level=level)


def test_all_met_passes_and_is_not_borderline():
    rubric = _rubric(MUST_A, NICE_A)
    report = decide_verdict(
        rubric, [_score("m1", ScoreLevel.MET), _score("n1", ScoreLevel.MET)]
    )
    assert report.verdict is Verdict.PASS
    assert report.borderline is False
    assert report.score == 1.0


def test_unmet_must_have_rejects():
    rubric = _rubric(MUST_A, MUST_B)
    report = decide_verdict(
        rubric, [_score("m1", ScoreLevel.MET), _score("m2", ScoreLevel.UNMET)]
    )
    assert report.verdict is Verdict.REJECT
    assert any("K8s" in r for r in report.reasons)


def test_partial_must_have_passes_when_loose_but_is_borderline():
    rubric = _rubric(MUST_A)
    report = decide_verdict(
        rubric, [_score("m1", ScoreLevel.PARTIAL)], strictness=Strictness.LOOSE
    )
    assert report.verdict is Verdict.PASS
    assert report.borderline is True


def test_partial_must_have_rejects_when_strict():
    rubric = _rubric(MUST_A)
    report = decide_verdict(
        rubric, [_score("m1", ScoreLevel.PARTIAL)], strictness=Strictness.STRICT
    )
    assert report.verdict is Verdict.REJECT


def test_weak_nice_to_haves_make_a_pass_borderline():
    rubric = _rubric(MUST_A, NICE_A, NICE_B)
    report = decide_verdict(
        rubric,
        [
            _score("m1", ScoreLevel.MET),
            _score("n1", ScoreLevel.UNMET),
            _score("n2", ScoreLevel.UNMET),
        ],
    )
    assert report.verdict is Verdict.PASS
    assert report.score == 0.0
    assert report.borderline is True


def test_no_nice_to_haves_scores_full_and_not_borderline():
    rubric = _rubric(MUST_A)
    report = decide_verdict(rubric, [_score("m1", ScoreLevel.MET)])
    assert report.score == 1.0
    assert report.borderline is False


def test_partial_nice_to_have_is_half_weight():
    rubric = _rubric(MUST_A, NICE_A, NICE_B)
    report = decide_verdict(
        rubric,
        [
            _score("m1", ScoreLevel.MET),
            _score("n1", ScoreLevel.MET),
            _score("n2", ScoreLevel.PARTIAL),
        ],
    )
    assert report.score == 0.75  # (1 + 0.5) / 2


def test_missing_score_is_treated_as_unmet():
    rubric = _rubric(MUST_A, MUST_B)
    report = decide_verdict(rubric, [_score("m1", ScoreLevel.MET)])  # m2 absent
    assert report.verdict is Verdict.REJECT


def test_report_scores_follow_rubric_order_and_length():
    rubric = _rubric(MUST_A, NICE_A, MUST_B)
    report = decide_verdict(rubric, [_score("m1", ScoreLevel.MET)])
    assert tuple(s.requirement_id for s in report.scores) == ("m1", "n1", "m2")


def test_borderline_threshold_is_configurable():
    rubric = _rubric(MUST_A, NICE_A, NICE_B)
    scores = [
        _score("m1", ScoreLevel.MET),
        _score("n1", ScoreLevel.MET),
        _score("n2", ScoreLevel.UNMET),
    ]  # nice_score = 0.5
    assert decide_verdict(rubric, scores, borderline_threshold=0.4).borderline is False
    assert decide_verdict(rubric, scores, borderline_threshold=0.6).borderline is True
