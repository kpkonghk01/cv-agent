"""Source port — lists and reads documents (CVs or a JD). See AGENT.md.

The same port serves CV reading (iterate all) and JD reading (pick one). Folder now,
Google Drive later — swap the adapter, not the pipeline.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class DocumentRef(BaseModel):
    """A selectable document in a Source."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.name:
            object.__setattr__(self, "name", self.id)


@runtime_checkable
class Source(Protocol):
    def list(self) -> tuple[DocumentRef, ...]: ...

    def read_bytes(self, doc_id: str) -> bytes: ...

    def read_text(self, doc_id: str) -> str: ...
