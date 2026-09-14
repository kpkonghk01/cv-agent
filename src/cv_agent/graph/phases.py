"""Per-candidate work for the two-phase workflow, as direct node orchestration.

Phase 1 (screen) and Phase 2 (interview) are each linear, so they call the LLM nodes
directly rather than through a branching graph. Batch fan-out + failure isolation live
in app.py. Everything is dependency-injected (PipelineDeps + RunContext) so it is
unit-testable with fakes.
"""

from __future__ import annotations

from cv_agent.config import NodeName
from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.screening import ScreeningReport
from cv_agent.graph.context import PipelineDeps, RunContext
from cv_agent.graph.reports import render_scorecard
from cv_agent.hashing import cv_hash, short
from cv_agent.naming import candidate_id, interview_brief_filename
from cv_agent.nodes import interview_brief, screen, structure_cv
from cv_agent.ocr import extract_text_layer


def ensure_profile(
    deps: PipelineDeps, ctx: RunContext, digest: str, cv_id: str, cv_bytes: bytes
) -> CandidateProfile:
    """Cached Candidate Profile, or OCR (+ text-layer scavenge) → structure → cache."""
    cached = deps.store.get_profile(digest)
    if cached is not None:
        return cached
    result = deps.ocr.to_markdown(cv_bytes)
    try:
        text_layer = extract_text_layer(cv_bytes)
    except Exception:
        text_layer = ""  # best-effort scavenge; a bad/non-PDF text layer must not block
    profile = structure_cv(
        deps.clients[NodeName.STRUCTURE_CV],
        result.markdown,
        filename=cv_id,
        text_layer=text_layer,
        ocr_confidence=result.confidence,
    )
    deps.store.put_profile(digest, profile)
    return profile


def screen_candidate(
    deps: PipelineDeps, ctx: RunContext, cv_id: str, cv_bytes: bytes
) -> tuple[str, CandidateProfile, ScreeningReport]:
    """Phase 1: (cached screening) or OCR→structure→score, persisting both."""
    digest = cv_hash(cv_bytes)
    report = deps.store.get_screening(digest, ctx.jd_hash)
    profile = deps.store.get_profile(digest)
    if report is not None and profile is not None:
        return digest, profile, report  # fully cached — no LLM/OCR

    profile = ensure_profile(deps, ctx, digest, cv_id, cv_bytes)
    report = screen(
        deps.clients[NodeName.SCREEN],
        profile,
        ctx.rubric,
        strictness=ctx.strictness,
        must_weight=ctx.must_weight,
        nice_weight=ctx.nice_weight,
    )
    deps.store.put_screening(digest, ctx.jd_hash, report)
    return digest, profile, report


def interview_candidate(
    deps: PipelineDeps,
    ctx: RunContext,
    digest: str,
    profile: CandidateProfile,
    report: ScreeningReport,
) -> str:
    """Phase 2: draft the interview brief (deterministic scorecard + LLM brief) and write it."""
    brief = interview_brief(
        deps.clients[NodeName.INTERVIEW],
        profile,
        ctx.rubric,
        report,
        minutes=ctx.minutes,
        interview_format=ctx.interview_format,
        output_language=ctx.output_language,
        prev_scorecard=ctx.prev_scorecard,
    )
    scorecard = "## 篩選評分卡（Screening scorecard）\n\n" + render_scorecard(report, ctx.rubric)
    document = f"{scorecard}\n\n---\n\n{brief}"
    filename = interview_brief_filename(
        candidate_id(profile.name, digest), ctx.jd_slug, short(ctx.interview_meta_hash)
    )
    return deps.sink.write(filename, document)
