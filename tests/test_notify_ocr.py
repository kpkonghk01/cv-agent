"""Small ports: NullNotifier is a no-op; OcrResult is an immutable value."""

from __future__ import annotations

import pytest

from cv_agent.notify import NullNotifier
from cv_agent.ocr import OcrResult


def test_null_notifier_is_noop():
    assert NullNotifier().notify("anything") is None


def test_ocr_result_defaults_and_immutability():
    r = OcrResult(markdown="# hi")
    assert r.confidence is None
    assert r.page_count is None
    with pytest.raises(Exception):
        r.markdown = "x"  # type: ignore[misc]
