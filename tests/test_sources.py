"""LocalFolderSource: listing, reading, glob filtering, path-traversal safety."""

from __future__ import annotations

import pytest

from cv_agent.sources import DocumentRef, LocalFolderSource


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "b.pdf").write_bytes(b"BBB")
    (tmp_path / "a.pdf").write_bytes(b"AAA")
    (tmp_path / "note.md").write_text("hello", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    return tmp_path


def test_list_is_glob_filtered_and_sorted(folder):
    src = LocalFolderSource(str(folder), "*.pdf")
    assert [r.id for r in src.list()] == ["a.pdf", "b.pdf"]


def test_list_excludes_directories(folder):
    src = LocalFolderSource(str(folder), "*")
    ids = [r.id for r in src.list()]
    assert "sub" not in ids


def test_document_ref_name_defaults_to_id(folder):
    ref = LocalFolderSource(str(folder), "*.md").list()[0]
    assert isinstance(ref, DocumentRef)
    assert ref.id == "note.md"
    assert ref.name == "note.md"


def test_read_bytes_and_text(folder):
    src = LocalFolderSource(str(folder), "*.pdf")
    assert src.read_bytes("a.pdf") == b"AAA"
    assert LocalFolderSource(str(folder), "*.md").read_text("note.md") == "hello"


def test_missing_file_raises(folder):
    with pytest.raises(FileNotFoundError):
        LocalFolderSource(str(folder), "*.pdf").read_bytes("nope.pdf")


@pytest.mark.parametrize("bad", ["../x.pdf", "sub/x.pdf", "..", "a/../b"])
def test_path_traversal_is_rejected(folder, bad):
    with pytest.raises(ValueError):
        LocalFolderSource(str(folder), "*").read_bytes(bad)


def test_empty_folder_lists_nothing(tmp_path):
    assert LocalFolderSource(str(tmp_path), "*.pdf").list() == ()


def test_missing_folder_raises_on_list(tmp_path):
    with pytest.raises(FileNotFoundError):
        LocalFolderSource(str(tmp_path / "ghost"), "*").list()
