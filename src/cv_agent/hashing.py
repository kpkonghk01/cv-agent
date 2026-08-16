"""Content hashes used as dedup / cache keys (see ADR 0003).

- ``cv_hash``: identity of a CV = SHA-256 of the raw PDF bytes. A re-exported PDF
  (different bytes) is treated as a new CV — an accepted v1 limitation.
- ``jd_hash``: identity of a JD, whitespace-normalised so trivial reformatting
  does not invalidate the cached Rubric.
- ``interview_meta_hash``: identity of an interview configuration, order-independent,
  so a second round with different settings produces a distinct Interview Brief.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

_WHITESPACE = re.compile(r"\s+")


def cv_hash(data: bytes) -> str:
    """SHA-256 hex of raw CV bytes."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("cv_hash expects bytes")
    return hashlib.sha256(bytes(data)).hexdigest()


def jd_hash(text: str) -> str:
    """SHA-256 hex of a JD, with runs of whitespace collapsed and edges stripped."""
    if not isinstance(text, str):
        raise TypeError("jd_hash expects str")
    normalised = _WHITESPACE.sub(" ", text).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def interview_meta_hash(meta: Mapping[str, object]) -> str:
    """SHA-256 hex of interview settings; key order does not matter."""
    if not isinstance(meta, Mapping):
        raise TypeError("interview_meta_hash expects a mapping")
    canonical = json.dumps(meta, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def short(digest: str, length: int = 8) -> str:
    """First ``length`` chars of a hex digest, for readable filenames."""
    if len(digest) < length:
        raise ValueError(f"digest too short to shorten to {length}")
    return digest[:length]
