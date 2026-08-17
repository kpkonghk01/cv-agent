"""Prompt builders for the LLM nodes. Kept separate so node files stay thin.

Prompt *wording* quality is validated by offline evals; these tests only pin the
input→output wiring (that the right context reaches the model).
"""

from __future__ import annotations

from cv_agent.domain.candidate import CandidateProfile
from cv_agent.domain.rubric import Rubric
from cv_agent.domain.screening import ScreeningReport
from cv_agent.llm.structured import Message

_BILINGUAL = (
    "The content mixes Chinese and English; keep values in their original language "
    "and do not translate technical terms."
)


def structure_messages(markdown: str, *, filename: str | None = None) -> list[Message]:
    system = (
        "You extract a structured CandidateProfile as JSON from a CV in Markdown. "
        f"{_BILINGUAL} Output ONLY JSON matching the schema; leave source_markdown empty."
    )
    user = f"CV markdown:\n\n{markdown}"
    if filename:
        user += (
            "\n\n---\nSource filename (platform exports often embed the candidate's name "
            "or role here; use it to fill fields the OCR text is missing — e.g. name — but "
            f"prefer the CV body when they disagree):\n{filename}"
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def rubric_messages(jd_text: str) -> list[Message]:
    system = (
        "You convert a job description into a screening Rubric as JSON: a list of "
        "requirements (each must_have or nice_to_have) and a role_archetype "
        "(technical | management | hybrid). Output ONLY JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Job description:\n\n{jd_text}"},
    ]


def screen_messages(profile: CandidateProfile, rubric: Rubric) -> list[Message]:
    reqs = "\n".join(f"- {r.id}: {r.text} [{r.kind.value}]" for r in rubric.requirements)
    system = (
        "You score a candidate against each rubric requirement. For each requirement "
        "id return level (met|partial|unmet) with a short evidence quote from the CV. "
        'Output ONLY JSON: {"scores": [...]}. Do NOT decide pass/reject.'
    )
    user = f"Requirements:\n{reqs}\n\nCandidate profile (JSON):\n{profile.model_dump_json()}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def brief_messages(
    profile: CandidateProfile,
    rubric: Rubric,
    report: ScreeningReport,
    *,
    minutes: int,
    interview_format: str,
    output_language: str,
    prev_scorecard: str | None,
) -> list[Message]:
    system = (
        f"You draft a pre-interview brief in {output_language} for the interviewer. "
        "Produce Markdown with: opening remarks; deep questions grouped by competency, "
        "each grounded in the CV with a follow-up ladder and 'what a good answer looks "
        f"like'; a time budget for a {minutes}-minute {interview_format} interview; and "
        "an empty scorecard. Do NOT invent the candidate's answers."
    )
    holes = ", ".join(report.reasons) or "none noted"
    parts = [
        f"Role archetype: {rubric.role_archetype.value}",
        f"Interview: {minutes} min, format {interview_format}",
        f"Screening notes (areas to probe): {holes}",
        f"Borderline: {report.borderline}",
        f"Candidate profile (JSON):\n{profile.model_dump_json()}",
    ]
    if prev_scorecard:
        parts.append(f"Previous round scorecard:\n{prev_scorecard}")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
