"""JD_RUBRIC node: JD text → Rubric (with sequential ids and optional role override)."""

from __future__ import annotations

from cv_agent.domain.enums import RoleArchetype
from cv_agent.domain.rubric import Rubric
from cv_agent.llm.structured import LLMClient, structured_call
from cv_agent.nodes.prompts import rubric_messages


def jd_to_rubric(
    client: LLMClient,
    jd_text: str,
    *,
    role_override: RoleArchetype | None = None,
    max_retries: int = 2,
) -> Rubric:
    """Derive the Rubric; normalise Requirement ids to r1..rn for stable referencing."""
    rubric = structured_call(client, Rubric, rubric_messages(jd_text), max_retries=max_retries)
    reqs = tuple(
        r.model_copy(update={"id": f"r{i + 1}"}) for i, r in enumerate(rubric.requirements)
    )
    return rubric.model_copy(
        update={
            "requirements": reqs,
            "role_archetype": role_override or rubric.role_archetype,
        }
    )
