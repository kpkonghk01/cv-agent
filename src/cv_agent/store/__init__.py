"""Storage layer: three cache ports (ADR 0003) with a SQLite backend."""

from __future__ import annotations

from cv_agent.store.ports import (
    FailureCache,
    ProcessedRegistry,
    ProfileCache,
    RubricCache,
    ScreeningCache,
    SourceIndex,
    Store,
)
from cv_agent.store.records import FailureRecord, ProcessedRecord
from cv_agent.store.sqlite_store import SqliteStore

__all__ = [
    "ProcessedRegistry",
    "ProfileCache",
    "RubricCache",
    "ScreeningCache",
    "SourceIndex",
    "FailureCache",
    "Store",
    "ProcessedRecord",
    "FailureRecord",
    "SqliteStore",
]
