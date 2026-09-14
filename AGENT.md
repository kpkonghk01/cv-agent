# AGENT.md — cv-agent working agreements

工作語言：**繁體中文**與使用者溝通。

This file captures the decisions and conventions agreed during design. The glossary
lives in [CONTEXT.md](./CONTEXT.md); architectural decisions live in [docs/adr/](./docs/adr/).

## What this project is

A **two-phase, per-candidate pipeline** (deterministic workflow, not autonomous agents —
[ADR 0004](./docs/adr/0004-deterministic-workflow-not-autonomous-agents.md)):

- **Phase 1 `screen`** — OCR → structure → score every CV (since a date), rank by weighted
  `rank_score`, write ONE ranked **Shortlist** (top N). Persists profile + full ScreeningReport.
- **Phase 2 `interview`** — for HR's accepted candidates (by CV filename or name), reload the
  cached profile + screening and draft the Interview Brief. No re-OCR, no re-screen.

Each phase's per-candidate flow is linear, so it is direct node orchestration
(`graph/phases.py`); batch fan-out + failure isolation live in `app.py`
([ADR 0005](./docs/adr/0005-two-phase-workflow.md)). The old combined `run` is gone.

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
- **Ranking (`rank_score`, 0–100)**: weighted attainment over ALL requirements
  (Met/Partial/Unmet = 1/0.5/0; must-have `must_weight` default 2, nice-to-have `nice_weight`
  default 1, both overridable in the JD meta). Phase 1 ranks within one JD and takes the top N.
  Pure ranking — the pass/reject verdict is informational, not a shortlist gate.

## Persistence (3 caches, one SQLite file — [ADR 0003](./docs/adr/0003-three-layer-cache-dedup.md))

- `ProfileCache` keyed by `cv_hash` (OCR is expensive, JD-independent).
- `RubricCache` keyed by `jd_hash`.
- `ScreeningCache` keyed by `(cv_hash, jd_hash)` — the full ScreeningReport, so Phase 2 reloads
  Phase 1's scoring without re-running the LLM.
- `ProcessedRegistry` keyed by `(cv_hash, jd_hash)` (legacy verdict summary; superseded by the
  ScreeningCache in the two-phase flow).
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

`Source` (CV & JD; LocalFolder **or GoogleDrive**, `CV_SOURCE=local|gdrive`) · SQLite caches
(Profile/Rubric/Screening/Processed) · `ReportSink` (LocalFolder → GoogleDrive) ·
`Notifier` (NullNotifier → Slack, v1 no-op). Text-layer scavenge (pdfplumber) supplements OCR.

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

Google Drive **sink** (source is done) · Slack notifier · vision-LLM `--ocr-fallback` (image-only
CVs; text-layer scavenge already covers the common image-name gap) · `M` JDs per run ·
post-interview evaluation (ingest scorecards; `--prev-scorecard` is the input half).

LangGraph is no longer used (the two-phase flows are linear — ADR 0005); the dependency remains
so a checkpointer/HITL graph can be reintroduced if a phase ever needs branching or resumability.

## Operational notes (learned from real runs)

Hard-won field notes — read before debugging an LLM run or blaming a model.

- **Structured output on local/reasoning models needs BOTH levers.** Reasoning models (Qwen3)
  deliberate in the answer ("我们需要…推断 schema？") and hit the token cap with empty content.
  Two fixes together: (1) `response_format=json_object` on the structured nodes (grammar stops the
  rambling); (2) inject the Pydantic JSON Schema into the prompt (json mode only forces *valid*
  JSON, not the right *fields* — without the schema the model returns `{}`). Both live in the code
  now; don't remove either.
- **Disabling "thinking" via `/no_think` or `chat_template_kwargs.enable_thinking=false` did NOT
  work on vMLX** for these models. `json_object` was the only lever that actually stopped the
  runaway deliberation. `LLM_DISABLE_THINKING` is kept (harmless) but is not what fixes it.
- **The free-form interview node needs neither** — writing a document is natural for the model, so
  it produces a clean brief with no deliberation. Never put `json_mode` on the interview node.
- **Diagnose by streaming first.** When a call returns empty, stream the raw tokens to *see* what
  it generates before assuming the model is bad — and check whether the prompt gives the model what
  it needs (e.g. the schema). Blind black-box re-runs waste minutes each.
- **Screening verdicts vary by model.** Same CV + JD: the aligned model scored one must-have
  `unmet` (→ reject); the crack model scored it `partial` (→ borderline pass). The rule is
  reproducible; the per-Requirement scores are not, across models. In production, pin one model
  and/or human-review borderlines. Evidence quotes make the divergence explainable.
- **`max_tokens` is output-only** (separate from the 262k context). 8192 comfortably fit a full
  interview brief (`finish_reason=stop`). A long JD / very senior role may need more.
- **Red herring:** `Force-killed llamacpp (pid …)` in logs is Marker's Surya GGUF OCR cleaning up
  its own worker — **not** the LLM server crashing.
- **Speed reality:** a 27B on Apple Silicon runs ~10 tok/s and vMLX serves one request at a time
  (`max_num_seqs=1`), so a CV's four sequential LLM calls take several minutes. Sequential-first is
  fine; a smaller model is the lever if throughput matters.
- **Marker force-OCR bypasses the boss直聘 watermark/poisoned-text layer** — validated on a real CV
  (clean bilingual markdown, two columns linearised).
- **OCR engine comparison (measured on a real boss直聘 CV).** Marker beats the alternatives for
  these CVs: *pdfplumber* (text layer) is complete — it even keeps an image-rendered name — but the
  poisoned text layer buries everything in ~600 single-char watermark fragments + hex tokens;
  *Tesseract* (the pdf skill's scanned path) rasterises like Marker but mangles Chinese
  (专业技能→"suisse", 学历→"ZF i") and transcribes the visible watermark. Marker is clean, accurate,
  and layout-aware; its only gap is dropping image-classified regions (a name baked into an image).
- **Text-layer scavenge recovers Marker's gap cheaply.** `ocr/extract_text_layer` (pdfplumber,
  denoised) + the CV filename are fed to the structuring LLM as *secondary* hints — the clean OCR
  body wins on conflict. This is the lightweight alternative to a vision `--ocr-fallback`, which is
  now only needed for genuinely image-only CVs.
