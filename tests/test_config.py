"""Config: env parsing, per-node LLM overrides, validation, fail-fast errors."""

from __future__ import annotations

import pytest

from cv_agent.config import AppConfig, ConfigError, LLMConfig, NodeName, resolve_llm_config

BASE_ENV = {
    "LLM_BASE_URL": "http://127.0.0.1:8000/v1",
    "LLM_API_KEY": "sk-local",
    "LLM_MODEL": "Qwen3.8-27B",
}


def test_default_llm_applies_to_every_node():
    cfg = resolve_llm_config(BASE_ENV, NodeName.SCREEN)
    assert cfg == LLMConfig(
        base_url="http://127.0.0.1:8000/v1", api_key="sk-local", model="Qwen3.8-27B"
    )


def test_per_node_model_override():
    env = {**BASE_ENV, "LLM_MODEL__INTERVIEW": "gpt-strong"}
    assert resolve_llm_config(env, NodeName.INTERVIEW).model == "gpt-strong"
    # other nodes keep the default
    assert resolve_llm_config(env, NodeName.SCREEN).model == "Qwen3.8-27B"


def test_per_node_can_override_base_url_and_key_independently():
    env = {
        **BASE_ENV,
        "LLM_BASE_URL__STRUCTURE_CV": "http://local/v1",
        "LLM_API_KEY__STRUCTURE_CV": "sk-x",
    }
    cfg = resolve_llm_config(env, NodeName.STRUCTURE_CV)
    assert cfg.base_url == "http://local/v1"
    assert cfg.api_key == "sk-x"
    assert cfg.model == "Qwen3.8-27B"  # inherited


def test_missing_required_llm_field_raises_configerror():
    with pytest.raises(ConfigError):
        resolve_llm_config({"LLM_BASE_URL": "x", "LLM_API_KEY": "y"}, NodeName.SCREEN)


def test_appconfig_from_env_defaults():
    cfg = AppConfig.from_env(BASE_ENV)
    assert cfg.cv_source_dir == "./data/cvs"
    assert cfg.jd_source_dir == "./data/jds"
    assert cfg.report_sink_dir == "./data/reports"
    assert cfg.store_path == "./data/cv_agent.sqlite"
    assert cfg.max_concurrency == 1
    assert cfg.ocr_confidence_threshold == 0.6
    assert cfg.default_jd is None


def test_appconfig_builds_llm_map_for_all_nodes():
    cfg = AppConfig.from_env(BASE_ENV)
    assert set(cfg.llm.keys()) == set(NodeName)
    assert cfg.llm[NodeName.SCREEN].model == "Qwen3.8-27B"


def test_appconfig_overrides_from_env():
    env = {**BASE_ENV, "MAX_CONCURRENCY": "4", "DEFAULT_JD": "eng.md", "CV_SOURCE_DIR": "/cvs"}
    cfg = AppConfig.from_env(env)
    assert cfg.max_concurrency == 4
    assert cfg.default_jd == "eng.md"
    assert cfg.cv_source_dir == "/cvs"


@pytest.mark.parametrize(
    "bad",
    [
        {"MAX_CONCURRENCY": "0"},
        {"MAX_CONCURRENCY": "-1"},
        {"MAX_CONCURRENCY": "two"},
        {"OCR_CONFIDENCE_THRESHOLD": "1.5"},
        {"OCR_CONFIDENCE_THRESHOLD": "nan-ish"},
    ],
)
def test_appconfig_validates_numeric_ranges(bad):
    with pytest.raises(ConfigError):
        AppConfig.from_env({**BASE_ENV, **bad})


def test_appconfig_is_immutable():
    cfg = AppConfig.from_env(BASE_ENV)
    with pytest.raises(Exception):
        cfg.max_concurrency = 9  # type: ignore[misc]
