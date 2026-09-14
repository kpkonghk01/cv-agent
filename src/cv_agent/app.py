"""Two-phase run orchestration.

Phase 1 ``run_screen``: OCR → structure → score every CV (since a date), rank, write ONE
shortlist. Phase 2 ``run_interview``: for accepted candidates (by filename or name), reload
the cached profile + screening and draft the interview brief — no re-OCR.

Pure and testable: every adapter is injected. Real construction from AppConfig is in cli.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict

from cv_agent.config import NodeName
from cv_agent.graph import (
    PipelineDeps,
    RunContext,
    ShortlistEntry,
    interview_candidate,
    render_shortlist,
    screen_candidate,
)
from cv_agent.hashing import cv_hash, jd_hash
from cv_agent.naming import shortlist_filename, slugify
from cv_agent.nodes import jd_to_rubric
from cv_agent.settings import ResolvedSettings, resolve_settings


class ScreenSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int = 0
    shortlisted: int = 0
    errors: int = 0
    error_summaries: tuple[str, ...] = ()
    shortlist_path: str | None = None


class InterviewSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated: int = 0
    briefs: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


def _stem(jd_id: str) -> str:
    return jd_id[:-3] if jd_id.endswith(".md") else jd_id


def load_jd_meta(jd_source, jd_id: str) -> dict:
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


def _context(
    jd_source, store, clients, jd_id: str, cli_overrides: Mapping[str, object], now: str
) -> tuple[RunContext, ResolvedSettings]:
    jd_text = jd_source.read_text(jd_id)
    settings = resolve_settings(
        load_jd_meta(jd_source, jd_id), cli_overrides, default_title=_stem(jd_id)
    )
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
        interview_meta_hash=settings.interview_meta_hash,
        created_at=now,
        reject_mode=settings.reject_mode,
        must_weight=settings.must_weight,
        nice_weight=settings.nice_weight,
        prev_scorecard=cli_overrides.get("prev_scorecard"),
    )
    return ctx, settings


# --- Phase 1: screen -> shortlist ----------------------------------------


def run_screen(
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
    since: str | None = None,
    top_n: int | None = None,
    limit: int | None = None,
) -> ScreenSummary:
    ctx, settings = _context(jd_source, store, clients, jd_id, cli_overrides, now)
    deps = PipelineDeps(store=store, sink=sink, ocr=ocr, clients=clients)

    entries: list[ShortlistEntry] = []
    errors: list[str] = []
    refs = cv_source.list(since)
    if limit is not None:
        refs = refs[:limit]  # cost/test cap on how many CVs to OCR + score
    for ref in refs:
        # ref.name is the human filename (candidate hint + display); ref.id reads bytes
        # (== filename locally, an opaque file id on Drive).
        try:
            digest, profile, report = screen_candidate(
                deps, ctx, ref.name, cv_source.read_bytes(ref.id)
            )
        except Exception as err:  # per-candidate isolation
            errors.append(f"{ref.name}: {err}")
            continue
        entries.append(
            ShortlistEntry(name=profile.name or ref.name, cv_id=ref.name, report=report)
        )

    entries.sort(key=lambda e: e.report.rank_score, reverse=True)
    top = tuple(entries[:top_n]) if top_n else tuple(entries)
    label = since or "all"
    content = render_shortlist(
        top, ctx.rubric, jd_title=settings.title, since=label, total_screened=len(entries)
    )
    path = sink.write(shortlist_filename(ctx.jd_slug, label), content)

    summary = ScreenSummary(
        total=len(entries),
        shortlisted=len(top),
        errors=len(errors),
        error_summaries=tuple(errors),
        shortlist_path=path,
    )
    notifier.notify(render_screen_summary(summary))
    return summary


# --- Phase 2: interview accepted candidates ------------------------------


def run_interview(
    *,
    cv_source,
    jd_source,
    store,
    ocr,
    clients,
    sink,
    notifier,
    jd_id: str,
    selectors: Sequence[str],
    cli_overrides: Mapping[str, object],
    now: str,
    confirm: Callable[[str], bool],
) -> InterviewSummary:
    ctx, _ = _context(jd_source, store, clients, jd_id, cli_overrides, now)
    deps = PipelineDeps(store=store, sink=sink, ocr=ocr, clients=clients)
    by_filename = {ref.name: ref for ref in cv_source.list(None)}

    briefs: list[str] = []
    skipped: list[str] = []
    for sel in selectors:
        resolved = _resolve(deps, ctx, sel, cv_source, by_filename, confirm, skipped)
        if resolved is None:
            continue
        digest, profile, report = resolved
        briefs.append(interview_candidate(deps, ctx, digest, profile, report))

    summary = InterviewSummary(generated=len(briefs), briefs=tuple(briefs), skipped=tuple(skipped))
    notifier.notify(render_interview_summary(summary))
    return summary


def _resolve(deps, ctx, sel, cv_source, by_filename, confirm, skipped):
    """Resolve a selector (filename or name) to (cv_hash, profile, report), or None."""
    if sel in by_filename:  # filename → deterministic
        ref = by_filename[sel]
        digest = cv_hash(cv_source.read_bytes(ref.id))
        profile = deps.store.get_profile(digest)
        report = deps.store.get_screening(digest, ctx.jd_hash)
        if profile is not None and report is not None:
            return digest, profile, report
        if confirm(sel):  # not screened yet → OCR + score on demand
            return screen_candidate(deps, ctx, ref.name, cv_source.read_bytes(ref.id))
        skipped.append(f"{sel}: not screened, declined")
        return None

    # name → match stored profile names for this JD's screening
    screened = [h for h in deps.store.find_cv_by_name(sel)
                if deps.store.get_screening(h, ctx.jd_hash) is not None]
    if len(screened) == 1:
        h = screened[0]
        return h, deps.store.get_profile(h), deps.store.get_screening(h, ctx.jd_hash)
    reason = "no screened candidate by that name (use the CV filename)" if not screened \
        else f"{len(screened)} candidates match that name (use the CV filename)"
    skipped.append(f"{sel}: {reason}")
    return None


# --- Summary rendering ----------------------------------------------------


def render_screen_summary(s: ScreenSummary) -> str:
    lines = [
        "=== screen summary ===",
        f"screened={s.total} shortlisted={s.shortlisted} errors={s.errors}",
        f"shortlist: {s.shortlist_path}",
    ]
    if s.error_summaries:
        lines += ["", "Errors (not scored; will retry next run):",
                  *(f"  - {e}" for e in s.error_summaries)]
    return "\n".join(lines)


def render_interview_summary(s: InterviewSummary) -> str:
    lines = ["=== interview summary ===", f"briefs={s.generated} skipped={len(s.skipped)}"]
    if s.briefs:
        lines += ["", "Written:", *(f"  - {p}" for p in s.briefs)]
    if s.skipped:
        lines += ["", "Skipped:", *(f"  - {x}" for x in s.skipped)]
    return "\n".join(lines)
