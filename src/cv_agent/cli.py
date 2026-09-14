"""Command-line entry point (two-phase). Loads .env, builds real adapters, runs a phase.

Real IO / wiring only (excluded from the coverage gate); the logic it calls is tested.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from cv_agent.app import (
    render_interview_summary,
    render_screen_summary,
    run_interview,
    run_screen,
)
from cv_agent.config import AppConfig, NodeName
from cv_agent.notify import NullNotifier
from cv_agent.sinks import LocalFolderSink
from cv_agent.sources import LocalFolderSource
from cv_agent.store import SqliteStore


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cv-agent", description="Screen CVs and draft interviews.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list-jds", help="List selectable JDs from the JD source.")

    def _add_common(sp):
        sp.add_argument("--jd", help="JD filename (else DEFAULT_JD, else interactive).")
        sp.add_argument("--role", help="Override role archetype.")
        sp.add_argument("--format", help="Interview format.")
        sp.add_argument("--minutes", type=int, help="Interview length.")
        sp.add_argument("--lang", help="Output language.")
        strict = sp.add_mutually_exclusive_group()
        strict.add_argument("--strict", action="store_const", const="strict", dest="strictness")
        strict.add_argument("--loose", action="store_const", const="loose", dest="strictness")

    screen = sub.add_parser("screen", help="Phase 1: score CVs since a date → ranked shortlist.")
    _add_common(screen)
    screen.add_argument("--since", help="Only CVs in date-folders >= this (e.g. 20260818).")
    screen.add_argument("--top", type=int, help="Keep only the top N in the shortlist.")
    screen.add_argument("--limit", type=int, help="Cap how many CVs to OCR+score (cost/test).")
    screen.add_argument("--concurrency", type=int, help="Parallel CVs (default MAX_CONCURRENCY).")

    interview = sub.add_parser("interview", help="Phase 2: draft briefs for accepted candidates.")
    _add_common(interview)
    interview.add_argument("candidates", nargs="*", help="CV filenames or candidate names.")
    interview.add_argument("--from-file", help="File with one filename/name per line.")
    interview.add_argument("--round", type=int, help="Interview round label (avoids overwrite).")
    interview.add_argument("--prev-scorecard", help="Path to a previous round's scorecard.")
    return p


def _overrides(args: argparse.Namespace) -> dict:
    raw = {
        "role": getattr(args, "role", None),
        "format": getattr(args, "format", None),
        "minutes": getattr(args, "minutes", None),
        "lang": getattr(args, "lang", None),
        "strictness": getattr(args, "strictness", None),
        "round": getattr(args, "round", None),
    }
    if getattr(args, "prev_scorecard", None):
        with open(args.prev_scorecard, encoding="utf-8") as fh:
            raw["prev_scorecard"] = fh.read()
    return {k: v for k, v in raw.items() if v is not None}


def _resolve_jd(cli_jd: str | None, default_jd: str | None, jd_source) -> str:
    if cli_jd:
        return cli_jd
    if default_jd:
        return default_jd
    choices = jd_source.list()
    if not choices:
        raise SystemExit("No JD found. Add one to the JD source or pass --jd.")
    if len(choices) == 1:
        return choices[0].id
    for i, ref in enumerate(choices, 1):
        print(f"  {i}. {ref.id}")
    return choices[int(input("Select a JD number: ").strip()) - 1].id


def _selectors(args: argparse.Namespace) -> list[str]:
    items = list(args.candidates)
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as fh:
            items += [ln.strip() for ln in fh if ln.strip()]
    return items


def _build_clients(config: AppConfig) -> dict:
    from cv_agent.llm import OpenAICompatibleClient

    raw_max = os.environ.get("LLM_MAX_TOKENS")
    max_tokens = int(raw_max) if raw_max else None
    disable_thinking = os.environ.get("LLM_DISABLE_THINKING", "").lower() in ("1", "true", "yes")
    json_nodes = {NodeName.STRUCTURE_CV, NodeName.JD_RUBRIC, NodeName.SCREEN}
    return {
        node: OpenAICompatibleClient(
            config.llm[node],
            max_tokens=max_tokens,
            disable_thinking=disable_thinking,
            json_mode=node in json_nodes,
        )
        for node in NodeName
    }


def _cv_source(config: AppConfig):
    if os.environ.get("CV_SOURCE", "local").lower() == "gdrive":
        from cv_agent.sources import GoogleDriveSource

        return GoogleDriveSource.from_env(os.environ)
    return LocalFolderSource(config.cv_source_dir, "*.pdf")


def _confirm(selector: str) -> bool:
    return input(f"{selector} has not been screened. OCR + score it now? [y/N] ").strip().lower() in (
        "y",
        "yes",
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    load_dotenv()
    config = AppConfig.from_env(os.environ)
    jd_source = LocalFolderSource(config.jd_source_dir, "*.md")

    if args.command == "list-jds":
        for ref in jd_source.list():
            print(ref.id)
        return 0

    jd_id = _resolve_jd(args.jd, config.default_jd, jd_source)
    from cv_agent.ocr import MarkerOcrEngine

    store = SqliteStore(config.store_path)
    common = dict(
        cv_source=_cv_source(config),
        jd_source=jd_source,
        store=store,
        ocr=MarkerOcrEngine(force_ocr=True),
        clients=_build_clients(config),
        sink=LocalFolderSink(config.report_sink_dir),
        notifier=NullNotifier(),
        jd_id=jd_id,
        cli_overrides=_overrides(args),
        now=datetime.now(timezone.utc).isoformat(),
        progress=lambda msg: print(msg, file=sys.stderr, flush=True),
    )
    try:
        if args.command == "screen":
            summary = run_screen(
                **common, since=args.since, top_n=args.top, limit=args.limit,
                concurrency=args.concurrency or config.max_concurrency,
            )
            print(render_screen_summary(summary))
        else:  # interview
            summary = run_interview(**common, selectors=_selectors(args), confirm=_confirm)
            print(render_interview_summary(summary))
    finally:
        store.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
