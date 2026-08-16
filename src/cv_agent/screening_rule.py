"""The deterministic screening rule (ADR 0004, AGENT.md).

Pure function: given a Rubric and per-Requirement scores, decide the verdict with a
reproducible rule — **reject only if a must-have is Unmet** (loose default: a Partial
must-have passes). nice-to-have hits become a ranking score and a borderline flag.
"""

from __future__ import annotations

from collections.abc import Iterable

from cv_agent.domain.enums import ScoreLevel, Strictness, Verdict
from cv_agent.domain.rubric import Rubric
from cv_agent.domain.screening import RequirementScore, ScreeningReport

_WEIGHT = {ScoreLevel.MET: 1.0, ScoreLevel.PARTIAL: 0.5, ScoreLevel.UNMET: 0.0}


def _must_have_ok(level: ScoreLevel, strictness: Strictness) -> bool:
    if strictness is Strictness.STRICT:
        return level is ScoreLevel.MET
    return level is not ScoreLevel.UNMET  # loose: Partial passes


def decide_verdict(
    rubric: Rubric,
    scores: Iterable[RequirementScore],
    *,
    strictness: Strictness = Strictness.LOOSE,
    borderline_threshold: float = 0.5,
) -> ScreeningReport:
    """Score → verdict. Missing scores default to ``Unmet`` (defensive)."""
    by_id = {s.requirement_id: s for s in scores}

    # Order scores by the rubric; fill gaps with an explicit Unmet.
    ordered = tuple(
        by_id.get(req.id, RequirementScore(requirement_id=req.id, level=ScoreLevel.UNMET))
        for req in rubric.requirements
    )
    level_of = {s.requirement_id: s.level for s in ordered}

    failed_must = [r for r in rubric.must_haves if not _must_have_ok(level_of[r.id], strictness)]
    verdict = Verdict.REJECT if failed_must else Verdict.PASS

    nice = rubric.nice_to_haves
    nice_score = (
        1.0
        if not nice
        else round(sum(_WEIGHT[level_of[r.id]] for r in nice) / len(nice), 4)
    )

    partial_must = [r for r in rubric.must_haves if level_of[r.id] is ScoreLevel.PARTIAL]
    borderline = verdict is Verdict.PASS and (
        nice_score < borderline_threshold or bool(partial_must)
    )

    reasons = _reasons(verdict, failed_must, partial_must, nice_score, borderline)
    return ScreeningReport(
        scores=ordered,
        verdict=verdict,
        borderline=borderline,
        score=nice_score,
        reasons=reasons,
    )


def _reasons(verdict, failed_must, partial_must, nice_score, borderline) -> tuple[str, ...]:
    if verdict is Verdict.REJECT:
        return tuple(f"Unmet must-have: {r.text}" for r in failed_must)
    reasons = ["All must-have requirements satisfied."]
    if partial_must:
        reasons.append(
            "Weak on must-haves: " + ", ".join(r.text for r in partial_must)
        )
    if borderline:
        reasons.append(f"Borderline (nice-to-have strength {nice_score}).")
    return tuple(reasons)
