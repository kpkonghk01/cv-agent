"""SQLite backend implementing all three storage ports in one file (ADR 0003).

Models are stored as JSON text and rehydrated via Pydantic, so schema evolution
is a model concern, not a migration concern, for v1. Use ``:memory:`` in tests.
"""

from __future__ import annotations

import sqlite3
import threading
from types import TracebackType

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.rubric import Rubric
from cv_agent.domain.screening import ScreeningReport
from cv_agent.store.records import FailureRecord, ProcessedRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (cv_hash TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rubrics  (jd_hash TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processed (
    cv_hash TEXT NOT NULL,
    jd_hash TEXT NOT NULL,
    json    TEXT NOT NULL,
    PRIMARY KEY (cv_hash, jd_hash)
);
CREATE TABLE IF NOT EXISTS screenings (
    cv_hash TEXT NOT NULL,
    jd_hash TEXT NOT NULL,
    json    TEXT NOT NULL,
    PRIMARY KEY (cv_hash, jd_hash)
);
CREATE TABLE IF NOT EXISTS source_index (
    source_id TEXT PRIMARY KEY,   -- Drive file id / filename
    cv_hash   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS failures (
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
        # check_same_thread=False + a lock make the store usable from a thread pool.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
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

    def find_cv_by_name(self, name: str) -> tuple[str, ...]:
        """cv_hashes whose profile name contains ``name`` (case-insensitive)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT cv_hash FROM profiles "
                "WHERE lower(json_extract(json, '$.name')) LIKE '%' || lower(?) || '%'",
                (name,),
            )
            return tuple(row[0] for row in cur.fetchall())

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

    # --- ScreeningCache (full report, keyed by (cv_hash, jd_hash)) --------

    def get_screening(self, cv_hash: str, jd_hash: str) -> ScreeningReport | None:
        row = self._fetch(
            "SELECT json FROM screenings WHERE cv_hash = ? AND jd_hash = ?", (cv_hash, jd_hash)
        )
        return ScreeningReport.model_validate_json(row) if row else None

    def put_screening(self, cv_hash: str, jd_hash: str, report: ScreeningReport) -> None:
        self._upsert(
            "INSERT OR REPLACE INTO screenings (cv_hash, jd_hash, json) VALUES (?, ?, ?)",
            (cv_hash, jd_hash, report.model_dump_json()),
        )

    # --- SourceIndex (source id -> cv_hash, to skip re-downloading) --------

    def get_cv_hash(self, source_id: str) -> str | None:
        return self._fetch("SELECT cv_hash FROM source_index WHERE source_id = ?", (source_id,))

    def put_cv_hash(self, source_id: str, cv_hash: str) -> None:
        self._upsert(
            "INSERT OR REPLACE INTO source_index (source_id, cv_hash) VALUES (?, ?)",
            (source_id, cv_hash),
        )

    # --- FailureCache (remembered failures, keyed by (cv_hash, jd_hash)) ---

    def get_failure(self, cv_hash: str, jd_hash: str) -> FailureRecord | None:
        row = self._fetch(
            "SELECT json FROM failures WHERE cv_hash = ? AND jd_hash = ?", (cv_hash, jd_hash)
        )
        return FailureRecord.model_validate_json(row) if row else None

    def put_failure(self, cv_hash: str, jd_hash: str, record: FailureRecord) -> None:
        self._upsert(
            "INSERT OR REPLACE INTO failures (cv_hash, jd_hash, json) VALUES (?, ?, ?)",
            (cv_hash, jd_hash, record.model_dump_json()),
        )

    def forget_failure(self, cv_hash: str, jd_hash: str | None = None) -> int:
        if jd_hash is None:
            return self._delete("DELETE FROM failures WHERE cv_hash = ?", (cv_hash,))
        return self._delete(
            "DELETE FROM failures WHERE cv_hash = ? AND jd_hash = ?", (cv_hash, jd_hash)
        )

    # --- Forget (maintenance: force re-analysis of a CV) ------------------

    def forget_profile(self, cv_hash: str) -> int:
        """Drop the cached Candidate Profile for a CV. Returns rows removed."""
        return self._delete("DELETE FROM profiles WHERE cv_hash = ?", (cv_hash,))

    def forget_processed(self, cv_hash: str, jd_hash: str | None = None) -> int:
        """Drop screening judgments for a CV — all JDs, or one when jd_hash is given."""
        if jd_hash is None:
            return self._delete("DELETE FROM processed WHERE cv_hash = ?", (cv_hash,))
        return self._delete(
            "DELETE FROM processed WHERE cv_hash = ? AND jd_hash = ?", (cv_hash, jd_hash)
        )

    def forget_screening(self, cv_hash: str, jd_hash: str | None = None) -> int:
        """Drop cached full screening reports for a CV — all JDs, or one."""
        if jd_hash is None:
            return self._delete("DELETE FROM screenings WHERE cv_hash = ?", (cv_hash,))
        return self._delete(
            "DELETE FROM screenings WHERE cv_hash = ? AND jd_hash = ?", (cv_hash, jd_hash)
        )

    def forget_source_index(self, cv_hash: str) -> int:
        """Drop source-id → cv_hash mappings for a CV (so it is re-downloaded next run)."""
        return self._delete("DELETE FROM source_index WHERE cv_hash = ?", (cv_hash,))

    # --- Internals & lifecycle -------------------------------------------

    def _delete(self, sql: str, params: tuple[object, ...]) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.rowcount

    def _fetch(self, sql: str, params: tuple[object, ...]) -> str | None:
        with self._lock:
            cur = self._conn.execute(sql, params)
            row = cur.fetchone()
        return row[0] if row else None

    def _upsert(self, sql: str, params: tuple[object, ...]) -> None:
        with self._lock:
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
