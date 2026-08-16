"""Application configuration resolved from an environment mapping.

BYOK, OpenAI-compatible, model-agnostic (ADR 0002): one default LLM plus optional
per-node overrides. ``from_env`` takes an explicit mapping (not ``os.environ``) so
it is trivially testable; the CLI loads ``.env`` and passes ``os.environ`` in.

Precedence for interview-time settings (CLI > JD meta > env > default) is applied by
the settings resolver, not here — this module only covers env → defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid — fail fast, clear message."""


class NodeName(str, Enum):
    """The four LLM nodes; names double as env override suffixes."""

    STRUCTURE_CV = "structure_cv"
    JD_RUBRIC = "jd_rubric"
    SCREEN = "screen"
    INTERVIEW = "interview"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class LLMConfig(_Frozen):
    base_url: str
    api_key: str
    model: str


_LLM_FIELDS = {"base_url": "LLM_BASE_URL", "api_key": "LLM_API_KEY", "model": "LLM_MODEL"}

DEFAULTS = {
    "CV_SOURCE_DIR": "./data/cvs",
    "JD_SOURCE_DIR": "./data/jds",
    "REPORT_SINK_DIR": "./data/reports",
    "STORE_PATH": "./data/cv_agent.sqlite",
    "MAX_CONCURRENCY": "1",
    "OCR_CONFIDENCE_THRESHOLD": "0.6",
}


def resolve_llm_config(env: Mapping[str, str], node: NodeName) -> LLMConfig:
    """Default LLM_* with optional LLM_*__<NODE> overrides for one node."""
    values: dict[str, str] = {}
    for field, base_key in _LLM_FIELDS.items():
        override = env.get(f"{base_key}__{node.name}")
        value = override if override not in (None, "") else env.get(base_key)
        if value in (None, ""):
            raise ConfigError(
                f"Missing LLM config for node {node.name}: set {base_key} "
                f"(or {base_key}__{node.name})."
            )
        values[field] = value
    return LLMConfig(**values)


def _require_int(env: Mapping[str, str], key: str, *, minimum: int) -> int:
    raw = env.get(key, DEFAULTS[key])
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ConfigError(f"{key} must be an integer, got {raw!r}.") from None
    if value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}, got {value}.")
    return value


def _require_unit_float(env: Mapping[str, str], key: str) -> float:
    raw = env.get(key, DEFAULTS[key])
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ConfigError(f"{key} must be a number, got {raw!r}.") from None
    if not 0.0 <= value <= 1.0:
        raise ConfigError(f"{key} must be within [0, 1], got {value}.")
    return value


class AppConfig(_Frozen):
    cv_source_dir: str
    jd_source_dir: str
    report_sink_dir: str
    store_path: str
    default_jd: str | None
    max_concurrency: int
    ocr_confidence_threshold: float
    llm: Mapping[NodeName, LLMConfig]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "AppConfig":
        llm = {node: resolve_llm_config(env, node) for node in NodeName}
        return cls(
            cv_source_dir=env.get("CV_SOURCE_DIR", DEFAULTS["CV_SOURCE_DIR"]),
            jd_source_dir=env.get("JD_SOURCE_DIR", DEFAULTS["JD_SOURCE_DIR"]),
            report_sink_dir=env.get("REPORT_SINK_DIR", DEFAULTS["REPORT_SINK_DIR"]),
            store_path=env.get("STORE_PATH", DEFAULTS["STORE_PATH"]),
            default_jd=env.get("DEFAULT_JD") or None,
            max_concurrency=_require_int(env, "MAX_CONCURRENCY", minimum=1),
            ocr_confidence_threshold=_require_unit_float(env, "OCR_CONFIDENCE_THRESHOLD"),
            llm=llm,
        )
