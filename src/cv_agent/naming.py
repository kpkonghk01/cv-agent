"""Report filename routing (AGENT.md).

Filenames are verdict-prefixed and carry an interview-meta discriminator so a second
interview round never overwrites the first. Slugs are filesystem-safe but keep CJK.
"""

from __future__ import annotations

import re

from cv_agent.hashing import short

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_SEP_RUN = re.compile(r"-{2,}")
_WHITESPACE = re.compile(r"\s+")


def slugify(text: str) -> str:
    """Lowercase, filesystem-safe slug. Whitespace/unsafe chars → single '-'; CJK kept."""
    text = _UNSAFE.sub("-", text.strip().lower())
    text = _WHITESPACE.sub("-", text).replace("_", "-")
    return _SEP_RUN.sub("-", text).strip("-")


def candidate_id(soft_name: str | None, cv_hash: str) -> str:
    """Slug of the soft identity, or the short CV hash when it is missing/garbled."""
    if soft_name:
        slug = slugify(soft_name)
        if slug:
            return slug
    return short(cv_hash)


def interview_brief_filename(cand_id: str, jd_slug: str, discriminator: str) -> str:
    """`pass__{candidate}__{jd}__{round-or-metahash}__interview-brief.md`"""
    return f"pass__{cand_id}__{jd_slug}__{discriminator}__interview-brief.md"


def reject_report_filename(cand_id: str, jd_slug: str) -> str:
    """`reject__{candidate}__{jd}__reject-report.md`"""
    return f"reject__{cand_id}__{jd_slug}__reject-report.md"
