"""Command-line entry point. Loads .env, builds real adapters, runs a screening.

Real IO / wiring only (excluded from the coverage gate); the logic it calls is tested.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from cv_agent.app import render_summary, run_screening
from cv_agent.config import AppConfig, NodeName
from cv_agent.notify import NullNotifier
from cv_agent.sinks import LocalFolderSink
from cv_agent.sources import LocalFolderSource
from cv_agent.store import SqliteStore


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cv-agent", description="Screen CVs against a JD.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list-jds", help="List selectable JDs from the JD source.")

    run = sub.add_parser("run", help="Screen every CV against one JD.")
    run.add_argument("--jd", help="JD filename (else DEFAULT_JD, else interactive).")
    run.add_argument("--role", help="Override role archetype (technical|management|hybrid).")
    run.add_argument("--format", help="Interview format (technical|behavioral|mixed).")
    run.add_argument("--minutes", type=int, help="Interview length.")
    run.add_argument("--lang", help="Output language (default zh-Hant).")
    strict = run.add_mutually_exclusive_group()
    strict.add_argument("--strict", action="store_const", const="strict", dest="strictness")
    strict.add_argument("--loose", action="store_const", const="loose", dest="strictness")
    reject = run.add_mutually_exclusive_group()
    reject.add_argument("--no-reject-report", action="store_const", const="none", dest="reject_mode")
    reject.add_argument(
        "--concise-reject-report", action="store_const", const="concise", dest="reject_mode"
    )
    run.add_argument("--ocr-fallback", action="store_true", help="Reserved (vision-LLM re-OCR).")
    run.add_argument("--round", type=int, help="Interview round label (avoids overwrite).")
    run.add_argument("--prev-scorecard", help="Path to a previous round's scorecard.")
    run.add_argument("--max-concurrency", type=int, help="Reserved; v1 runs sequentially.")
    return p


def _overrides(args: argparse.Namespace) -> dict:
    prev = None
    if args.prev_scorecard:
        with open(args.prev_scorecard, encoding="utf-8") as fh:
            prev = fh.read()
    raw = {
        "role": args.role,
        "format": args.format,
        "minutes": args.minutes,
        "lang": args.lang,
        "strictness": args.strictness,
        "reject_mode": args.reject_mode or "full",
        "round": args.round,
        "prev_scorecard": prev,
    }
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
    picked = input("Select a JD number: ").strip()
    return choices[int(picked) - 1].id


def _build_clients(config: AppConfig) -> dict:
    from cv_agent.llm import OpenAICompatibleClient

    return {node: OpenAICompatibleClient(config.llm[node]) for node in NodeName}


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
    try:
        summary = run_screening(
            cv_source=LocalFolderSource(config.cv_source_dir, "*.pdf"),
            jd_source=jd_source,
            store=store,
            ocr=MarkerOcrEngine(force_ocr=True),
            clients=_build_clients(config),
            sink=LocalFolderSink(config.report_sink_dir),
            notifier=NullNotifier(),
            jd_id=jd_id,
            cli_overrides=_overrides(args),
            now=datetime.now(timezone.utc).isoformat(),
            ocr_confidence_threshold=config.ocr_confidence_threshold,
        )
    finally:
        store.close()

    print(render_summary(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
