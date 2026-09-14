"""Graph layer: two-phase per-candidate orchestration and its context."""

from __future__ import annotations

from cv_agent.graph.context import PipelineDeps, RunContext, uniform_clients
from cv_agent.graph.phases import ensure_profile, interview_candidate, screen_candidate
from cv_agent.graph.reports import (
    RejectReportMode,
    ShortlistEntry,
    render_reject_report,
    render_scorecard,
    render_shortlist,
)

__all__ = [
    "PipelineDeps",
    "RunContext",
    "uniform_clients",
    "screen_candidate",
    "interview_candidate",
    "ensure_profile",
    "RejectReportMode",
    "ShortlistEntry",
    "render_reject_report",
    "render_scorecard",
    "render_shortlist",
]
