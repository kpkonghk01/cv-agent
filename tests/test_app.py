"""run_screen (Phase 1 shortlist) and run_interview (Phase 2 briefs) orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from cv_agent.app import run_interview, run_screen
from cv_agent.domain import CandidateProfile, ScreeningReport, Verdict
from cv_agent.graph import uniform_clients
from cv_agent.hashing import cv_hash, jd_hash
from cv_agent.ocr import OcrResult
from cv_agent.sinks import LocalFolderSink
from cv_agent.sources import DocumentRef
from cv_agent.store import SqliteStore

JD_TEXT = "We need Go. Must have Go."
JDH = jd_hash(JD_TEXT)
RUBRIC = '{"role_archetype": "technical", "requirements": [{"id": "x", "text": "Go", "kind": "must_have"}]}'
PROFILE = '{"name": "Alice", "skills": ["Go"]}'
PASS = '{"scores": [{"requirement_id": "r1", "level": "met"}]}'
UNMET = '{"scores": [{"requirement_id": "r1", "level": "unmet"}]}'
BRIEF = "# Interview Brief"


class FakeJd:
    def read_text(self, doc_id):
        if doc_id.endswith(".meta.yaml"):
            raise FileNotFoundError(doc_id)
        return JD_TEXT


class FakeCv:
    def __init__(self, items, raise_on=()):
        self._items = items
        self._raise_on = set(raise_on)

    def list(self, since=None):
        return tuple(DocumentRef(id=k) for k in sorted(self._items))

    def read_bytes(self, doc_id):
        if doc_id in self._raise_on:
            raise OSError("unreadable CV")
        return self._items[doc_id]


class FakeJdMeta(FakeJd):
    def read_text(self, doc_id):
        if doc_id.endswith(".meta.yaml"):
            return "role_archetype: management"
        return JD_TEXT


class FakeOcr:
    def __init__(self):
        self.calls = 0

    def to_markdown(self, pdf_bytes):
        self.calls += 1
        return OcrResult(markdown="# CV")


class ScriptedClient:
    def __init__(self, sheets=()):
        self._sheets = list(sheets)

    def complete(self, messages):
        system = messages[0]["content"]
        if "screening Rubric" in system:
            return RUBRIC
        if "CandidateProfile" in system:
            return PROFILE
        if "score a candidate" in system:
            return self._sheets.pop(0)
        return BRIEF


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def notify(self, message):
        self.messages.append(message)


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def _common(store, tmp_path, cv_source, client):
    return dict(
        cv_source=cv_source,
        jd_source=FakeJd(),
        store=store,
        ocr=FakeOcr(),
        clients=uniform_clients(client),
        sink=LocalFolderSink(str(tmp_path)),
        notifier=FakeNotifier(),
        jd_id="eng.md",
        cli_overrides={},
        now="2026-09-14T00:00:00Z",
    )


# --- Phase 1 --------------------------------------------------------------


def test_screen_ranks_and_writes_one_shortlist(store, tmp_path):
    cv = FakeCv({"a.pdf": b"AAA", "b.pdf": b"BBB"})
    summary = run_screen(**_common(store, tmp_path, cv, ScriptedClient([PASS, UNMET])), top_n=None)
    assert summary.total == 2
    assert summary.shortlisted == 2
    files = [p.name for p in Path(tmp_path).glob("*.md")]
    assert files == ["shortlist__eng__all.md"]  # exactly one shortlist
    body = Path(tmp_path, "shortlist__eng__all.md").read_text(encoding="utf-8")
    # a.pdf (met -> 100) ranks above b.pdf (unmet -> 0)
    assert body.index("a.pdf") < body.index("b.pdf")


def test_screen_top_n_truncates(store, tmp_path):
    cv = FakeCv({"a.pdf": b"AAA", "b.pdf": b"BBB"})
    summary = run_screen(**_common(store, tmp_path, cv, ScriptedClient([PASS, UNMET])), top_n=1)
    assert summary.shortlisted == 1


def test_screen_limit_caps_how_many_are_scored(store, tmp_path):
    cv = FakeCv({"a.pdf": b"AAA", "b.pdf": b"BBB", "c.pdf": b"CCC"})
    summary = run_screen(**_common(store, tmp_path, cv, ScriptedClient([PASS])), limit=1)
    assert summary.total == 1  # only the first CV was OCR'd + scored


def test_screen_persists_profile_and_screening(store, tmp_path):
    cv = FakeCv({"a.pdf": b"AAA"})
    run_screen(**_common(store, tmp_path, cv, ScriptedClient([PASS])))
    h = cv_hash(b"AAA")
    assert store.get_profile(h) is not None
    assert store.get_screening(h, JDH).rank_score == 100.0


def test_screen_isolates_per_candidate_failures(store, tmp_path):
    cv = FakeCv({"a.pdf": b"AAA", "bad.pdf": b"X"}, raise_on={"bad.pdf"})
    summary = run_screen(**_common(store, tmp_path, cv, ScriptedClient([PASS])))
    assert summary.total == 1 and summary.errors == 1
    assert any("bad.pdf" in e for e in summary.error_summaries)


def test_screen_applies_meta_role_override(store, tmp_path):
    cv = FakeCv({"a.pdf": b"AAA"})
    common = _common(store, tmp_path, cv, ScriptedClient([PASS]))
    common["jd_source"] = FakeJdMeta()
    summary = run_screen(**common)
    assert summary.total == 1  # meta parsed + role override path exercised


# --- Phase 2 --------------------------------------------------------------


def _seed(store, cv_bytes=b"AAA", name="Alice"):
    """Pre-populate as if Phase 1 already screened this candidate."""
    from cv_agent.domain import Requirement, RequirementKind, Rubric

    h = cv_hash(cv_bytes)
    store.put_rubric(JDH, Rubric(requirements=(Requirement(id="r1", text="Go", kind=RequirementKind.MUST_HAVE),)))
    store.put_profile(h, CandidateProfile(name=name))
    store.put_screening(h, JDH, ScreeningReport(verdict=Verdict.PASS, rank_score=90.0))
    return h


def test_interview_by_filename_from_cache(store, tmp_path):
    _seed(store)
    cv = FakeCv({"a.pdf": b"AAA"})
    common = _common(store, tmp_path, cv, ScriptedClient())
    summary = run_interview(**common, selectors=["a.pdf"], confirm=lambda s: False)
    assert summary.generated == 1
    assert common["ocr"].calls == 0  # reused cache, no re-OCR
    assert Path(summary.briefs[0]).name.startswith("pass__")


def test_interview_by_name_from_cache(store, tmp_path):
    _seed(store, name="Alice")
    cv = FakeCv({"a.pdf": b"AAA"})
    summary = run_interview(**_common(store, tmp_path, cv, ScriptedClient()),
                            selectors=["Alice"], confirm=lambda s: False)
    assert summary.generated == 1


def test_interview_unscreened_filename_confirm_triggers_ocr(store, tmp_path):
    from cv_agent.domain import Requirement, RequirementKind, Rubric

    store.put_rubric(JDH, Rubric(requirements=(Requirement(id="r1", text="Go", kind=RequirementKind.MUST_HAVE),)))
    cv = FakeCv({"new.pdf": b"NEW"})
    common = _common(store, tmp_path, cv, ScriptedClient([PASS]))
    summary = run_interview(**common, selectors=["new.pdf"], confirm=lambda s: True)
    assert summary.generated == 1
    assert common["ocr"].calls == 1  # confirmed → OCR on demand


def test_interview_unscreened_declined_is_skipped(store, tmp_path):
    from cv_agent.domain import Requirement, RequirementKind, Rubric

    store.put_rubric(JDH, Rubric(requirements=(Requirement(id="r1", text="Go", kind=RequirementKind.MUST_HAVE),)))
    cv = FakeCv({"new.pdf": b"NEW"})
    summary = run_interview(**_common(store, tmp_path, cv, ScriptedClient()),
                            selectors=["new.pdf"], confirm=lambda s: False)
    assert summary.generated == 0
    assert any("declined" in s for s in summary.skipped)


def test_interview_unknown_name_is_skipped(store, tmp_path):
    _seed(store, name="Alice")
    cv = FakeCv({"a.pdf": b"AAA"})
    summary = run_interview(**_common(store, tmp_path, cv, ScriptedClient()),
                            selectors=["Bob"], confirm=lambda s: False)
    assert summary.generated == 0
    assert any("Bob" in s for s in summary.skipped)
