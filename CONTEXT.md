# CV Agent

A pipeline that screens candidate CVs against a job description and drafts interview material for the candidates who pass. Each candidate flows through the pipeline independently (OCR → screening → interview prep).

## Language

**Candidate**:
The person a CV represents and whom the pipeline evaluates.
_Avoid_: applicant, 應徵者 (mixing)

**CV**:
The source résumé document (PDF) belonging to one Candidate, read from a Source.
_Avoid_: resume, profile

**Candidate Profile**:
The structured JSON extracted from a CV after OCR (via Marker) and LLM structuring. JD-independent, so it is cached by CV content hash and reused across JDs. Both the Filter and Interviewer steps consume it.
_Avoid_: parsed CV, resume JSON

**JD** (Job Description):
The role specification a single run screens every CV against. Exactly one JD per run.
_Avoid_: role spec, posting

**Requirement**:
A single atomic criterion extracted from a JD, classified as must-have or nice-to-have.

**Rubric**:
The full set of Requirements derived from one JD, together with the scoring rules used to decide pass/reject.

**Role Archetype**:
The interviewing style a JD implies — `technical`, `management`, or `hybrid` — auto-detected during JD→Rubric and overridable in the JD meta file. Steers how the Interviewer weights depth vs breadth.

**Interview Brief**:
The Interviewer's deliverable for one passing Candidate: a pre-interview working document (opening remarks, competency-grouped questions with follow-up ladders grounded in CV/screening evidence, time allocation, and an empty scorecard). It is produced *before* the interview and contains no candidate answers.
_Avoid_: 最終報告 (ambiguous), final report, interview plan

**Job-hopping signal**:
An advisory indicator on a Candidate Profile (average tenure, count of short stints) derived where possible from work-experience dates. Informational for the Interviewer; never an automatic reject unless a JD explicitly lists stability as a Requirement.
_Avoid_: flight risk, loyalty score

**Screening Report**:
The Filter step's raw output for one Candidate: per-Requirement evidence and score, an overall pass/reject verdict, and reasons. Internal only — persisted in SQLite, never written to the output sink.
_Avoid_: filter result, review

**Reject Report**:
The exported artifact for a rejected Candidate. Defaults to the full Screening Report content; `--concise-reject-report` emits a summary; `--no-reject-report` suppresses it (a full→concise→none fade-out path). Pass candidates never get a standalone screening report — theirs is folded into the Interview Brief recap.
_Avoid_: rejection notice

**Source**:
An abstraction that lists and reads documents (CVs or JD). Backed by a local folder now, Google Drive or others later. The same port serves both CV and JD reading.
_Avoid_: loader, reader, provider
