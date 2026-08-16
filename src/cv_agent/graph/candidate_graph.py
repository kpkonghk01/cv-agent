"""Per-candidate LangGraph subgraph (ADR 0004: LangGraph as a workflow engine).

Flow: check dedup → (skip) | ocr → (cached profile) screen | structure → screen
      → (pass) interview brief | (reject) reject report → finalize (mark processed).

Dependencies are injected via ``PipelineDeps`` + ``RunContext`` closures, so the whole
path is unit-testable with fakes. Failure isolation is handled by the caller (app.py),
which wraps ``invoke`` per candidate — a bad CV never blocks the batch.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.enums import CandidateStatus, Verdict
from cv_agent.domain.screening import ScreeningReport
from cv_agent.graph.context import PipelineDeps, RunContext
from cv_agent.graph.reports import render_reject_report
from cv_agent.hashing import cv_hash, short
from cv_agent.naming import candidate_id, interview_brief_filename, reject_report_filename
from cv_agent.nodes import interview_brief, screen, structure_cv
from cv_agent.store.records import ProcessedRecord


class CandidateState(TypedDict, total=False):
    cv_id: str
    cv_bytes: bytes
    cv_hash: str
    markdown: str
    ocr_confidence: float | None
    profile: CandidateProfile
    report: ScreeningReport
    skipped: bool
    verdict: str
    report_path: str | None
    soft_name: str | None
    reasons: tuple[str, ...]


def build_candidate_graph(deps: PipelineDeps, ctx: RunContext) -> Any:
    """Compile the per-candidate graph bound to these dependencies and run context."""

    def check(state: CandidateState) -> dict:
        digest = cv_hash(state["cv_bytes"])
        return {"cv_hash": digest, "skipped": deps.store.is_processed(digest, ctx.jd_hash)}

    def route_check(state: CandidateState) -> str:
        return "skip" if state["skipped"] else "run"

    def ocr(state: CandidateState) -> dict:
        cached = deps.store.get_profile(state["cv_hash"])
        if cached is not None:
            return {"profile": cached}
        result = deps.ocr.to_markdown(state["cv_bytes"])
        return {"markdown": result.markdown, "ocr_confidence": result.confidence}

    def route_after_ocr(state: CandidateState) -> str:
        return "have_profile" if state.get("profile") is not None else "structure"

    def structure(state: CandidateState) -> dict:
        profile = structure_cv(
            deps.client, state["markdown"], ocr_confidence=state.get("ocr_confidence")
        )
        deps.store.put_profile(state["cv_hash"], profile)
        return {"profile": profile}

    def screen_node(state: CandidateState) -> dict:
        report = screen(deps.client, state["profile"], ctx.rubric, strictness=ctx.strictness)
        return {"report": report}

    def route_verdict(state: CandidateState) -> str:
        return "interview" if state["report"].is_pass else "reject"

    def interview(state: CandidateState) -> dict:
        profile, report = state["profile"], state["report"]
        brief = interview_brief(
            deps.client,
            profile,
            ctx.rubric,
            report,
            minutes=ctx.minutes,
            interview_format=ctx.interview_format,
            output_language=ctx.output_language,
            prev_scorecard=ctx.prev_scorecard,
        )
        cid = candidate_id(profile.name, state["cv_hash"])
        filename = interview_brief_filename(cid, ctx.jd_slug, short(ctx.interview_meta_hash))
        path = deps.sink.write(filename, brief)
        return _outcome(Verdict.PASS, path, profile.name, report.reasons)

    def reject(state: CandidateState) -> dict:
        profile, report = state["profile"], state["report"]
        content = render_reject_report(report, profile, ctx.reject_mode)
        path = None
        if content is not None:
            cid = candidate_id(profile.name, state["cv_hash"])
            path = deps.sink.write(reject_report_filename(cid, ctx.jd_slug), content)
        return _outcome(Verdict.REJECT, path, profile.name, report.reasons)

    def finalize(state: CandidateState) -> dict:
        deps.store.mark_processed(
            ProcessedRecord(
                cv_hash=state["cv_hash"],
                jd_hash=ctx.jd_hash,
                verdict=Verdict(state["verdict"]),
                status=CandidateStatus.OK,
                reasons=state.get("reasons", ()),
                soft_name=state.get("soft_name"),
                report_path=state.get("report_path"),
                created_at=ctx.created_at,
            )
        )
        return {}

    graph = StateGraph(CandidateState)
    for name, fn in [
        ("check", check),
        ("ocr", ocr),
        ("structure", structure),
        ("screen", screen_node),
        ("interview", interview),
        ("reject", reject),
        ("finalize", finalize),
    ]:
        graph.add_node(name, fn)

    graph.add_edge(START, "check")
    graph.add_conditional_edges("check", route_check, {"skip": END, "run": "ocr"})
    graph.add_conditional_edges(
        "ocr", route_after_ocr, {"have_profile": "screen", "structure": "structure"}
    )
    graph.add_edge("structure", "screen")
    graph.add_conditional_edges(
        "screen", route_verdict, {"interview": "interview", "reject": "reject"}
    )
    graph.add_edge("interview", "finalize")
    graph.add_edge("reject", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def _outcome(verdict: Verdict, path: str | None, soft_name: str | None, reasons) -> dict:
    return {
        "verdict": verdict.value,
        "report_path": path,
        "soft_name": soft_name,
        "reasons": tuple(reasons),
    }
