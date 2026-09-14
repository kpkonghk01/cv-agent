"""Per-candidate phase functions: screen (cache + score) and interview (brief)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cv_agent.domain import (
    CandidateProfile,
    Requirement,
    RequirementKind,
    Rubric,
    RoleArchetype,
    ScreeningReport,
    Strictness,
    Verdict,
)
from cv_agent.graph import (
    PipelineDeps,
    RunContext,
    interview_candidate,
    screen_candidate,
    uniform_clients,
)
from cv_agent.graph.reports import RejectReportMode
from cv_agent.hashing import cv_hash
from cv_agent.ocr import OcrResult
from cv_agent.sinks import LocalFolderSink
from cv_agent.store import SqliteStore

CV = b"%PDF fake"
CVH = cv_hash(CV)
PROFILE_JSON = '{"name": "Alice", "skills": ["Go"]}'
PASS_SHEET = '{"scores": [{"requirement_id": "r1", "level": "met"}]}'
BRIEF = "# Interview Brief\n..."


class FakeOcr:
    def __init__(self):
        self.calls = 0

    def to_markdown(self, pdf_bytes):
        self.calls += 1
        return OcrResult(markdown="# CV markdown")


class ScriptedClient:
    def __init__(self, sheet=PASS_SHEET):
        self._sheet = sheet
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        system = messages[0]["content"]
        if "CandidateProfile" in system:
            return PROFILE_JSON
        if "score a candidate" in system:
            return self._sheet
        return BRIEF


def _rubric():
    return Rubric(
        role_archetype=RoleArchetype.TECHNICAL,
        requirements=(Requirement(id="r1", text="Go", kind=RequirementKind.MUST_HAVE),),
    )


def _ctx():
    return RunContext(
        rubric=_rubric(),
        jd_hash="jd1",
        jd_slug="eng",
        minutes=45,
        interview_format="technical",
        output_language="zh-Hant",
        strictness=Strictness.LOOSE,
        interview_meta_hash="a" * 64,
        created_at="2026-09-14T00:00:00Z",
    )


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def _deps(store, tmp_path, client):
    return PipelineDeps(
        store=store, sink=LocalFolderSink(str(tmp_path)), ocr=FakeOcr(),
        clients=uniform_clients(client),
    )


def test_screen_candidate_ocrs_scores_and_caches(store, tmp_path):
    deps = _deps(store, tmp_path, ScriptedClient())
    digest, profile, report = screen_candidate(deps, _ctx(), "a.pdf", CV)
    assert digest == CVH
    assert profile.name == "Alice"
    assert report.verdict is Verdict.PASS
    assert report.rank_score == 100.0            # single must-have met
    assert store.get_profile(CVH) is not None    # cached
    assert store.get_screening(CVH, "jd1") is not None
    assert deps.ocr.calls == 1


def test_screen_candidate_reuses_cache_without_ocr_or_llm(store, tmp_path):
    store.put_profile(CVH, CandidateProfile(name="Alice"))
    store.put_screening(CVH, "jd1", ScreeningReport(verdict=Verdict.PASS, rank_score=88.0))
    client = ScriptedClient()
    deps = _deps(store, tmp_path, client)
    _, profile, report = screen_candidate(deps, _ctx(), "a.pdf", CV)
    assert report.rank_score == 88.0
    assert deps.ocr.calls == 0
    assert client.calls == 0


def test_screen_candidate_reuses_cached_profile_and_rescreens(store, tmp_path):
    # Profile cached but not screening: OCR is skipped, only screening runs.
    store.put_profile(CVH, CandidateProfile(name="Alice", skills=("Go",)))
    deps = _deps(store, tmp_path, ScriptedClient())
    _, profile, report = screen_candidate(deps, _ctx(), "a.pdf", CV)
    assert profile.name == "Alice"
    assert deps.ocr.calls == 0  # cached profile → no re-OCR
    assert report.verdict is Verdict.PASS
    assert store.get_screening(CVH, "jd1") is not None


def test_screen_candidate_survives_text_layer_failure(store, tmp_path, monkeypatch):
    # The best-effort text-layer scavenge must never block screening if it errors.
    import cv_agent.graph.phases as phases

    def _boom(_):
        raise RuntimeError("pdfplumber blew up")

    monkeypatch.setattr(phases, "extract_text_layer", _boom)
    deps = _deps(store, tmp_path, ScriptedClient())
    _, profile, report = screen_candidate(deps, _ctx(), "x.pdf", b"%PDF fake")
    assert profile.name == "Alice"
    assert report.verdict is Verdict.PASS


def test_interview_candidate_writes_brief_with_scorecard(store, tmp_path):
    deps = _deps(store, tmp_path, ScriptedClient())
    profile = CandidateProfile(name="Alice")
    report = ScreeningReport(verdict=Verdict.PASS, borderline=True, rank_score=70.0)
    path = interview_candidate(deps, _ctx(), CVH, profile, report)
    text = Path(path).read_text(encoding="utf-8")
    assert Path(path).name.startswith("pass__")
    assert BRIEF in text
    assert "篩選評分卡" in text
