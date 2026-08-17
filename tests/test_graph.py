"""Per-candidate graph: dedup skip, profile-cache reuse, verdict routing, output writing.

Integration-style: real SqliteStore(:memory:) + LocalFolderSink(tmp) + fake OCR/client.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cv_agent.domain import (
    CandidateProfile,
    CandidateStatus,
    Requirement,
    RequirementKind,
    Rubric,
    RoleArchetype,
    Strictness,
    Verdict,
)
from cv_agent.config import NodeName
from cv_agent.graph import (
    PipelineDeps,
    RejectReportMode,
    RunContext,
    build_candidate_graph,
    uniform_clients,
)
from cv_agent.hashing import cv_hash
from cv_agent.ocr import OcrResult
from cv_agent.store import ProcessedRecord, SqliteStore

CV = b"%PDF fake"
CVH = cv_hash(CV)

PROFILE_JSON = '{"name": "Alice", "skills": ["Go"]}'
PASS_SHEET = '{"scores": [{"requirement_id": "r1", "level": "met"}]}'
REJECT_SHEET = '{"scores": [{"requirement_id": "r1", "level": "unmet"}]}'
BRIEF = "# Interview Brief\n..."


class FakeOcr:
    def __init__(self):
        self.calls = 0

    def to_markdown(self, pdf_bytes):
        self.calls += 1
        return OcrResult(markdown="# CV markdown")


class ScriptedClient:
    """Routes by the system prompt so call ordering doesn't matter."""

    def __init__(self, sheet_json):
        self._sheet = sheet_json
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


def _ctx(reject_mode=RejectReportMode.FULL, force_pass=False):
    return RunContext(
        rubric=_rubric(),
        jd_hash="jd1",
        jd_slug="eng",
        minutes=45,
        interview_format="technical",
        output_language="zh-Hant",
        strictness=Strictness.LOOSE,
        reject_mode=reject_mode,
        interview_meta_hash="a" * 64,
        created_at="2026-08-17T00:00:00Z",
        force_pass=force_pass,
    )


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def _deps(store, tmp_path, sheet):
    from cv_agent.sinks import LocalFolderSink

    return PipelineDeps(
        store=store,
        sink=LocalFolderSink(str(tmp_path)),
        ocr=FakeOcr(),
        clients=uniform_clients(ScriptedClient(sheet)),
    )


def _run(deps, ctx):
    return build_candidate_graph(deps, ctx).invoke({"cv_id": "a.pdf", "cv_bytes": CV})


def test_pass_writes_brief_and_records_processed(store, tmp_path):
    deps = _deps(store, tmp_path, PASS_SHEET)
    state = _run(deps, _ctx())
    assert state["verdict"] == "pass"
    assert Path(state["report_path"]).name.startswith("pass__")
    content = Path(state["report_path"]).read_text(encoding="utf-8")
    assert BRIEF in content
    assert "篩選評分卡" in content  # deterministic scorecard prepended to the brief
    assert store.is_processed(CVH, "jd1") is True
    assert store.get_record(CVH, "jd1").verdict is Verdict.PASS
    assert deps.ocr.calls == 1
    assert store.get_profile(CVH) is not None  # cached for reuse


def test_reject_full_writes_report(store, tmp_path):
    deps = _deps(store, tmp_path, REJECT_SHEET)
    state = _run(deps, _ctx(RejectReportMode.FULL))
    assert state["verdict"] == "reject"
    assert Path(state["report_path"]).name.startswith("reject__")
    assert "Requirement scores" in Path(state["report_path"]).read_text(encoding="utf-8")
    assert store.get_record(CVH, "jd1").verdict is Verdict.REJECT


def test_reject_none_mode_writes_no_file_but_records(store, tmp_path):
    deps = _deps(store, tmp_path, REJECT_SHEET)
    state = _run(deps, _ctx(RejectReportMode.NONE))
    assert state["report_path"] is None
    assert list(Path(tmp_path).glob("*.md")) == []
    assert store.get_record(CVH, "jd1").verdict is Verdict.REJECT


def test_already_processed_is_skipped(store, tmp_path):
    store.mark_processed(
        ProcessedRecord(cv_hash=CVH, jd_hash="jd1", verdict=Verdict.PASS,
                        status=CandidateStatus.OK, created_at="earlier")
    )
    deps = _deps(store, tmp_path, PASS_SHEET)
    state = _run(deps, _ctx())
    assert state["skipped"] is True
    assert deps.ocr.calls == 0
    assert deps.clients[NodeName.SCREEN].calls == 0
    assert list(Path(tmp_path).glob("*.md")) == []


def test_force_pass_routes_a_reject_to_the_interview_node(store, tmp_path):
    deps = _deps(store, tmp_path, REJECT_SHEET)
    state = _run(deps, _ctx(force_pass=True))
    assert state["verdict"] == "pass"
    assert Path(state["report_path"]).name.startswith("pass__")
    content = Path(state["report_path"]).read_text(encoding="utf-8")
    assert BRIEF in content
    assert "篩選評分卡" in content  # deterministic scorecard prepended to the brief
    assert store.get_record(CVH, "jd1").verdict is Verdict.PASS


def test_cached_profile_skips_ocr_and_structure(store, tmp_path):
    store.put_profile(CVH, CandidateProfile(name="Alice", skills=("Go",)))
    deps = _deps(store, tmp_path, PASS_SHEET)
    state = _run(deps, _ctx())
    assert state["verdict"] == "pass"
    assert deps.ocr.calls == 0  # OCR skipped
    assert deps.clients[NodeName.SCREEN].calls == 2  # screen + interview only (no structure)
