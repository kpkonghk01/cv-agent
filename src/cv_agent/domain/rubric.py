"""Rubric — the set of Requirements derived from one JD, plus its role archetype."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from cv_agent.domain.enums import RequirementKind, RoleArchetype


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Requirement(_Frozen):
    """A single atomic criterion extracted from a JD."""

    id: str
    text: str
    kind: RequirementKind
    category: str | None = None

    @property
    def is_must_have(self) -> bool:
        return self.kind is RequirementKind.MUST_HAVE


class Rubric(_Frozen):
    requirements: tuple[Requirement, ...] = ()
    role_archetype: RoleArchetype = RoleArchetype.HYBRID

    @property
    def must_haves(self) -> tuple[Requirement, ...]:
        return tuple(r for r in self.requirements if r.is_must_have)

    @property
    def nice_to_haves(self) -> tuple[Requirement, ...]:
        return tuple(r for r in self.requirements if not r.is_must_have)
