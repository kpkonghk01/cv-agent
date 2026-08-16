"""Rendering of exported report bodies (pure — the interview brief comes from the LLM).

The Reject Report defaults to the full Screening Report content; a concise mode and a
suppress mode give the full→concise→none fade-out path (AGENT.md).
"""

from __future__ import annotations

from enum import Enum

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.screening import ScreeningReport


class RejectReportMode(str, Enum):
    FULL = "full"       # default: include per-Requirement scoring
    CONCISE = "concise"  # verdict + reasons only
    NONE = "none"       # suppress the file entirely


def render_reject_report(
    report: ScreeningReport, profile: CandidateProfile, mode: RejectReportMode
) -> str | None:
    """Markdown for a rejected candidate, or None when suppressed."""
    if mode is RejectReportMode.NONE:
        return None

    who = profile.name or "Unknown candidate"
    reasons = "\n".join(f"- {r}" for r in report.reasons) or "- (no reasons recorded)"
    body = [f"# Reject Report — {who}", "", "**Verdict:** reject", "", "## Reasons", reasons]

    if mode is RejectReportMode.FULL:
        scored = "\n".join(
            f"- `{s.requirement_id}`: {s.level.value}"
            + (f" — {s.evidence}" if s.evidence else "")
            for s in report.scores
        ) or "- (no scores recorded)"
        body += ["", "## Requirement scores", scored]

    return "\n".join(body) + "\n"
