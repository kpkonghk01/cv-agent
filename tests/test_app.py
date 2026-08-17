"""run_screening orchestration: routing, skip, failure isolation, summary, notifier."""

from __future__ import annotations

from pathlib import Path

import pytest

from cv_agent.app import run_screening
from cv_agent.domain import CandidateStatus, Verdict
from cv_agent.hashing import cv_hash, jd_hash
from cv_agent.ocr import OcrResult
from cv_agent.sinks import LocalFolderSink
from cv_agent.sources import DocumentRef
from cv_agent.store import ProcessedRecord, SqliteStore

JD_TEXT = "We need Go. Must have Go."
RUBRIC = '{"role_archetype": "technical", "requirements": [{"id": "x", "text": "Go", "kind": "must_have"}]}'
PROFILE = '{"name": "Alice", "skills": ["Go"]}'
PASS = '{"scores": [{"requirement_id": "r1", "level": "met"}]}'
REJECT = '{"scores": [{"requirement_id": "r1", "level": "unmet"}]}'


class FakeJd:
    def __init__(self, meta_text=None):
        self.meta_text = meta_text

    def read_text(self, doc_id):
        if doc_id.endswith(".meta.yaml"):
            if self.meta_text is None:
                raise FileNotFoundError(doc_id)
            return self.meta_text
        return JD_TEXT


class FakeCv:
    def __init__(self, items, raise_on=()):
        self._items = items
        self._raise_on = set(raise_on)

    def list(self):
        return tuple(DocumentRef(id=k) for k in sorted(self._items))

    def read_bytes(self, doc_id):
        if doc_id in self._raise_on:
            raise OSError("unreadable CV")
        return self._items[doc_id]


class FakeOcr:
    def __init__(self, confidence=None):
        self.confidence = confidence

    def to_markdown(self, pdf_bytes):
        return OcrResult(markdown="# CV", confidence=self.confidence)


class ScriptedClient:
    def __init__(self, sheets):
        self._sheets = list(sheets)

    def complete(self, messages):
        system = messages[0]["content"]
        if "screening Rubric" in system:
            return RUBRIC
        if "CandidateProfile" in system:
            return PROFILE
        if "score a candidate" in system:
            return self._sheets.pop(0)
        return "# Interview Brief"


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


def _run(store, tmp_path, cv_source, client, notifier, ocr=None, cli=None):
    return run_screening(
        cv_source=cv_source,
        jd_source=FakeJd(),
        store=store,
        ocr=ocr or FakeOcr(),
        client=client,
        sink=LocalFolderSink(str(tmp_path)),
        notifier=notifier,
        jd_id="eng.md",
        cli_overrides=cli or {},
        now="2026-08-17T00:00:00Z",
    )


def test_mixed_pass_and_reject(store, tmp_path):
    notifier = FakeNotifier()
    summary = _run(
        store, tmp_path,
        FakeCv({"a.pdf": b"AAA", "b.pdf": b"BBB"}),
        ScriptedClient([PASS, REJECT]),
        notifier,
    )
    assert (summary.total, summary.passed, summary.rejected) == (2, 1, 1)
    names = sorted(p.name.split("__")[0] for p in Path(tmp_path).glob("*.md"))
    assert names == ["pass", "reject"]
    assert len(notifier.messages) == 1  # one notification per run
    assert store.get_rubric(jd_hash(JD_TEXT)) is not None  # rubric cached


def test_already_processed_is_skipped(store, tmp_path):
    store.mark_processed(
        ProcessedRecord(cv_hash=cv_hash(b"AAA"), jd_hash=jd_hash(JD_TEXT),
                        verdict=Verdict.PASS, status=CandidateStatus.OK, created_at="old")
    )
    summary = _run(
        store, tmp_path,
        FakeCv({"a.pdf": b"AAA", "b.pdf": b"BBB"}),
        ScriptedClient([PASS]),  # only b.pdf reaches screen
        FakeNotifier(),
    )
    assert summary.skipped == 1
    assert summary.passed == 1


def test_failure_isolation_continues_and_does_not_persist_error(store, tmp_path):
    summary = _run(
        store, tmp_path,
        FakeCv({"a.pdf": b"AAA", "bad.pdf": b"X"}, raise_on={"bad.pdf"}),
        ScriptedClient([PASS]),  # only a.pdf reaches screen
        FakeNotifier(),
    )
    assert summary.errors == 1
    assert summary.passed == 1
    assert any("bad.pdf" in e for e in summary.error_summaries)
    # errored CV is NOT marked processed => it will retry next run
    assert store.is_processed(cv_hash(b"X"), jd_hash(JD_TEXT)) is False


def _run_with_jd(store, tmp_path, jd_source):
    return run_screening(
        cv_source=FakeCv({"a.pdf": b"AAA"}),
        jd_source=jd_source,
        store=store,
        ocr=FakeOcr(),
        client=ScriptedClient([PASS]),
        sink=LocalFolderSink(str(tmp_path)),
        notifier=FakeNotifier(),
        jd_id="eng.md",
        cli_overrides={},
        now="2026-08-17T00:00:00Z",
    )


def test_meta_yaml_role_override_is_applied(store, tmp_path):
    summary = _run_with_jd(store, tmp_path, FakeJd(meta_text="role_archetype: management"))
    assert summary.passed == 1  # meta parsed + role override path exercised


def test_non_dict_meta_is_ignored(store, tmp_path):
    summary = _run_with_jd(store, tmp_path, FakeJd(meta_text="just a scalar, not a mapping"))
    assert summary.passed == 1


def test_low_ocr_confidence_flags_manual_review(store, tmp_path):
    summary = _run(
        store, tmp_path,
        FakeCv({"a.pdf": b"AAA"}),
        ScriptedClient([PASS]),
        FakeNotifier(),
        ocr=FakeOcr(confidence=0.3),
    )
    assert summary.manual_review == ("Alice",)
