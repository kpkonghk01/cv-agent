# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Read first

- **[AGENT.md](./AGENT.md)** — working agreements, architecture stance, decision rules, testing,
  config precedence, and deferred seams. Follow it.
- **[CONTEXT.md](./CONTEXT.md)** — the domain glossary (ubiquitous language). Use these terms exactly.
- **[docs/adr/](./docs/adr/)** — architectural decision records; read before changing structural choices.

## Non-negotiables

- Communicate in **繁體中文 (Traditional Chinese)**.
- The pipeline is a **stateful deterministic workflow**, not autonomous agents (ADR 0004).
- LLM access is **BYOK / OpenAI-compatible**; never hardcode a provider or model (ADR 0002).
- Screening verdicts must stay **reproducible and evidence-based** (rubric rule in AGENT.md).
- Follow the immutability / small-files / error-handling / input-validation rules from the user's
  global coding standards.
