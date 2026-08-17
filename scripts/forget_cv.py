"""Clear cached results for one CV so it gets re-analysed on the next run.

Because the store dedups by (cv_hash, jd_hash) and caches the OCR'd profile by cv_hash
(see ADR 0003), a CV that was already processed is skipped on re-run. Use this to force
a fresh analysis — e.g. after changing the model, the JD, or the screening strictness.

Usage:
    uv run python scripts/forget_cv.py "<cv-file>"            # nuke everything for this CV
    uv run python scripts/forget_cv.py "<cv-file>" --jd "<jd-file>"  # only re-judge vs one JD

<cv-file> / <jd-file> may be a bare filename (looked up in the source dirs) or a full path.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from cv_agent.hashing import cv_hash, jd_hash
from cv_agent.store import SqliteStore


def _resolve(name: str, source_dir: str, kind: str) -> Path:
    path = Path(name)
    if not path.is_file():
        path = Path(source_dir) / name
    if not path.is_file():
        sys.exit(f"{kind} not found: {name}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clear cached results for a CV.")
    parser.add_argument("cv", help="CV filename (in CV source dir) or a path to the PDF")
    parser.add_argument(
        "--jd",
        help="Only clear the judgment against this JD (keeps the OCR/profile cache).",
    )
    args = parser.parse_args(argv)
    load_dotenv()

    store_path = os.environ.get("STORE_PATH", "./data/cv_agent.sqlite")
    cv_dir = os.environ.get("CV_SOURCE_DIR", "./data/cvs")
    jd_dir = os.environ.get("JD_SOURCE_DIR", "./data/jds")

    cv_h = cv_hash(_resolve(args.cv, cv_dir, "CV").read_bytes())
    store = SqliteStore(store_path)
    try:
        if args.jd:
            jd_h = jd_hash(_resolve(args.jd, jd_dir, "JD").read_text(encoding="utf-8"))
            n = store.forget_processed(cv_h, jd_h)
            print(f"Cleared {n} judgment(s) for CV {cv_h[:8]} × JD {jd_h[:8]}. Profile kept.")
        else:
            profiles = store.forget_profile(cv_h)
            judged = store.forget_processed(cv_h)
            print(
                f"Cleared profile ({profiles}) + {judged} judgment(s) for CV {cv_h[:8]}. "
                "It will be fully re-analysed on the next run."
            )
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
