"""Text-layer scavenge (pdfplumber) to recover fields the image OCR drops.

Marker force-OCR yields clean text but skips image-classified regions (e.g. a name
rendered as a graphic — see the boss直聘 case in AGENT.md). The PDF text layer often
still holds those fields, buried in the platform's watermark noise. We extract it,
denoise the obvious watermark junk, and offer it to the structuring LLM as a *secondary*
hint: prefer the clean OCR body, scavenge only the fields the OCR missed.
"""

from __future__ import annotations

import re

# A long, spaceless, mixed letter+digit token is almost always a watermark id,
# not real CV content (real long tokens like "SpringCloudGateway" have no digits;
# phones are all-digits; emails contain '@'/'.').
_WATERMARK_TOKEN = re.compile(r"^[A-Za-z0-9_\-~]{16,}$")


def _is_watermark_token(line: str) -> bool:
    return (
        bool(_WATERMARK_TOKEN.match(line))
        and any(c.isdigit() for c in line)
        and any(c.isalpha() for c in line)
    )


def denoise_text_layer(text: str) -> str:
    """Drop the poisoned text layer's obvious noise: single-char fragments and
    long random watermark tokens. Pure and deterministic."""
    kept = [
        line
        for raw in text.splitlines()
        if len(line := raw.strip()) > 1 and not _is_watermark_token(line)
    ]
    return "\n".join(kept)


def extract_text_layer(pdf_bytes: bytes, *, denoise: bool = True) -> str:
    """Extract the PDF text layer via pdfplumber (real IO). Best-effort scavenge aid."""
    import io

    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts)
    return denoise_text_layer(text) if denoise else text
