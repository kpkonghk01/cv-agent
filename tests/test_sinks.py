"""LocalFolderSink: writing, directory creation, path-traversal safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from cv_agent.sinks import LocalFolderSink


def test_write_returns_path_and_persists_content(tmp_path):
    sink = LocalFolderSink(str(tmp_path))
    path = sink.write("pass__alice__jd__x__interview-brief.md", "# Brief")
    assert Path(path).read_text(encoding="utf-8") == "# Brief"
    assert Path(path).parent == tmp_path


def test_creates_directory_if_missing(tmp_path):
    target = tmp_path / "reports" / "nested"
    sink = LocalFolderSink(str(target))
    path = sink.write("reject__bob__jd__reject-report.md", "nope")
    assert Path(path).exists()


def test_overwrite_is_allowed_for_same_filename(tmp_path):
    sink = LocalFolderSink(str(tmp_path))
    sink.write("f.md", "v1")
    path = sink.write("f.md", "v2")
    assert Path(path).read_text(encoding="utf-8") == "v2"


@pytest.mark.parametrize("bad", ["../escape.md", "sub/child.md", "..", ""])
def test_unsafe_filename_is_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        LocalFolderSink(str(tmp_path)).write(bad, "x")
