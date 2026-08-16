"""Filesystem safety shared by folder-backed adapters."""

from __future__ import annotations

import os


def safe_name(name: str) -> str:
    """Return ``name`` if it is a bare filename, else raise ValueError.

    Rejects empty names, ``.``/``..``, and anything containing a path separator —
    the guard against path traversal for local Source/Sink adapters.
    """
    if not name or name in (".", ".."):
        raise ValueError(f"unsafe name: {name!r}")
    if name != os.path.basename(name) or os.sep in name or (os.altsep and os.altsep in name):
        raise ValueError(f"unsafe name (path components not allowed): {name!r}")
    return name
