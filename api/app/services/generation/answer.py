"""One screening answer at a time, for the Apply panel's per-question prompt (Chris 2026-11-11).

Same voice, rules and grounding as the letter (build_writer_system, approved facts, voice samples,
the verify checks and one repair pass), but a single answer, so it is quick enough to prompt and
tweak. Context: the job brief, the cover letter being sent, the answers already in the other
boxes (including ones Chris typed himself), his one-line instruction or a tweak chip, the current
answer when revising, and his past answers to similar questions (style only).

Chris's own words (his instruction and the other answers) join the evidence as "your_words"
entries, so a detail he asks for is not stripped by the claim check as unsupported.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.embeddings import generate_embedding
from app.models.fact import Fact
from app.services.generation.brief import JobBrief, build_job_brief
from app.services.generation.evidence import Evidence, format_facts, select_evidence
from app.services.generation.verify import CLAIM_CHECK_SKIPPED, repair_note
from app.services.generation.voice import load_voice
from app.services.generation.writer import (
    Draft,
    _block,
    _bullets,
    _format_repair,
    _format_requirements,
    _format_voice_samples,
    build_writer_system,
)
from app.services.learned_rules import accepted_rules
from app.services.llm import structured_call
from app.services.untrusted import escape_brackets, neutralise

logger = logging.getLogger(__name__)

# One-tap tweaks under each answer (Chris chose these four)
TWEAKS = {
    "shorter": "Make it shorter: two or three sentences, keeping the strongest specific.",
    "specific": "Make it more specific: name the project, the problem and the outcome from the evidence.",
    "link": "Add a relevant link if the evidence or Chris's words contain one; never invent a URL.",
    "number": "Add a concrete number or result from the evidence; never invent or round one.",
}
MAX_INSTRUCTION = 600
MAX_ANSWER = 4000
MAX_LETTER = 8000
MAX_OTHER_ANSWERS = 10
MAX_PAST_ANSWERS = 3
YOUR_WORDS = "your_words"

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "fact_ids_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "fact_ids_used"],
    "additionalProperties": False,
}


@dataclass
class AnswerResult:
    answer: str
    warnings: list[str] = field(default_factory=list)
    claims_verified: bool = True
    fact_ids_used: list[str] = field(default_factory=list)


def your_words_facts(instruction: Optional[str], other_answers: Sequence[dict]) -> list[Fact]:
    """Chris's own words as transient evidence entries (never stored): his instruction and the
    answers he already has in the other boxes."""
    notes = []
    if instruction and instruction.strip():
        notes.append(instruction.strip()[:MAX_INSTRUCTION])
    for item in list(other_answers)[:MAX_OTHER_ANSWERS]:
        answer = str(item.get("answer") or "").strip()
        if answer:
            notes.append(answer[:MAX_ANSWER])
    return [Fact(id=f"yours-{i}", kind=YOUR_WORDS, statement=note) for i, note in enumerate(notes, 1)]


async def past_answers(db: AsyncSession, user_id: str, question: str) -> list[dict]:
    """The user's stored answers to the most similar questions (style reference only)."""
    try:
        embedding = await generate_embedding(question)
        rows = (await db.execute(text("""
            SELECT question, answer FROM screening_answers
            WHERE user_id = :user_id AND question_embedding IS NOT NULL
            ORDER BY question_embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """), {"user_id": user_id, "embedding": str(embedding), "limit": MAX_PAST_ANSWERS})).fetchall()
    except Exception as exc:
        logger.warning("Past answer lookup failed: %s", type(exc).__name__)
        return []
    return [{"question": r.question, "answer": r.answer} for r in rows if (r.answer or "").strip()]


