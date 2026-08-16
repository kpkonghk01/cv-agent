# Stateful deterministic workflow, not autonomous agents

The project is framed as "multi-agent", but the work is a mostly-linear per-candidate pipeline. We deliberately build it as a **stateful deterministic workflow** (LangGraph used as a workflow engine) with a small number of **structured LLM nodes**, rather than autonomous agents that loop and use tools freely.

## Why

- Hiring pass/reject must be **reproducible, auditable, and defensible** (bias/compliance risk; CV screening is high-risk under regimes like the EU AI Act). Autonomous, tool-looping agents make outputs non-reproducible.
- The Filter is therefore an **evidence-based rubric scorer**, not a black-box judge: it extracts per-Requirement evidence and a deterministic rule decides the verdict (see the screening rule in AGENT.md).
- LangGraph earns its place through state, retries, fan-out, and a future human-in-the-loop/checkpointer seam — not through agent autonomy.

## Considered Options

- **Autonomous multi-agent (tool-using, looping).** Rejected: non-reproducible verdicts, harder to audit, unnecessary for a linear pipeline.
- **Plain Python pipeline (no LangGraph).** Viable, but loses the state/fan-out/HITL seams we want for later.

A future reader wondering "why isn't this agentic?" should read this as intentional.
