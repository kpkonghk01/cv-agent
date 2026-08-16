# OCR via Marker (force-OCR), LLM does structuring not OCR

CVs are exported from platforms like boss直聘 and carry a poisoned text layer (invisible watermarks / garbage text meant to defeat copy-paste and analysis) and sometimes a two-column layout. We convert each CV with **Marker in force-OCR mode**, which rasterises the page and re-OCRs the pixels — bypassing the poisoned text layer — and uses layout detection to recover reading order across columns. Marker outputs Markdown; a downstream **LLM node** then structures that Markdown into JSON. The LLM is **not** used for OCR.

## Considered Options

- **Marker → Markdown → LLM → JSON (chosen).** Deterministic, offline, cheap, mature at two-column/table handling. Beats the watermark problem via force-OCR.
- **Vision LLM does OCR + structuring directly** (rasterise pages → VL model). Reuses the BYOK LLM pipeline but is costlier, less reproducible, and token-heavy per page. Kept as an optional fallback when Marker confidence is low.

## Consequences

- The locally hosted / BYOK main LLM only needs to be a strong **bilingual (CN/EN) text** instruct model — vision capability is not required for the main path.
- Marker adds a heavy dependency (multi-GB models); runs on Apple Silicon via MPS at moderate speed.
