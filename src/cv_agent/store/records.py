"""Persisted registry record for one (CV, JD) screening outcome."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from cv_agent.domain.enums import CandidateStatus, Verdict


class FailureRecord(BaseModel):
    """A remembered per-(CV, JD) processing failure, so re-runs skip it by default
    instead of re-paying OCR/LLM — until --retry or --handoff asks otherwise."""

    model_config = ConfigDict(frozen=True)

    step: str          # where it failed: ocr | structure | screen | process
    reason: str
    created_at: str | None = None


class ProcessedRecord(BaseModel):
    """What we remember about screening one CV against one JD (see ADR 0003).

    ``created_at`` is a caller-supplied ISO-8601 string so persistence stays
    deterministic and testable; the store never invents timestamps.
    """

    model_config = ConfigDict(frozen=True)

    cv_hash: str
    jd_hash: str
    verdict: Verdict
    status: CandidateStatus = CandidateStatus.OK
    reasons: tuple[str, ...] = ()
    soft_name: str | None = None
    soft_phone: str | None = None
    report_path: str | None = None
    created_at: str | None = None
