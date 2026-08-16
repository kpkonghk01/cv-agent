"""Sink layer: write exported reports to a backend (folder now, Drive later)."""

from __future__ import annotations

from cv_agent.sinks.local_folder import LocalFolderSink
from cv_agent.sinks.ports import ReportSink

__all__ = ["ReportSink", "LocalFolderSink"]
