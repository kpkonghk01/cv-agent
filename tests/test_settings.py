"""Settings precedence (CLI > meta > default), enum validation, meta hash."""

from __future__ import annotations

import pytest

from cv_agent.config import ConfigError
from cv_agent.domain.enums import RoleArchetype, Strictness
from cv_agent.graph.reports import RejectReportMode
from cv_agent.settings import resolve_settings


def test_defaults_when_nothing_supplied():
    s = resolve_settings({}, {}, default_title="Eng")
    assert s.title == "Eng"
    assert s.role_override is None  # auto-detect
    assert s.interview_format == "mixed"
    assert s.minutes == 45
    assert s.output_language == "zh-Hant"
    assert s.strictness is Strictness.LOOSE
    assert s.reject_mode is RejectReportMode.FULL


def test_meta_overrides_default():
    meta = {"role_archetype": "technical", "default_minutes": 30, "screening_strictness": "strict"}
    s = resolve_settings(meta, {}, default_title="Eng")
    assert s.role_override is RoleArchetype.TECHNICAL
    assert s.minutes == 30
    assert s.strictness is Strictness.STRICT


def test_cli_overrides_meta():
    meta = {"default_minutes": 30, "interview_format": "behavioral"}
    cli = {"minutes": 60, "format": "technical"}
    s = resolve_settings(meta, cli, default_title="Eng")
    assert s.minutes == 60
    assert s.interview_format == "technical"


def test_reject_mode_from_cli():
    assert resolve_settings({}, {"reject_mode": "concise"}, default_title="X").reject_mode is (
        RejectReportMode.CONCISE
    )
    assert resolve_settings({}, {"reject_mode": "none"}, default_title="X").reject_mode is (
        RejectReportMode.NONE
    )


def test_invalid_enum_raises_configerror():
    with pytest.raises(ConfigError):
        resolve_settings({}, {"role": "wizard"}, default_title="X")
    with pytest.raises(ConfigError):
        resolve_settings({"screening_strictness": "brutal"}, {}, default_title="X")


def test_invalid_minutes_raises():
    with pytest.raises(ConfigError):
        resolve_settings({}, {"minutes": "quick"}, default_title="X")


def test_meta_hash_changes_with_round_and_settings():
    base = resolve_settings({}, {}, default_title="X").interview_meta_hash
    r2 = resolve_settings({}, {"round": 2}, default_title="X").interview_meta_hash
    longer = resolve_settings({}, {"minutes": 90}, default_title="X").interview_meta_hash
    assert base != r2 != longer
    assert base != longer
