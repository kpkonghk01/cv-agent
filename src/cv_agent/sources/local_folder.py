"""Local folder implementation of the Source port."""

from __future__ import annotations

from pathlib import Path

from cv_agent.fs import safe_name
from cv_agent.sources.ports import DocumentRef


class LocalFolderSource:
    """Read documents from a directory, filtered by a glob (e.g. ``*.pdf``, ``*.md``)."""

    def __init__(self, directory: str, glob: str = "*") -> None:
        self._dir = Path(directory)
        self._glob = glob

    def list(self) -> tuple[DocumentRef, ...]:
        if not self._dir.is_dir():
            raise FileNotFoundError(f"source directory not found: {self._dir}")
        files = sorted(p for p in self._dir.glob(self._glob) if p.is_file())
        return tuple(DocumentRef(id=p.name) for p in files)

    def read_bytes(self, doc_id: str) -> bytes:
        path = self._dir / safe_name(doc_id)
        if not path.is_file():
            raise FileNotFoundError(f"document not found: {doc_id}")
        return path.read_bytes()

    def read_text(self, doc_id: str) -> str:
        return self.read_bytes(doc_id).decode("utf-8")
