"""ReportSink port — where exported artifacts go (folder now, Drive later)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ReportSink(Protocol):
    def write(self, filename: str, content: str) -> str:
        """Write ``content`` under ``filename``; return the location written."""
        ...
