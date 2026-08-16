"""SqliteStore: the three cache ports, keying, round-trips, and persistence."""

from __future__ import annotations

import pytest

from cv_agent.domain import (
    CandidateProfile,
    CandidateStatus,
    Requirement,
    RequirementKind,
    Rubric,
    RoleArchetype,
    Verdict,
    WorkExperience,
)
from cv_agent.store import ProcessedRecord, SqliteStore


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Alice",
        skills=("Go", "K8s"),
        work_experience=(WorkExperience(company="A", title="SRE", highlights=("scaled X",)),),
        source_markdown="# Alice",
    )


def _rubric() -> Rubric:
    return Rubric(
        role_archetype=RoleArchetype.TECHNICAL,
        requirements=(Requirement(id="r1", text="Go", kind=RequirementKind.MUST_HAVE),),
    )


# --- ProfileCache ---------------------------------------------------------


def test_profile_round_trip(store):
    assert store.get_profile("cv1") is None
    store.put_profile("cv1", _profile())
    got = store.get_profile("cv1")
    assert got == _profile()
    assert isinstance(got.skills, tuple)


def test_put_profile_is_idempotent_upsert(store):
    store.put_profile("cv1", _profile())
    store.put_profile("cv1", _profile().model_copy(update={"name": "Alice2"}))
    assert store.get_profile("cv1").name == "Alice2"


# --- RubricCache ----------------------------------------------------------


def test_rubric_round_trip(store):
    assert store.get_rubric("jd1") is None
    store.put_rubric("jd1", _rubric())
    got = store.get_rubric("jd1")
    assert got == _rubric()
    assert got.role_archetype is RoleArchetype.TECHNICAL


# --- ProcessedRegistry ----------------------------------------------------


def _record(cv="cv1", jd="jd1", verdict=Verdict.PASS) -> ProcessedRecord:
    return ProcessedRecord(
        cv_hash=cv,
        jd_hash=jd,
        verdict=verdict,
        status=CandidateStatus.OK,
        reasons=("all must-haves met",),
        soft_name="Alice",
        report_path="data/reports/pass__alice.md",
        created_at="2026-08-17T00:00:00Z",
    )


def test_processed_is_false_until_marked(store):
    assert store.is_processed("cv1", "jd1") is False
    store.mark_processed(_record())
    assert store.is_processed("cv1", "jd1") is True


def test_processed_keying_is_cv_and_jd(store):
    store.mark_processed(_record(cv="cv1", jd="jd1"))
    # same CV, different JD => not processed (must be re-screened) — ADR 0003
    assert store.is_processed("cv1", "jd2") is False
    assert store.is_processed("cv2", "jd1") is False


def test_get_record_returns_full_record(store):
    store.mark_processed(_record())
    rec = store.get_record("cv1", "jd1")
    assert rec.verdict is Verdict.PASS
    assert rec.reasons == ("all must-haves met",)
    assert rec.soft_name == "Alice"
    assert store.get_record("cv1", "nope") is None


def test_mark_processed_replaces_prior_verdict(store):
    store.mark_processed(_record(verdict=Verdict.PASS))
    store.mark_processed(_record(verdict=Verdict.REJECT))
    assert store.get_record("cv1", "jd1").verdict is Verdict.REJECT


# --- Persistence & lifecycle ---------------------------------------------


def test_data_persists_across_instances(tmp_path):
    db = str(tmp_path / "s.sqlite")
    with SqliteStore(db) as s:
        s.put_profile("cv1", _profile())
        s.mark_processed(_record())
    with SqliteStore(db) as s2:
        assert s2.get_profile("cv1") == _profile()
        assert s2.is_processed("cv1", "jd1") is True


def test_empty_path_is_rejected():
    with pytest.raises(ValueError):
        SqliteStore("")


def test_record_is_immutable():
    rec = _record()
    with pytest.raises(Exception):
        rec.verdict = Verdict.REJECT  # type: ignore[misc]
