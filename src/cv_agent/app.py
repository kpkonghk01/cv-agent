"""Two-phase run orchestration.

Phase 1 ``run_screen``: OCR → structure → score every CV (since a date), rank, write ONE
shortlist. Phase 2 ``run_interview``: for accepted candidates (by filename or name), reload
the cached profile + screening and draft the interview brief — no re-OCR.

Pure and testable: every adapter is injected. Real construction from AppConfig is in cli.py.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor

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
from cv_agent.store import FailureRecord


class ScreenSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int = 0                       # scored this run (cached + fresh)
    shortlisted: int = 0
    skipped: int = 0                     # previously-failed, skipped by default
    failed: int = 0                      # failed this run (remembered in the failure cache)
    errors: int = 0                      # transient errors (e.g. download) — not remembered
    error_summaries: tuple[str, ...] = ()
    shortlist_path: str | None = None
    failures_path: str | None = None     # machine-readable manifest (only with --handoff)


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
    concurrency: int = 1,
    retry_failed: bool = False,
    handoff: bool = False,
    progress: Callable[[str], None] = lambda _: None,
) -> ScreenSummary:
    progress("preparing rubric…")
    ctx, settings = _context(jd_source, store, clients, jd_id, cli_overrides, now)
    deps = PipelineDeps(store=store, sink=sink, ocr=ocr, clients=clients)

    entries: list[ShortlistEntry] = []
    errors: list[str] = []            # transient (e.g. download) — not remembered
    failed: list[dict] = []           # processing failures remembered this run
    skipped: list[str] = []           # previously-failed, skipped by default
    refs = cv_source.list(since)
    if limit is not None:
        refs = refs[:limit]  # cost/test cap on how many CVs to OCR + score
    total = len(refs)
    progress(f"screening {total} CV(s)… (concurrency={concurrency})")
    plock = threading.Lock()
    counter = {"n": 0}

    def _work(ref):
        try:
            outcome: tuple = _process_ref(deps, ctx, ref, cv_source, retry_failed, handoff)
        except Exception as err:  # transient (download etc.) — retried next run, not cached
            outcome = ("error", ref, str(err))
        with plock:  # atomic, ordered progress even from worker threads
            counter["n"] += 1
            n = counter["n"]
            kind = outcome[0]
            if kind == "scored":
                report = outcome[3]
                tag = "cached " if outcome[4] else ""
                progress(f"[{n}/{total}] {ref.name} → {tag}{report.rank_score:g} "
                         f"({report.verdict.value})")
            elif kind == "skipped":
                progress(f"[{n}/{total}] {ref.name} ⏭ skipped (cached failure: {outcome[2].step})")
            else:  # failed | error
                progress(f"[{n}/{total}] {ref.name} ✗ {outcome[2 if kind == 'error' else 4]}")
        return outcome

    if concurrency <= 1:
        outcomes = [_work(ref) for ref in refs]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            outcomes = list(pool.map(_work, refs))

    for outcome in outcomes:
        kind = outcome[0]
        if kind == "scored":
            _, ref, profile, report, _cached = outcome
            entries.append(
                ShortlistEntry(name=profile.name or ref.name, cv_id=ref.name, report=report)
            )
        elif kind == "skipped":
            _, ref, failure = outcome
            skipped.append(f"{ref.name}: previously failed at {failure.step} ({failure.reason})")
        elif kind == "failed":
            _, ref, digest, step, reason = outcome
            errors.append(f"{ref.name}: {reason}")
            failed.append({"cv_id": ref.name, "source_id": ref.id, "cv_hash": digest,
                           "step": step, "reason": reason})
        else:  # transient error
            _, ref, reason = outcome
            errors.append(f"{ref.name}: {reason} (transient)")

    entries.sort(key=lambda e: e.report.rank_score, reverse=True)
    top = tuple(entries[:top_n]) if top_n else tuple(entries)
    label = since or "all"
    content = render_shortlist(
        top, ctx.rubric, jd_title=settings.title, since=label, total_screened=len(entries)
    )
    path = sink.write(shortlist_filename(ctx.jd_slug, label), content)
    progress(f"shortlist → {path}")

    failures_path = None
    if handoff and failed:  # hand the failed steps off to the driving agent
        failures_path = sink.write(
            f"failures__{ctx.jd_slug}__{label}.json", _failures_manifest(ctx, failed)
        )
        progress(f"failures manifest → {failures_path}")

    summary = ScreenSummary(
        total=len(entries),
        shortlisted=len(top),
        skipped=len(skipped),
        failed=len(failed),
        errors=len(errors),
        error_summaries=tuple(errors) + tuple(skipped),
        shortlist_path=path,
        failures_path=failures_path,
    )
    notifier.notify(render_screen_summary(summary))
    return summary


def _process_ref(deps, ctx, ref, cv_source, retry_failed: bool, handoff: bool):
    """Screen one source ref, honouring the failure cache. Returns one of:
    ``("scored", ref, profile, report, from_cache)`` — usable score;
    ``("skipped", ref, failure_record)`` — a remembered failure, skipped (default);
    ``("failed", ref, cv_hash, step, reason)`` — failed this run (now remembered).

    A known, fully-cached CV loads without downloading. A processing failure (OCR/LLM) is
    remembered so the next run skips it — unless ``retry_failed`` or ``handoff`` is set. Only
    the OCR/structure/screen step is caught here; infra errors (download) propagate to the
    caller as transient, so they are retried rather than cached."""
    digest = deps.store.get_cv_hash(ref.id)
    downloaded = None
    if digest is None:
        downloaded = cv_source.read_bytes(ref.id)  # may raise (transient) → caller
        digest = cv_hash(downloaded)
        deps.store.put_cv_hash(ref.id, digest)

    report = deps.store.get_screening(digest, ctx.jd_hash)
    profile = deps.store.get_profile(digest)
    if report is not None and profile is not None:
        return "scored", ref, profile, report, True

    if not (retry_failed or handoff):
        failure = deps.store.get_failure(digest, ctx.jd_hash)
        if failure is not None:
            return "skipped", ref, failure

    if downloaded is None:
        downloaded = cv_source.read_bytes(ref.id)  # may raise (transient) → caller
    try:
        _, profile, report = screen_candidate(deps, ctx, ref.name, downloaded)
    except Exception as err:  # processing failure → remember it, so re-runs skip by default
        deps.store.put_failure(
            digest, ctx.jd_hash,
            FailureRecord(step="process", reason=str(err), created_at=ctx.created_at),
        )
        return "failed", ref, digest, "process", str(err)
    deps.store.forget_failure(digest, ctx.jd_hash)  # success clears any stale failure
    return "scored", ref, profile, report, False


def _failures_manifest(ctx, failed: list[dict]) -> str:
    """A machine-readable handoff for the driving agent: which CVs failed, where, and the
    ids it needs to fetch each one and ingest a profile (see ``ingest-profile``)."""
    payload = {
        "jd_hash": ctx.jd_hash,
        "jd_slug": ctx.jd_slug,
        "created_at": ctx.created_at,
        "failures": failed,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


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
    progress: Callable[[str], None] = lambda _: None,
) -> InterviewSummary:
    ctx, _ = _context(jd_source, store, clients, jd_id, cli_overrides, now)
    deps = PipelineDeps(store=store, sink=sink, ocr=ocr, clients=clients)
    by_filename = {ref.name: ref for ref in cv_source.list(None)}

    briefs: list[str] = []
    skipped: list[str] = []
    for i, sel in enumerate(selectors, 1):
        progress(f"[{i}/{len(selectors)}] {sel}")
        resolved = _resolve(deps, ctx, sel, cv_source, by_filename, confirm, skipped)
        if resolved is None:
            continue
        digest, profile, report = resolved
        path = interview_candidate(deps, ctx, digest, profile, report)
        progress(f"    → {path}")
        briefs.append(path)

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
        f"screened={s.total} shortlisted={s.shortlisted} "
        f"skipped={s.skipped} failed={s.failed} errors={s.errors}",
        f"shortlist: {s.shortlist_path}",
    ]
    if s.failures_path:
        lines.append(f"failures manifest: {s.failures_path}")
    if s.error_summaries:
        lines += ["", "Not scored (failed = remembered; transient = retried; "
                  "skipped = --retry to re-run):",
                  *(f"  - {e}" for e in s.error_summaries)]
    return "\n".join(lines)


def render_interview_summary(s: InterviewSummary) -> str:
    lines = ["=== interview summary ===", f"briefs={s.generated} skipped={len(s.skipped)}"]
    if s.briefs:
        lines += ["", "Written:", *(f"  - {p}" for p in s.briefs)]
    if s.skipped:
        lines += ["", "Skipped:", *(f"  - {x}" for x in s.skipped)]
    return "\n".join(lines)
