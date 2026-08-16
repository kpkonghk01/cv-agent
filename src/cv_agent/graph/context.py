"""Injected dependencies and per-run context for the candidate graph."""

from __future__ import annotations

from dataclasses import dataclass

from cv_agent.domain.enums import Strictness
from cv_agent.domain.rubric import Rubric
from cv_agent.graph.reports import RejectReportMode
from cv_agent.llm.structured import LLMClient
from cv_agent.ocr.ports import OcrEngine
from cv_agent.sinks.ports import ReportSink
from cv_agent.store.ports import Store


@dataclass(frozen=True)
class RunContext:
    """Everything constant across the CVs of one run (one JD, one interview config)."""

    rubric: Rubric
    jd_hash: str
    jd_slug: str
    minutes: int
    interview_format: str
    output_language: str
    strictness: Strictness
    reject_mode: RejectReportMode
    interview_meta_hash: str
    created_at: str
    prev_scorecard: str | None = None


@dataclass(frozen=True)
class PipelineDeps:
    """The infrastructure adapters the graph drives (all swappable ports)."""

    store: Store
    sink: ReportSink
    ocr: OcrEngine
    client: LLMClient
