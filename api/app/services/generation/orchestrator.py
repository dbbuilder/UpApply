"""Generation v2 pipeline: brief → evidence → write → verify → at most one repair."""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.facts import credit_facts
from app.services.generation.brief import JobBrief, build_job_brief
from app.services.generation.evidence import Evidence, select_evidence
from app.services.generation.verify import CLAIM_CHECK_SKIPPED, check_claims, check_rules
from app.services.generation.writer import Draft, write_application

NO_FACTS_WARNING = "No approved facts matched this job, so the draft has no verified specifics."


@dataclass
class GenerationResult:
    draft: Draft
    brief: JobBrief
    evidence: Evidence
    warnings: list[str]


async def _verify(
    draft: Draft, brief: JobBrief, evidence: Evidence, profile, prototype_url: Optional[str]
) -> list[str]:
    warnings = check_rules(draft.cover_letter, brief, profile.preferred_closing)
    if prototype_url and prototype_url.strip() and prototype_url.strip() not in draft.cover_letter:
        warnings.append(f"Prototype URL {prototype_url.strip()} is missing from the letter.")
    for item in draft.screening_answers:
        if not item.get("answer"):
            warnings.append(f'No answer for screening question: "{item.get("question", "")}"')
    warnings.extend(await check_claims(draft, evidence))
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
) -> GenerationResult:
    """Run the full v2 pipeline. The caller owns the transaction (commit).

    `brief`: a stored brief to reuse (per-question screening, spec §2.3) — skips the Haiku call.
    `credit_usage=False`: the letter will be discarded, so cited facts must not gain times_used
    (that would depress their win_signal in the rerank).
    """
    if brief is None:
        brief = await build_job_brief(title, description, skills, questions)
    evidence = await select_evidence(db, user.id, brief, profile.proposal_anchors)

    draft = await write_application(profile, brief, evidence, include_call_offer, prototype_url, extra_points)
    warnings = await _verify(draft, brief, evidence, profile, prototype_url)

    repairable = [w for w in warnings if w != CLAIM_CHECK_SKIPPED]
    if repairable:
        draft = await write_application(
            profile, brief, evidence, include_call_offer, prototype_url, extra_points,
            repair_notes=repairable,
        )
        warnings = await _verify(draft, brief, evidence, profile, prototype_url)

    if not evidence.facts:
        warnings.append(NO_FACTS_WARNING)

    if credit_usage:
        await _credit_usage(db, user.id, evidence, draft)
    return GenerationResult(draft=draft, brief=brief, evidence=evidence, warnings=warnings)
