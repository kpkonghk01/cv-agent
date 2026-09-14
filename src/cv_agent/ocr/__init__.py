"""OCR layer: engine port + Marker implementation (ADR 0001)."""

from __future__ import annotations

from cv_agent.ocr.marker_engine import MarkerOcrEngine
from cv_agent.ocr.ports import OcrEngine, OcrResult
from cv_agent.ocr.text_layer import denoise_text_layer, extract_text_layer

__all__ = [
    "OcrEngine",
    "OcrResult",
    "MarkerOcrEngine",
    "denoise_text_layer",
    "extract_text_layer",
]
