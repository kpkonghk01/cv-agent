# Two-phase workflow: screen (shortlist) then interview (accepted)

With a large CV inflow, running every candidate straight through to an interview brief is
wasteful — HR only interviews a few. We split the pipeline into two commands:

- **`screen`** scores every CV (since a date) and writes ONE ranked **Shortlist** (top N by a
  weighted 0–100 `rank_score`). It persists the profile and the full `ScreeningReport`.
- **`interview`** takes the candidates HR actually booked (by CV filename or name), reloads the
  cached profile + screening, and drafts the interview brief — no re-OCR, no re-score.

The combined `run` command is removed.

## Consequences

- Ranking is **pure** (top N by `rank_score`); the pass/reject verdict is informational, not a
  gate. Weights (must-have vs nice-to-have) default 2×/1× and are overridable per JD.
- A new `ScreeningCache` keyed by `(cv_hash, jd_hash)` persists the full report so Phase 2 needs
  no LLM re-run. Un-screened CVs named in Phase 2 are OCR'd on demand only after a confirm prompt.
- **LangGraph is dropped from the per-candidate flow.** Each phase is now linear (no pass→interview
  branch within a single pass), so it is direct node orchestration (`graph/phases.py`) rather than
  a `StateGraph`. Batch fan-out + failure isolation stay in `app.py`. This does not change the
  "deterministic workflow, not autonomous agents" stance of ADR 0004; the langgraph dependency is
  kept so a checkpointer/HITL graph can return if a phase later needs branching or resumability.
