"""Resolve interview-time settings with precedence CLI > JD meta > built-in default.

Env is not a source here (it carries no interview settings). Pure and testable; the CLI
passes an argparse-derived mapping, the meta a parsed YAML mapping.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from cv_agent.config import ConfigError
from cv_agent.domain.enums import RoleArchetype, Strictness
from cv_agent.graph.reports import RejectReportMode
from cv_agent.hashing import interview_meta_hash


class ResolvedSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    role_override: RoleArchetype | None
    interview_format: str
    minutes: int
    output_language: str
    strictness: Strictness
    reject_mode: RejectReportMode
    interview_meta_hash: str


def _parse_enum(enum, raw, label):
    try:
        return enum(raw)
    except ValueError:
        allowed = ", ".join(e.value for e in enum)
        raise ConfigError(f"invalid {label}: {raw!r} (allowed: {allowed})") from None


def _as_int(raw, label):
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ConfigError(f"{label} must be an integer, got {raw!r}") from None


def resolve_settings(
    meta: Mapping[str, object],
    cli: Mapping[str, object],
    *,
    default_title: str,
) -> ResolvedSettings:
    def pick(cli_key, meta_key, default=None):
        if cli.get(cli_key) is not None:
            return cli[cli_key]
        if meta.get(meta_key) is not None:
            return meta[meta_key]
        return default

    role_raw = pick("role", "role_archetype")
    role_override = _parse_enum(RoleArchetype, role_raw, "role_archetype") if role_raw else None
    fmt = str(pick("format", "interview_format", "mixed"))
    minutes = _as_int(pick("minutes", "default_minutes", 45), "minutes")
    lang = str(pick("lang", "output_language", "zh-Hant"))
    strictness = _parse_enum(
        Strictness, str(pick("strictness", "screening_strictness", "loose")), "strictness"
    )
    reject_mode = _parse_enum(
        RejectReportMode, str(cli.get("reject_mode", "full")), "reject_mode"
    )

    meta_hash = interview_meta_hash(
        {
            "minutes": minutes,
            "format": fmt,
            "language": lang,
            "role": role_override.value if role_override else "auto",
            "round": cli.get("round"),
        }
    )
    return ResolvedSettings(
        title=str(pick("title", "title", default_title)),
        role_override=role_override,
        interview_format=fmt,
        minutes=minutes,
        output_language=lang,
        strictness=strictness,
        reject_mode=reject_mode,
        interview_meta_hash=meta_hash,
    )
