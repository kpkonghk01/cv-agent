"""Hashing: dedup keys must be deterministic and robust to trivial differences."""

from __future__ import annotations

import pytest

from cv_agent.hashing import cv_hash, interview_meta_hash, jd_hash


def test_cv_hash_is_deterministic_and_hex():
    h = cv_hash(b"%PDF-1.7 ...")
    assert h == cv_hash(b"%PDF-1.7 ...")
    assert len(h) == 64
    int(h, 16)  # valid hex


def test_cv_hash_differs_on_different_bytes():
    assert cv_hash(b"a") != cv_hash(b"b")


def test_jd_hash_ignores_surrounding_and_collapsible_whitespace():
    a = jd_hash("Senior Engineer\n\n  Must have Go.  ")
    b = jd_hash("Senior Engineer\nMust have Go.")
    assert a == b


def test_jd_hash_is_case_and_content_sensitive():
    assert jd_hash("Go required") != jd_hash("go required")
    assert jd_hash("Go") != jd_hash("Rust")


def test_interview_meta_hash_is_order_independent():
    a = interview_meta_hash({"minutes": 45, "role": "technical"})
    b = interview_meta_hash({"role": "technical", "minutes": 45})
    assert a == b


def test_interview_meta_hash_changes_with_values():
    base = interview_meta_hash({"minutes": 45})
    assert base != interview_meta_hash({"minutes": 30})


def test_hashes_have_short_helpers_for_filenames():
    from cv_agent.hashing import short

    assert short(cv_hash(b"x")) == cv_hash(b"x")[:8]
    with pytest.raises(ValueError):
        short("abc", length=8)  # too short to shorten to 8
