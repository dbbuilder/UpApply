"""Generation v2 pipeline: brief → evidence → write → verify → at most one repair."""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.job import MAX_GEN_DESCRIPTION, MAX_GEN_SKILL_LENGTH, MAX_GEN_SKILLS, MAX_GEN_TITLE
from app.services.facts import credit_facts
from app.services.generation.brief import JobBrief, build_job_brief
from app.services.generation.evidence import Evidence, select_evidence
from app.services.generation.verify import (
    CLAIM_CHECK_SKIPPED,
    Issue,
    check_answer_rules,
    check_answer_voice,
    check_specifics,
    check_claims,
    check_rules,
    repair_note,
)
from app.services.generation.voice import load_voice
from app.services.generation.writer import Draft, write_application

NO_FACTS_WARNING = "No approved facts matched this job, so the draft has no verified specifics."
# Stored jobs (job_id path) and stored briefs never passed request validation, so the engine
# enforces the free-text limits (app.schemas.job) itself before untrusted text reaches a prompt.


@dataclass
class GenerationResult:
    draft: Draft
    brief: JobBrief
    evidence: Evidence
    warnings: list[str]
    claims_verified: bool = True  # False when the claim check was skipped for the final draft


async def _verify(
    draft: Draft,
    brief: JobBrief,
    evidence: Evidence,
    profile,
    prototype_url: Optional[str],
    answers_only: bool = False,
    voice: Optional[dict] = None,
    include_call_offer: Optional[bool] = None,
) -> list[str]:
    if answers_only:
        # The letter is discarded: only the answers are checked, and only they are audited.
        warnings = check_answer_rules(draft.screening_answers) + check_answer_voice(draft.screening_answers, voice)
        audited = draft.model_copy(update={"cover_letter": ""})
    else:
        warnings = check_rules(
            draft.cover_letter, brief, profile.preferred_closing, draft.screening_answers, voice, include_call_offer
        )
        if prototype_url and prototype_url.strip() and prototype_url.strip() not in draft.cover_letter:
            warnings.append(Issue(
                f"Prototype URL {prototype_url.strip()} is missing from the letter.", "missing_prototype_url"
            ))
        audited = draft
        warnings.extend(check_specifics(draft.fact_ids_used, evidence.facts))
    for item in draft.screening_answers:
        if not item.get("answer"):
            question = str(item.get("question", ""))
            warnings.append(Issue(f'No answer for screening question: "{question}"', "missing_answer", question))
    warnings.extend(await check_claims(audited, evidence))
    return warnings


async def _credit_usage(db: AsyncSession, user_id: str, evidence: Evidence, draft: Draft) -> None:
    used = set(draft.fact_ids_used)
    ids = [fact.id for fact in evidence.facts if str(fact.id) in used]
    # Phase 1 Task 1.4: won=False increments times_used (flush-free UPDATE in the caller's transaction)
    await credit_facts(db, ids, won=False, user_id=user_id)


async def generate_application(
    db: AsyncSession,
    user,
    profile,
    title: str,
    description: str,
    skills: list[str],
    questions: list[str],
    include_call_offer: bool = True,
    prototype_url: Optional[str] = None,
    extra_points: Optional[str] = None,
    brief: Optional[JobBrief] = None,
    credit_usage: bool = True,
    answers_only: bool = False,
    exclude_proposal_ids: Optional[list[str]] = None,
) -> GenerationResult:
    """Run the full v2 pipeline. The caller owns the transaction (commit).

    `brief`: a stored brief to reuse (per-question screening, spec §2.3) — skips the Haiku call.
    `credit_usage=False`: the letter will be discarded, so cited facts must not gain times_used
    (that would depress their win_signal in the rerank).
    `answers_only=True`: only the screening answers are used, so verify (and the repair
    decision) ignores the letter.
    `exclude_proposal_ids`: proposal ids / upwork_proposal_ids never used as voice samples
    (the eval excludes each golden job's own letter).
    """
    if brief is None:
        brief = await build_job_brief(
            (title or "")[:MAX_GEN_TITLE],
            (description or "")[:MAX_GEN_DESCRIPTION],
            [str(s)[:MAX_GEN_SKILL_LENGTH] for s in (skills or [])[:MAX_GEN_SKILLS]],
            questions,
        )
    elif len(brief.title) > MAX_GEN_TITLE or len(brief.description) > MAX_GEN_DESCRIPTION:
        brief = brief.model_copy(update={
            "title": brief.title[:MAX_GEN_TITLE], "description": brief.description[:MAX_GEN_DESCRIPTION],
        })
    evidence = await select_evidence(
        db, user.id, brief, profile.proposal_anchors, exclude_proposal_ids=exclude_proposal_ids
    )

    draft = await write_application(
        profile, brief, evidence, include_call_offer, prototype_url, extra_points, email=user.email
    )
    voice = load_voice(user.email)
    warnings = await _verify(
        draft, brief, evidence, profile, prototype_url, answers_only, voice, include_call_offer
    )

    repairable = [w for w in warnings if w != CLAIM_CHECK_SKIPPED]
    if repairable:
        draft = await write_application(
            profile, brief, evidence, include_call_offer, prototype_url, extra_points,
            repair_notes=[repair_note(w) for w in repairable], email=user.email,
        )
        warnings = await _verify(
            draft, brief, evidence, profile, prototype_url, answers_only, voice, include_call_offer
        )

    claims_verified = CLAIM_CHECK_SKIPPED not in warnings
    warnings.extend(evidence.warnings)
    if not evidence.facts:
        warnings.append(NO_FACTS_WARNING)

    if credit_usage:
        await _credit_usage(db, user.id, evidence, draft)
    return GenerationResult(
        draft=draft, brief=brief, evidence=evidence, warnings=warnings, claims_verified=claims_verified
    )
