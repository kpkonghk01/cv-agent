# AGENT.md — cv-agent working agreements

工作語言：**繁體中文**與使用者溝通。

This file captures the decisions and conventions agreed during design. The glossary
lives in [CONTEXT.md](./CONTEXT.md); architectural decisions live in [docs/adr/](./docs/adr/).

## What this project is

A **per-candidate pipeline** (not autonomous agents — [ADR 0004](./docs/adr/0004-deterministic-workflow-not-autonomous-agents.md)):
each CV flows independently through **OCR → structuring → screening → (if pass) interview prep**.
LangGraph is used as a stateful workflow engine, with a small number of structured LLM nodes.

## Architecture stance

- **LLM nodes produce structured output**, enforced by Pydantic schema + validation + retry.
  Never trust a single model's raw JSON ([ADR 0002](./docs/adr/0002-byok-openai-compatible-model-agnostic.md)).
- **BYOK, model-agnostic.** Every node targets an OpenAI-compatible `(base_url, api_key, model)`.
  One default + optional per-node overrides. Local (vMLX/mlx-lm) and cloud are interchangeable.
- **OCR is Marker with force-OCR** ([ADR 0001](./docs/adr/0001-marker-ocr-llm-structuring.md)); the LLM
  structures Marker's markdown, it does not do OCR. Vision-LLM OCR is a reserved `--ocr-fallback` seam.

## The four LLM nodes

1. `STRUCTURE_CV` — Marker markdown → `CandidateProfile` (JD-independent; keeps `source_markdown`).
2. `JD_RUBRIC` — JD (+ meta) → `Rubric` (Requirements + auto-detected `RoleArchetype`).
3. `SCREEN` — `CandidateProfile` + `Rubric` → `ScreeningReport`.
4. `INTERVIEW` — passing candidate → `Interview Brief`.

## Screening decision rule (deterministic, loose default)

- Each Requirement scored `Met | Partial | Unmet` with evidence quote + confidence.
- **Reject iff any must-have is `Unmet`.** A `Partial` must-have **passes** (loose default;
  `--strict` / `screening_strictness: strict` requires `Met`).
- nice-to-have hits become a score used only for ranking + a `borderline` flag (still a pass).
- `job_hopping` is **advisory**, never an auto-reject unless a JD lists stability as a Requirement.

## Persistence (3 caches, one SQLite file — [ADR 0003](./docs/adr/0003-three-layer-cache-dedup.md))

- `ProfileCache` keyed by `cv_hash` (OCR is expensive, JD-independent).
- `ProcessedRegistry` keyed by `(cv_hash, jd_hash)` (skip-on-rerun; stores verdict/soft-identity/path).
- `RubricCache` keyed by `jd_hash`.
- Interview Brief unit = `(cv_hash, jd_hash, interview_meta_hash)` → never overwrite across rounds.
- Dedup by content hash; re-exported PDF = new CV (accepted v1 limitation).

## Output boundary

- **Screening Report**: SQLite only, never to the sink.
- **Reject Report**: default = full screening content via `ReportSink`; `--concise-reject-report`
  = summary; `--no-reject-report` = off (fade-out path full→concise→none).
- **Interview Brief**: via `ReportSink`, one `.md` per `(cv, jd, interview_meta)`.
  Filenames verdict-prefixed: `pass__…__interview-brief.md`, `reject__…__reject-report.md`.
- End-of-run terminal summary (counts + reject reasons + error/manual-review lists) is always on.

## Modular ports (adapters swap without touching flow)

`Source` (CV & JD; LocalFolder → GoogleDrive) · `ProcessedRegistry`/`RubricCache`/`ProfileCache`
(SQLite → …) · `ReportSink` (LocalFolder → GoogleDrive) · `Notifier` (NullNotifier → Slack, v1 no-op).

## Config precedence

**CLI > JD meta (`<jd>.meta.yaml`) > `.env` > built-in defaults.**

## Robustness

- Per-candidate failure isolation: OCR/JSON failure after retries → mark `error`, skip, continue.
- Retries: LLM structured calls validate + retry (~2); OCR retries once.
- `MAX_CONCURRENCY=1` (sequential first); fan-out reserved.
- Resume via SQLite idempotency; no checkpointer in v1.
- Multi-page CVs (2–5 pp) are normal: handle cross-page order, repeated header/footer noise,
  per-page confidence, and generous OCR timeouts.

## Testing

- **80% coverage gate** on deterministic core (hashing, dedup keys, decision rule, config/CLI
  precedence, YAML validation, filename routing, SQLite ports via in-memory, sink routing) **and**
  LLM nodes' parse/validate/retry contract with a **mocked client + fixtures**. TDD the core.
- Marker OCR: one `@pytest.mark.slow` smoke test, excluded from the gate.
- **LLM semantics → offline evals** on a golden CV set (may use the local model); not in the gate.

## Deferred (seams left in place)

Google Drive source/sink · Slack notifier · vision-LLM `--ocr-fallback` · LangGraph checkpointer ·
`M` JDs per run · **Phase 2**: ingest interview scorecards → post-interview evaluation
(v1 already accepts `--prev-scorecard` as the input half of that seam).
