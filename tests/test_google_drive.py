"""GoogleDriveSource: date-folder filtering, listing, download — with a fake service."""

from __future__ import annotations

from cv_agent.sources import GoogleDriveSource

FOLDER = "application/vnd.google-apps.folder"
PDF = "application/pdf"


class _Exec:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class FakeDriveService:
    """Minimal stand-in for the Drive v3 client used by GoogleDriveSource."""

    def __init__(self, tree, blobs):
        self._tree = tree      # parent_id -> [{id, name, mime}]
        self._blobs = blobs    # file_id -> bytes

    def files(self):
        return self

    def list(self, q, fields, pageSize, pageToken):
        parent = q.split("'")[1]
        mime = q.split("mimeType='")[1].split("'")[0]
        files = [
            {"id": c["id"], "name": c["name"]}
            for c in self._tree.get(parent, [])
            if c["mime"] == mime
        ]
        return _Exec({"files": files})

    def get_media(self, fileId):
        return _Exec(self._blobs[fileId])


def _source():
    tree = {
        "root": [
            {"id": "f1", "name": "20260817", "mime": FOLDER},
            {"id": "f2", "name": "20260818", "mime": FOLDER},
        ],
        # deliberately out of name order to prove list() sorts them
        "f1": [{"id": "p1", "name": "b.pdf", "mime": PDF}, {"id": "p0", "name": "a.pdf", "mime": PDF}],
        "f2": [{"id": "p2", "name": "new.pdf", "mime": PDF}],
    }
    return GoogleDriveSource(
        FakeDriveService(tree, {"p0": b"A", "p1": b"B", "p2": b"NEW"}), "root"
    )


def test_list_traverses_date_folders_and_sorts_pdfs_by_name():
    refs = _source().list()
    # folders sorted (f1 before f2); PDFs within a folder sorted (a.pdf before b.pdf)
    assert [(r.id, r.name) for r in refs] == [
        ("p0", "a.pdf"), ("p1", "b.pdf"), ("p2", "new.pdf")
    ]


def test_list_since_keeps_only_newer_date_folders():
    refs = _source().list(since="20260818")
    assert [r.name for r in refs] == ["new.pdf"]


def test_read_bytes_and_text_by_file_id():
    src = _source()
    assert src.read_bytes("p2") == b"NEW"
    assert src.read_text("p0") == "A"
