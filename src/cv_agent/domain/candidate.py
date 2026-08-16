"""Candidate Profile — the structured, JD-independent view of a CV.

All models are frozen (immutable); sequences are tuples so a profile cannot be
mutated in place. See CONTEXT.md for the domain terms.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Contact(_Frozen):
    email: str | None = None
    phone: str | None = None


class WorkExperience(_Frozen):
    company: str
    title: str | None = None
    start: str | None = None
    end: str | None = None
    highlights: tuple[str, ...] = ()


class Education(_Frozen):
    school: str
    degree: str | None = None
    field: str | None = None
    year: str | None = None


class Project(_Frozen):
    name: str
    description: str | None = None
    tech: tuple[str, ...] = ()


class Certification(_Frozen):
    name: str
    issuer: str | None = None
    year: str | None = None


class JobHoppingSignal(_Frozen):
    """Advisory only — never an automatic reject (see CONTEXT.md)."""

    avg_tenure_months: float | None = None
    short_stints: int | None = None
    note: str | None = None


class CandidateProfile(_Frozen):
    # Soft identity (may be garbled/missing under anti-analysis watermarks)
    name: str | None = None
    contact: Contact | None = None

    # Overview
    years_experience: float | None = None
    current_title: str | None = None
    current_company: str | None = None

    # Body — values keep their original language (CN/EN); tech terms untranslated
    skills: tuple[str, ...] = ()
    work_experience: tuple[WorkExperience, ...] = ()
    education: tuple[Education, ...] = ()
    projects: tuple[Project, ...] = ()
    certifications: tuple[Certification, ...] = ()
    job_hopping: JobHoppingSignal | None = None

    # Metadata
    languages_detected: tuple[str, ...] = ()
    ocr_confidence: float | None = None
    source_markdown: str = ""
    extras: dict[str, str] = {}
