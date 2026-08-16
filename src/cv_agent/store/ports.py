"""Storage ports (adapters swap without touching the pipeline — see AGENT.md).

Three focused caches, keyed differently (ADR 0003). A single backend may implement
all three; callers should depend on these Protocols, not the concrete store.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.rubric import Rubric
from cv_agent.store.records import ProcessedRecord


@runtime_checkable
class ProfileCache(Protocol):
    """Candidate Profile keyed by ``cv_hash`` (OCR is expensive, JD-independent)."""

    def get_profile(self, cv_hash: str) -> CandidateProfile | None: ...

    def put_profile(self, cv_hash: str, profile: CandidateProfile) -> None: ...


@runtime_checkable
class RubricCache(Protocol):
    """Rubric keyed by ``jd_hash`` (JD-independent of any CV)."""

    def get_rubric(self, jd_hash: str) -> Rubric | None: ...

    def put_rubric(self, jd_hash: str, rubric: Rubric) -> None: ...


@runtime_checkable
class ProcessedRegistry(Protocol):
    """Screening outcomes keyed by ``(cv_hash, jd_hash)`` for skip-on-rerun."""

    def is_processed(self, cv_hash: str, jd_hash: str) -> bool: ...

    def get_record(self, cv_hash: str, jd_hash: str) -> ProcessedRecord | None: ...

    def mark_processed(self, record: ProcessedRecord) -> None: ...


@runtime_checkable
class Store(ProfileCache, RubricCache, ProcessedRegistry, Protocol):
    """A backend that provides all three caches (the SQLite store does)."""
