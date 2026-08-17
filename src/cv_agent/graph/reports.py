"""Rendering of exported report bodies (pure — the interview brief comes from the LLM).

The Reject Report defaults to the full Screening Report content; a concise mode and a
suppress mode give the full→concise→none fade-out path (AGENT.md).
"""

from __future__ import annotations

from enum import Enum

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.rubric import Rubric
from cv_agent.domain.screening import ScreeningReport


class RejectReportMode(str, Enum):
    FULL = "full"       # default: include per-Requirement scoring
    CONCISE = "concise"  # verdict + reasons only
    NONE = "none"       # suppress the file entirely


def render_scorecard(report: ScreeningReport, rubric: Rubric | None) -> str:
    """A bullet list of every Requirement: text, must/nice, level, and evidence.

    Deterministic (not LLM-generated). Shared by the Reject Report and the Interview
    Brief so both read on their own, not as opaque r-ids. Falls back to the id when no
    rubric is supplied.
    """
    by_id = {r.id: r for r in (rubric.requirements if rubric else ())}
    lines = []
    for s in report.scores:
        req = by_id.get(s.requirement_id)
        if req is not None:
            kind = "must-have" if req.is_must_have else "nice-to-have"
            label = f"{req.text} `[{kind}]`"
        else:
            label = f"`{s.requirement_id}`"
        line = f"- {label}: **{s.level.value}**"
        if s.evidence:
            line += f" — {s.evidence}"
        lines.append(line)
    return "\n".join(lines) or "- (no scores recorded)"


def render_reject_report(
    report: ScreeningReport,
    profile: CandidateProfile,
    mode: RejectReportMode,
    *,
    rubric: Rubric | None = None,
) -> str | None:
    """Markdown for a rejected candidate, or None when suppressed."""
    if mode is RejectReportMode.NONE:
        return None

    who = profile.name or "Unknown candidate"
    reasons = "\n".join(f"- {r}" for r in report.reasons) or "- (no reasons recorded)"
    body = [f"# Reject Report — {who}", "", "**Verdict:** reject", "", "## Reasons", reasons]

    if mode is RejectReportMode.FULL:
        body += ["", "## Requirement scores", render_scorecard(report, rubric)]

    return "\n".join(body) + "\n"
