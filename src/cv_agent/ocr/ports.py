"""OCR port. The graph depends on this, so it is testable with a fake engine."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class OcrResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    markdown: str
    confidence: float | None = None
    page_count: int | None = None


@runtime_checkable
class OcrEngine(Protocol):
    def to_markdown(self, pdf_bytes: bytes) -> OcrResult: ...
