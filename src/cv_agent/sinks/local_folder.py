"""Local folder implementation of the ReportSink port."""

from __future__ import annotations

from pathlib import Path

from cv_agent.fs import safe_name


class LocalFolderSink:
    """Write reports as files into a directory (created on demand)."""

    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)

    def write(self, filename: str, content: str) -> str:
        path = self._dir / safe_name(filename)
        self._dir.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)
