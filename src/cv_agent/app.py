"""Run orchestration: one JD × many CVs, sequential (v1), with per-candidate failure
isolation and an end-of-run summary + notification.

Pure and testable: every adapter is injected. Real construction from AppConfig lives in
cli.py (real IO, excluded from the coverage gate).
"""

from __future__ import annotations

from collections.abc import Mapping

import yaml
from pydantic import BaseModel, ConfigDict

from cv_agent.config import NodeName
from cv_agent.graph.candidate_graph import build_candidate_graph
from cv_agent.graph.context import PipelineDeps, RunContext
from cv_agent.hashing import jd_hash
from cv_agent.naming import slugify
from cv_agent.nodes import jd_to_rubric
from cv_agent.settings import ResolvedSettings, resolve_settings


class RunSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int = 0
    passed: int = 0
    rejected: int = 0
    skipped: int = 0
    errors: int = 0
    reject_summaries: tuple[str, ...] = ()
    error_summaries: tuple[str, ...] = ()
    manual_review: tuple[str, ...] = ()


def _stem(jd_id: str) -> str:
    return jd_id[:-3] if jd_id.endswith(".md") else jd_id


def load_jd_meta(jd_source, jd_id: str) -> dict:
    """Read the optional ``<stem>.meta.yaml`` sidecar; empty dict if absent."""
    try:
        raw = jd_source.read_text(f"{_stem(jd_id)}.meta.yaml")
    except FileNotFoundError:
        return {}
    parsed = yaml.safe_load(raw)
    return parsed if isinstance(parsed, dict) else {}


def _build_rubric(store, clients, jd_text: str, jd_h: str, settings: ResolvedSettings):
    rubric = store.get_rubric(jd_h)
    if rubric is None:
        rubric = jd_to_rubric(clients[NodeName.JD_RUBRIC], jd_text)
        store.put_rubric(jd_h, rubric)
    if settings.role_override is not None:
        rubric = rubric.model_copy(update={"role_archetype": settings.role_override})
    return rubric


def run_screening(
    *,
    cv_source,
    jd_source,
    store,
    ocr,
    clients,
    sink,
    notifier,
    jd_id: str,
    cli_overrides: Mapping[str, object],
    now: str,
    ocr_confidence_threshold: float = 0.6,
) -> RunSummary:
    jd_text = jd_source.read_text(jd_id)
    settings = resolve_settings(load_jd_meta(jd_source, jd_id), cli_overrides, default_title=_stem(jd_id))
    jd_h = jd_hash(jd_text)
    rubric = _build_rubric(store, clients, jd_text, jd_h, settings)

    ctx = RunContext(
        rubric=rubric,
        jd_hash=jd_h,
        jd_slug=slugify(settings.title),
        minutes=settings.minutes,
        interview_format=settings.interview_format,
        output_language=settings.output_language,
        strictness=settings.strictness,
        reject_mode=settings.reject_mode,
        interview_meta_hash=settings.interview_meta_hash,
        created_at=now,
        prev_scorecard=cli_overrides.get("prev_scorecard"),
        force_pass=bool(cli_overrides.get("force_pass")),
    )
    deps = PipelineDeps(store=store, sink=sink, ocr=ocr, clients=clients)
    graph = build_candidate_graph(deps, ctx)

    acc = _Accumulator(threshold=ocr_confidence_threshold)
    for ref in cv_source.list():
        acc.total += 1
        try:
            state = graph.invoke({"cv_id": ref.id, "cv_bytes": cv_source.read_bytes(ref.id)})
        except Exception as err:  # per-candidate isolation — never block the batch
            acc.error(ref.id, err)
            continue
        acc.record(ref.id, state)

    summary = acc.summary()
    notifier.notify(render_summary(summary))
    return summary


class _Accumulator:
    def __init__(self, *, threshold: float) -> None:
        self.threshold = threshold
        self.total = self.passed = self.rejected = self.skipped = self.errors = 0
        self.rejects: list[str] = []
        self.error_list: list[str] = []
        self.manual: list[str] = []

    def error(self, cv_id: str, err: Exception) -> None:
        self.errors += 1
        self.error_list.append(f"{cv_id}: {err}")

    def record(self, cv_id: str, state: dict) -> None:
        if state.get("skipped"):
            self.skipped += 1
            return
        who = state.get("soft_name") or cv_id
        profile = state.get("profile")
        if profile is not None and profile.ocr_confidence is not None:
            if profile.ocr_confidence < self.threshold:
                self.manual.append(who)
        if state.get("verdict") == "pass":
            self.passed += 1
        else:
            self.rejected += 1
            reasons = "; ".join(state.get("reasons", ())) or "no reason recorded"
            self.rejects.append(f"{who}: {reasons}")

    def summary(self) -> RunSummary:
        return RunSummary(
            total=self.total,
            passed=self.passed,
            rejected=self.rejected,
            skipped=self.skipped,
            errors=self.errors,
            reject_summaries=tuple(self.rejects),
            error_summaries=tuple(self.error_list),
            manual_review=tuple(self.manual),
        )


def render_summary(s: RunSummary) -> str:
    lines = [
        "=== cv-agent run summary ===",
        f"total={s.total} pass={s.passed} reject={s.rejected} skip={s.skipped} error={s.errors}",
    ]
    if s.reject_summaries:
        lines += ["", "Rejected:", *(f"  - {r}" for r in s.reject_summaries)]
    if s.manual_review:
        lines += ["", "Manual review (low OCR confidence):", *(f"  - {m}" for m in s.manual_review)]
    if s.error_summaries:
        lines += ["", "Errors (not marked processed; will retry next run):",
                  *(f"  - {e}" for e in s.error_summaries)]
    return "\n".join(lines)
