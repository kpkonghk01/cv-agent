"""Injected dependencies and per-run context for the candidate graph."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cv_agent.config import NodeName
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
    """The infrastructure adapters the graph drives (all swappable ports).

    ``clients`` is one LLM client per node, so BYOK per-node model overrides
    (ADR 0002) are honoured end-to-end.
    """

    store: Store
    sink: ReportSink
    ocr: OcrEngine
    clients: Mapping[NodeName, LLMClient]


def uniform_clients(client: LLMClient) -> dict[NodeName, LLMClient]:
    """Use one client for every node (default when no per-node override is set)."""
    return {node: client for node in NodeName}
