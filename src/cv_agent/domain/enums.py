"""Closed vocabularies shared across the domain (see CONTEXT.md)."""

from __future__ import annotations

from enum import Enum


class RoleArchetype(str, Enum):
    """Interviewing style a JD implies; steers depth vs breadth."""

    TECHNICAL = "technical"
    MANAGEMENT = "management"
    HYBRID = "hybrid"


class RequirementKind(str, Enum):
    """Whether a Requirement gates the verdict or only scores it."""

    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class ScoreLevel(str, Enum):
    """How well a Candidate meets a single Requirement."""

    MET = "met"
    PARTIAL = "partial"
    UNMET = "unmet"


class Strictness(str, Enum):
    """How a must-have Requirement that is only ``Partial`` is treated."""

    LOOSE = "loose"   # a Partial must-have passes (default)
    STRICT = "strict"  # a must-have must be Met to pass


class Verdict(str, Enum):
    """Outcome of screening one Candidate against one JD."""

    PASS = "pass"
    REJECT = "reject"


class CandidateStatus(str, Enum):
    """Processing outcome recorded for a Candidate in the registry."""

    OK = "ok"
    ERROR = "error"
    MANUAL_REVIEW = "manual_review"
