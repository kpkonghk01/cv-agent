"""Source layer: read CVs and JDs from a backend (folder now, Drive later)."""

from __future__ import annotations

from cv_agent.sources.local_folder import LocalFolderSource
from cv_agent.sources.ports import DocumentRef, Source

__all__ = ["DocumentRef", "Source", "LocalFolderSource"]