def build_answer_prompt(
    profile,
    brief: JobBrief,
    question: str,
    evidence: Evidence,
    cover_letter: Optional[str],
    other_answers: Sequence[dict],
    instruction: Optional[str],
    current_answer: Optional[str],
    past: Sequence[dict],
    repair_notes=None,
) -> str:
    name = profile.full_name or "the freelancer"
    parts = [
        f"JOB TITLE:\n{_block('job_title', neutralise(brief.title, 300))}",
        f"JOB POST:\n{_block('job_post', neutralise(brief.description, 12000))}",
        f"NEEDS:\n{_block('client_needs', _bullets(brief.needs))}",
    ]
    if brief.requirements:
        parts.append(f"REQUIREMENTS (graded from the post):\n"
                     f"{_block('client_requirements', _format_requirements(brief.requirements))}")
    parts += [
        f"EVIDENCE (the only source of specifics about {name}; entries of kind \"{YOUR_WORDS}\" are "
        f"{name}'s own words and count as evidence):\n{_block('evidence', format_facts(evidence.facts))}",
        f"VOICE SAMPLES (real letters {name} sent; style only):\n{_format_voice_samples(evidence.voice_samples)}",
    ]
    if past:
        lines = "\n\n".join(f"Q: {neutralise(p['question'], 500)}\nA: {neutralise(p['answer'], 2000)}" for p in past)
        parts.append("PAST ANSWERS (" + name + "'s answers to similar questions for other jobs; style only, "
                     "never a source of facts about this job):\n" + _block("past_answers", lines))
    if cover_letter and cover_letter.strip():
        parts.append("COVER LETTER BEING SENT (do not repeat it; add something it does not say):\n"
                     + _block("cover_letter", neutralise(cover_letter, MAX_LETTER)))
    others = [o for o in other_answers if str(o.get("answer") or "").strip()][:MAX_OTHER_ANSWERS]
    if others:
        lines = "\n\n".join(f"Q: {neutralise(str(o.get('question', '')), 500)}\n"
                            f"A: {neutralise(str(o.get('answer', '')), MAX_ANSWER)}" for o in others)
        parts.append("OTHER ANSWERS ON THIS APPLICATION (stay consistent with them and do not repeat "
                     "their content):\n" + _block("other_answers", lines))
    parts.append("THE QUESTION TO ANSWER:\n" + _block("screening_question", neutralise(question, 1000)))
    if current_answer and current_answer.strip():
        parts.append("CURRENT ANSWER (revise it as instructed; keep what already works):\n"
                     + _block("current_answer", neutralise(current_answer, MAX_ANSWER)))
    if instruction and instruction.strip():
        parts.append(f"{name.upper()}'S INSTRUCTION FOR THIS ANSWER (follow it):\n"
                     + _block("instruction", escape_brackets(instruction.strip()[:MAX_INSTRUCTION])))
    parts.append(
        "TASK: write ONE screening answer to the question above, in the same voice as the letter. "
        "Not a letter: no salutation, no sign-off, no call offer. Answer what is asked first, then prove it "
        "with the evidence. 2-5 sentences unless the question or the instruction asks for more or less. "
        "The first word must not be \"I\". Return the answer and the ids of the evidence entries you used."
    )
    if repair_notes:
        parts.append(_format_repair(repair_notes))
    return "\n\n".join(parts)


async def _write(profile, email, rules, prompt: str, evidence: Evidence) -> tuple[str, list[str]]:
    data = await structured_call(
        model=settings.cover_letter_model,
        system=[{"type": "text", "text": build_writer_system(profile, email, rules),
                 "cache_control": {"type": "ephemeral"}}],
        user=prompt,
        schema=ANSWER_SCHEMA,
        effort=settings.answer_effort,
        max_tokens=4000,
        writer=True,
        api_retries=1,
    )
    allowed = {str(f.id) for f in evidence.facts}
    fact_ids = [fid for fid in dict.fromkeys(data.get("fact_ids_used", [])) if fid in allowed]
    return (data.get("answer") or "").strip(), fact_ids


async def write_answer(
    db: AsyncSession,
    user,
    profile,
    *,
    question: str,
    title: str = "",
    description: str = "",
    skills: Sequence[str] = (),
    brief: Optional[JobBrief] = None,
    cover_letter: Optional[str] = None,
    other_answers: Sequence[dict] = (),
    instruction: Optional[str] = None,
    tweak: Optional[str] = None,
    current_answer: Optional[str] = None,
) -> AnswerResult:
    """Raises EvidenceUnavailable or LLMError like generate_application; the caller maps them."""
    from app.services.generation.orchestrator import _verify  # shared answers-only checks

    if brief is None:
        brief = await build_job_brief(title or "", description or "", list(skills or []), [question])
    brief = brief.model_copy(update={"questions": [question]})
    evidence = await select_evidence(db, user.id, brief, profile.proposal_anchors)
    evidence = Evidence(
        facts=list(evidence.facts) + your_words_facts(instruction, other_answers),
        voice_samples=evidence.voice_samples, warnings=evidence.warnings,
    )
    full_instruction = " ".join(x for x in (TWEAKS.get(tweak or ""), (instruction or "").strip()) if x) or None
    past = await past_answers(db, user.id, question)
    rules = await accepted_rules(db, user.id)
    voice = load_voice(user.email)

    def prompt(repair=None):
        return build_answer_prompt(profile, brief, question, evidence, cover_letter, other_answers,
                                   full_instruction, current_answer, past, repair)

    answer, fact_ids = await _write(profile, user.email, rules, prompt(), evidence)
    draft = Draft(cover_letter="", screening_answers=[{"question": question, "answer": answer}],
                  fact_ids_used=fact_ids)
    warnings = await _verify(draft, brief, evidence, profile, None, answers_only=True, voice=voice)
    repairable = [w for w in warnings if w != CLAIM_CHECK_SKIPPED]
    if repairable:
        answer, fact_ids = await _write(profile, user.email, rules,
                                        prompt([repair_note(w) for w in repairable]), evidence)
        draft = Draft(cover_letter="", screening_answers=[{"question": question, "answer": answer}],
                      fact_ids_used=fact_ids)
        warnings = await _verify(draft, brief, evidence, profile, None, answers_only=True, voice=voice)
    return AnswerResult(
        answer=answer, warnings=[str(w) for w in warnings] + list(evidence.warnings),
        claims_verified=CLAIM_CHECK_SKIPPED not in warnings,
        fact_ids_used=[f for f in fact_ids if not f.startswith("yours-")],
    )
