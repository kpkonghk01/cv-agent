"""Domain model tests: immutability, defaults, and rubric partitioning."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cv_agent.domain import (
    CandidateProfile,
    Requirement,
    RequirementKind,
    Rubric,
    RoleArchetype,
    ScoreLevel,
    ScreeningReport,
    RequirementScore,
    Verdict,
    WorkExperience,
)


def test_candidate_profile_defaults_are_empty_and_typed():
    p = CandidateProfile()
    assert p.name is None
    assert p.skills == ()
    assert p.work_experience == ()
    assert p.source_markdown == ""


def test_sequences_are_coerced_to_tuples():
    p = CandidateProfile(skills=["Go", "K8s"], work_experience=[WorkExperience(company="A")])
    assert isinstance(p.skills, tuple)
    assert isinstance(p.work_experience, tuple)
    assert p.skills == ("Go", "K8s")


def test_profile_is_immutable():
    p = CandidateProfile(name="Alice")
    with pytest.raises(ValidationError):
        p.name = "Bob"  # type: ignore[misc]


def test_rubric_partitions_must_and_nice():
    rubric = Rubric(
        role_archetype=RoleArchetype.TECHNICAL,
        requirements=(
            Requirement(id="r1", text="5y backend", kind=RequirementKind.MUST_HAVE),
            Requirement(id="r2", text="Go", kind=RequirementKind.NICE_TO_HAVE),
            Requirement(id="r3", text="K8s", kind=RequirementKind.MUST_HAVE),
        ),
    )
    assert tuple(r.id for r in rubric.must_haves) == ("r1", "r3")
    assert tuple(r.id for r in rubric.nice_to_haves) == ("r2",)
    assert rubric.must_haves[0].is_must_have is True


def test_rubric_defaults_to_hybrid_archetype():
    assert Rubric().role_archetype is RoleArchetype.HYBRID


def test_enum_values_are_stable_strings():
    # Values are persisted/serialized — pin them so storage round-trips stay valid.
    assert ScoreLevel.PARTIAL.value == "partial"
    assert Verdict.PASS.value == "pass"
    assert RoleArchetype.MANAGEMENT.value == "management"


def test_screening_report_is_pass_helper():
    passed = ScreeningReport(verdict=Verdict.PASS)
    rejected = ScreeningReport(verdict=Verdict.REJECT)
    assert passed.is_pass is True
    assert rejected.is_pass is False


def test_requirement_score_optional_fields():
    s = RequirementScore(requirement_id="r1", level=ScoreLevel.MET)
    assert s.evidence is None
    assert s.confidence is None
