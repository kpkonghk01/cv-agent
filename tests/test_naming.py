"""Report filename routing: verdict prefixes, safe slugs, no-overwrite discriminator."""

from __future__ import annotations

from cv_agent.naming import (
    candidate_id,
    interview_brief_filename,
    reject_report_filename,
    slugify,
)

HASH = "abcdef1234567890" * 4  # 64 hex chars


def test_slugify_basic():
    assert slugify("AI Applications Engineer") == "ai-applications-engineer"
    assert slugify("Multiple   spaces") == "multiple-spaces"


def test_slugify_keeps_cjk():
    assert slugify(" 後端 工程師 ") == "後端-工程師"


def test_slugify_strips_filesystem_unsafe_chars():
    assert slugify('a/b:c*d?"e') == "a-b-c-d-e"
    assert "/" not in slugify("path/like/name")


def test_candidate_id_prefers_soft_name():
    assert candidate_id("Alice Wang", HASH) == "alice-wang"


def test_candidate_id_falls_back_to_short_hash():
    assert candidate_id(None, HASH) == HASH[:8]
    assert candidate_id("", HASH) == HASH[:8]
    # a name that slugifies to nothing also falls back
    assert candidate_id("///", HASH) == HASH[:8]


def test_interview_brief_filename():
    assert (
        interview_brief_filename("alice-wang", "ai-app-eng", "1a2b3c4d")
        == "pass__alice-wang__ai-app-eng__1a2b3c4d__interview-brief.md"
    )


def test_reject_report_filename():
    assert (
        reject_report_filename("alice-wang", "ai-app-eng")
        == "reject__alice-wang__ai-app-eng__reject-report.md"
    )


def test_filenames_are_safe_even_with_hostile_inputs():
    name = interview_brief_filename(candidate_id("a/b", HASH), slugify("PM/Lead"), "x")
    assert name.count("/") == 0
    assert name.startswith("pass__") and name.endswith("__interview-brief.md")
