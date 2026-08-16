"""STRUCTURE_CV node: Marker markdown → CandidateProfile."""

from __future__ import annotations

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.llm.structured import LLMClient, structured_call
from cv_agent.nodes.prompts import structure_messages


def structure_cv(
    client: LLMClient,
    markdown: str,
    *,
    ocr_confidence: float | None = None,
    max_retries: int = 2,
) -> CandidateProfile:
    """Extract a profile from OCR markdown; the node (not the LLM) attaches provenance."""
    profile = structured_call(
        client, CandidateProfile, structure_messages(markdown), max_retries=max_retries
    )
    return profile.model_copy(
        update={"source_markdown": markdown, "ocr_confidence": ocr_confidence}
    )
