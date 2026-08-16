# Three-layer cache with split dedup keys

The same CV can be screened against different JDs, and OCR is the most expensive step, so a single "already processed" key would either re-OCR needlessly or wrongly skip a CV against a new JD. We split persistence into three caches with different keys:

- **Candidate Profile cache** — key `cv_hash`. The OCR→JSON result is JD-independent, so it is computed once per CV and reused across every JD.
- **ProcessedRegistry** — key `(cv_hash, jd_hash)`. Records that a CV has been screened against a JD (verdict, reasons, soft identity, report path, timestamp). Drives skip-on-rerun.
- **RubricCache** — key `jd_hash`. The JD→Rubric extraction is CV-independent, reused across every CV.

Interview Brief generation is a further unit keyed by `(cv_hash, jd_hash, interview_meta_hash)` so a second interview round with different settings produces a new artifact instead of overwriting the first.

All three live in one SQLite file behind focused ports. Dedup by content hash means a re-exported PDF (different bytes) is treated as a new CV — accepted as a v1 limitation; a soft identity (name/phone) is stored alongside for future upgrade.

## Consequences

- The future "one batch of CVs × M JDs" feature is cheap: OCR runs once, screening runs M times.
- Resume-after-interrupt falls out of idempotency; no LangGraph checkpointer needed in v1.
