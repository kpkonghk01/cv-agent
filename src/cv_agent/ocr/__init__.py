"""OCR layer: engine port + Marker implementation (ADR 0001)."""

from __future__ import annotations

from cv_agent.ocr.marker_engine import MarkerOcrEngine
from cv_agent.ocr.ports import OcrEngine, OcrResult

__all__ = ["OcrEngine", "OcrResult", "MarkerOcrEngine"]
