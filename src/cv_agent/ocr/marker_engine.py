"""Marker-backed OCR engine (force-OCR to defeat poisoned text layers — ADR 0001).

Real IO: heavy models, imported lazily; excluded from the coverage gate and exercised
by a slow smoke test / offline evals. The exact Marker API can shift between versions —
this targets marker-pdf and is the one place to adjust if it changes.
"""

from __future__ import annotations

import os
import tempfile

from cv_agent.ocr.ports import OcrResult


class MarkerOcrEngine:
    def __init__(self, *, force_ocr: bool = True) -> None:
        self._force_ocr = force_ocr
        self._converter = None  # built lazily on first use

    def _ensure_converter(self) -> None:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict

        self._converter = PdfConverter(
            artifact_dict=create_model_dict(),
            config={"force_ocr": self._force_ocr},
        )

    def to_markdown(self, pdf_bytes: bytes) -> OcrResult:
        from marker.output import text_from_rendered

        if self._converter is None:
            self._ensure_converter()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            path = tmp.name
        try:
            rendered = self._converter(path)  # type: ignore[misc]
            markdown, _, _ = text_from_rendered(rendered)
        finally:
            os.unlink(path)

        return OcrResult(
            markdown=markdown,
            confidence=None,  # Marker exposes no single scalar; low-confidence flagging is a seam
            page_count=getattr(rendered, "page_count", None),
        )
