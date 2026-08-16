"""SQLite backend implementing all three storage ports in one file (ADR 0003).

Models are stored as JSON text and rehydrated via Pydantic, so schema evolution
is a model concern, not a migration concern, for v1. Use ``:memory:`` in tests.
"""

from __future__ import annotations

import sqlite3
from types import TracebackType

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.rubric import Rubric
from cv_agent.store.records import ProcessedRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (cv_hash TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rubrics  (jd_hash TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processed (
    cv_hash TEXT NOT NULL,
    jd_hash TEXT NOT NULL,
    json    TEXT NOT NULL,
    PRIMARY KEY (cv_hash, jd_hash)
);
"""


class SqliteStore:
    """One SQLite file behind ProfileCache, RubricCache, and ProcessedRegistry."""

    def __init__(self, path: str) -> None:
        if not path:
            raise ValueError("SqliteStore requires a path (use ':memory:' for tests)")
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- ProfileCache -----------------------------------------------------

    def get_profile(self, cv_hash: str) -> CandidateProfile | None:
        row = self._fetch("SELECT json FROM profiles WHERE cv_hash = ?", (cv_hash,))
        return CandidateProfile.model_validate_json(row) if row else None

    def put_profile(self, cv_hash: str, profile: CandidateProfile) -> None:
        self._upsert(
            "INSERT OR REPLACE INTO profiles (cv_hash, json) VALUES (?, ?)",
            (cv_hash, profile.model_dump_json()),
        )

    # --- RubricCache ------------------------------------------------------

    def get_rubric(self, jd_hash: str) -> Rubric | None:
        row = self._fetch("SELECT json FROM rubrics WHERE jd_hash = ?", (jd_hash,))
        return Rubric.model_validate_json(row) if row else None

    def put_rubric(self, jd_hash: str, rubric: Rubric) -> None:
        self._upsert(
            "INSERT OR REPLACE INTO rubrics (jd_hash, json) VALUES (?, ?)",
            (jd_hash, rubric.model_dump_json()),
        )

    # --- ProcessedRegistry ------------------------------------------------

    def is_processed(self, cv_hash: str, jd_hash: str) -> bool:
        row = self._fetch(
            "SELECT 1 FROM processed WHERE cv_hash = ? AND jd_hash = ?", (cv_hash, jd_hash)
        )
        return row is not None

    def get_record(self, cv_hash: str, jd_hash: str) -> ProcessedRecord | None:
        row = self._fetch(
            "SELECT json FROM processed WHERE cv_hash = ? AND jd_hash = ?", (cv_hash, jd_hash)
        )
        return ProcessedRecord.model_validate_json(row) if row else None

    def mark_processed(self, record: ProcessedRecord) -> None:
        self._upsert(
            "INSERT OR REPLACE INTO processed (cv_hash, jd_hash, json) VALUES (?, ?, ?)",
            (record.cv_hash, record.jd_hash, record.model_dump_json()),
        )

    # --- Internals & lifecycle -------------------------------------------

    def _fetch(self, sql: str, params: tuple[object, ...]) -> str | None:
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None

    def _upsert(self, sql: str, params: tuple[object, ...]) -> None:
        self._conn.execute(sql, params)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SqliteStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
