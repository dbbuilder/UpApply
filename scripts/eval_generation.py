#!/usr/bin/env python3
"""Golden-set blind A/B evaluation: legacy generator vs generation v2 (spec §4.2).

Golden JSON (list of jobs where Chris's real submitted letter is known):
    [{"id": "p-123", "title": "...", "description": "...", "skills": ["..."],
      "questions": ["..."], "chris_letter": "...", "outcome": "replied",
      "proposal_id": "<proposals.id, optional>", "upwork_proposal_id": "<optional>"}]
"id", "proposal_id" and "upwork_proposal_id" are all excluded from voice-sample retrieval so
the v2 side is never conditioned on the job's own submitted letter (the answer key).

Build the golden file from scraped proposals (read-only; letters Chris wrote/edited,
responses first, one per job title):
    cd api && doppler run --project upapply --config prd -- \\
        ./venv/bin/python ../scripts/eval_generation.py build-golden \\
        --email chris@servicevision.net --out ../docs/evals/golden.json

Generate the blind packet (needs DATABASE_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY):
    cd api && doppler run --project upapply --config prd -- \\
        ./venv/bin/python ../scripts/eval_generation.py generate \\
        --email chris@servicevision.net --golden ../docs/evals/golden.json

Then fill in docs/evals/<date>/scores.csv (preferred = A, B or tie) without opening
key.json, and score it:
    ./venv/bin/python ../scripts/eval_generation.py score --run-dir ../docs/evals/<date>

Nothing is committed to the database: each job runs in its own session that is
closed without commit, so times_used and job rows are never persisted.
"""
import argparse
import asyncio
import csv
import json
import random
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

PASS_PREFERENCE = 0.75
MIN_FACTS_CITED = 2
MIN_GOLDEN_JOBS = 15


def golden_exclusions(job: dict) -> list[str]:
    """Every id the golden job's own proposal may be stored under."""
    ids = (job.get("id"), job.get("proposal_id"), job.get("upwork_proposal_id"))
    return list(dict.fromkeys(str(i) for i in ids if i))


# Facts whose provenance is the golden job's own proposal (first source or any merged source).
GOLDEN_FACTS_DELETE = (
    "DELETE FROM facts WHERE user_id = :uid AND (source_ref = ANY(:ids) OR EXISTS ("
    "SELECT 1 FROM jsonb_array_elements(sources) s WHERE s->>'source_ref' = ANY(:ids)))"
)


def _snippets(job: dict) -> list[str]:
    """Distinctive fragments of the golden job's own letter and post (for matching memories)."""
    out = []
    for text in (job.get("chris_letter"), job.get("description")):
        t = " ".join((text or "").split())
        if len(t) >= 120:
            out.append(t[40:160])
    return out


def drop_golden_examples(job: dict, past: list[dict], memories: list[dict]) -> tuple[list[dict], list[dict]]:
    """Remove the golden job's own proposal from the legacy pipeline's past-proposal examples
    and any memory that contains its letter or post, so neither side sees the answer key."""
    ids = set(golden_exclusions(job))
    snippets = _snippets(job)
    kept_past = [p for p in past if str(p.get("id")) not in ids]

    def leaks(m: dict) -> bool:
        body = " ".join(((m.get("title") or "") + " " + (m.get("content") or "")).split())
        return any(s in body for s in snippets)

    return kept_past, [m for m in memories if not leaks(m)]


def assign_sides(job_ids: list[str], seed: int) -> dict[str, dict[str, str]]:
    """Randomly place the new letter on side A or B for each job (reproducible by seed)."""
    rng = random.Random(seed)
    sides = {}
    for job_id in job_ids:
        new_is_a = rng.random() < 0.5
        sides[job_id] = {"A": "new" if new_is_a else "old", "B": "old" if new_is_a else "new"}
    return sides


def render_pairs_markdown(jobs: list[dict], outputs: dict, sides: dict) -> str:
    lines = [
        "# Cover letter eval: blind pairs",
        "",
        "For each job, read the post and the letter that was actually sent, then letters A and B.",
        "Record the better letter in scores.csv as A, B or tie. Do not open key.json until scored.",
        "",
    ]
    for job in jobs:
        job_id = job["id"]
        letter = {side: outputs[job_id][which] for side, which in sides[job_id].items()}
        lines += [
            f"## {job_id}: {job['title']}",
            "",
            "### Job post",
            "",
            job["description"].strip(),
            "",
            "### Letter actually sent (reference)",
            "",
            (job.get("chris_letter") or "").strip() or "_not available_",
            "",
            "### Letter A",
            "",
            letter["A"].strip(),
            "",
            "### Letter B",
            "",
            letter["B"].strip(),
            "",
        ]
    return "\n".join(lines)


def write_score_sheet(path, job_ids: list[str]) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["job_id", "preferred", "notes"])
        for job_id in job_ids:
            writer.writerow([job_id, "", ""])


def score(rows: list[dict], key: dict) -> dict:
    """Spec §4.2 pass bar: at least 15 golden jobs, every pair judged, new preferred in >=75%
    of pairs (ties count against), zero unsupported claims, every new draft cites >=2 facts.
    A draft whose claim check was skipped was never verified, so it fails the run too."""
    from app.services.generation.verify import CLAIM_CHECK_SKIPPED

    sides, new_meta = key["sides"], key["new_meta"]
    judged = [r for r in rows if r["preferred"].strip().upper() in ("A", "B", "TIE")]
    new_wins = sum(
        1
        for r in judged
        if r["preferred"].strip().upper() != "TIE"
        and sides[r["job_id"]][r["preferred"].strip().upper()] == "new"
    )
    preference = new_wins / len(judged) if judged else 0.0
    unsupported = sum(
        sum(1 for w in meta["warnings"] if w.startswith("Unsupported claim")) for meta in new_meta.values()
    )
    skipped = sorted(job_id for job_id, meta in new_meta.items() if CLAIM_CHECK_SKIPPED in meta["warnings"])
    thin = sorted(job_id for job_id, meta in new_meta.items() if len(meta["fact_ids_used"]) < MIN_FACTS_CITED)
    judged_ids = {r["job_id"] for r in judged}
    unjudged = sum(1 for job_id in sides if job_id not in judged_ids)
    return {
        "pairs": len(sides),
        "judged": len(judged),
        "unjudged": unjudged,
        "new_preferred": new_wins,
        "preference": round(preference, 3),
        "unsupported_claims": unsupported,
        "claim_check_skipped": skipped,
        "drafts_under_2_facts": thin,
        "passed": len(sides) >= MIN_GOLDEN_JOBS
        and unjudged == 0
        and preference >= PASS_PREFERENCE
        and unsupported == 0
        and not skipped
        and not thin,
    }


GOLDEN_AUTHORS = ("chris", "chris_edited_ai")
_OUTCOME_TIER = {"hired": 0, "interviewed": 0, "replied": 0, "viewed": 1, "declined": 3}
MIN_GOLDEN_JOB_CHARS = 200
MIN_GOLDEN_LETTER_CHARS = 300


def select_golden(rows: list[dict], n: int = 20) -> list[dict]:
    """Pick golden jobs from proposal rows: only letters Chris wrote or edited, with the job
    post and a full letter present; responses first, then newest; one per job title."""
    eligible = [
        r for r in rows
        if r.get("author") in GOLDEN_AUTHORS
        and len((r.get("job_text") or "").strip()) >= MIN_GOLDEN_JOB_CHARS
        and len((r.get("cover_letter_text") or "").strip()) >= MIN_GOLDEN_LETTER_CHARS
        and (r.get("job_title") or "").strip()
    ]
    eligible.sort(key=lambda r: (_OUTCOME_TIER.get(r.get("outcome"), 2), -_order(r.get("created_at"))))
    golden, titles = [], set()
    for r in eligible:
        title_key = r["job_title"].strip().lower()
        if title_key in titles:
            continue
        titles.add(title_key)
        golden.append({
            "id": r["id"], "proposal_id": r["id"], "upwork_proposal_id": r.get("upwork_proposal_id"),
            "title": r["job_title"].strip(), "description": r["job_text"].strip(), "skills": [],
            "questions": [a["question"] for a in (r.get("screening_answers") or [])
                          if isinstance(a, dict) and (a.get("question") or "").strip()],
            "chris_letter": r["cover_letter_text"].strip(), "outcome": r.get("outcome"),
        })
        if len(golden) == n:
            break
    return golden


def _order(value) -> float:
    return value.timestamp() if hasattr(value, "timestamp") else float(value or 0)


async def build_golden(email: str, out: Path, n: int) -> None:
    from sqlalchemy import select

    from app.core.database import async_session_maker
    from app.models.proposal import Proposal
    from app.models.user import User

    async with async_session_maker() as db:  # read-only
        user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one()
        props = (await db.execute(select(Proposal).where(
            Proposal.user_id == user.id, Proposal.author.in_(GOLDEN_AUTHORS)))).scalars().all()
        rows = [{c: getattr(p, c) for c in ("id", "upwork_proposal_id", "job_title", "job_text",
                 "cover_letter_text", "author", "outcome", "screening_answers", "created_at")}
                for p in props]
    golden = select_golden(rows, n)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(golden, indent=2))
    positives = sum(1 for g in golden if _OUTCOME_TIER.get(g["outcome"]) == 0)
    print(f"wrote {len(golden)} golden jobs ({positives} with a reply or better) to {out}")
    if len(golden) < 15:
        print("WARNING: fewer than 15 eligible jobs — scrape more proposal details first (spec §4.2)")


async def _generate_one(email: str, job: dict) -> tuple[str, object, list[dict]]:
    from sqlalchemy import select, text

    from app.core.database import async_session_maker
    from app.models.user import User, UserProfile
    from app.services.cover_letter import generate_cover_letter
    from app.services.generation import generate_application
    from app.services.job_analysis import find_relevant_proposals, run_full_analysis

    skills = job.get("skills") or []
    async with async_session_maker() as db:  # closed without commit: nothing persists
        user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one()
        profile = (await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))).scalar_one()
        analysis = await run_full_analysis(
            db=db, user_id=user.id, profile=profile, job_description=job["description"],
            job_skills=skills, job_title=job["title"],
        )
        past = await find_relevant_proposals(
            db=db, user_id=user.id, job_description=job["description"], job_skills=skills,
            limit=3, successful_only=False,
        )
        past, memories = drop_golden_examples(job, past, analysis.relevant_memories)
        old = await generate_cover_letter(
            job_title=job["title"], job_description=job["description"], job_skills=skills, budget=None,
            skill_matches=analysis.skill_matches, missing_skills=analysis.missing_skills,
            relevant_memories=memories, profile=profile, past_proposals=past,
        )
        # Facts extracted from the golden job's own proposal would hand v2 the answer key;
        # this session is never committed, so the delete only hides them for this job.
        await db.execute(text(GOLDEN_FACTS_DELETE), {"uid": user.id, "ids": golden_exclusions(job)})
        new = await generate_application(
            db=db, user=user, profile=profile, title=job["title"], description=job["description"],
            skills=skills, questions=job.get("questions") or [], credit_usage=False,
            exclude_proposal_ids=golden_exclusions(job),
        )
        reference = (job.get("chris_letter") or "").strip()
        if reference and any(
            (v.cover_letter_text or "").strip() == reference for v in new.evidence.voice_samples
        ):
            raise SystemExit(
                f"{job['id']}: its own submitted letter was retrieved as a voice sample; "
                "add its proposal_id / upwork_proposal_id to the golden file"
            )
        # Read before the rollback expires the rows.
        evidence = [{"id": str(f.id), "statement": f.statement} for f in new.evidence.facts]
        await db.rollback()
    return old, new, evidence


JOB_ATTEMPTS = 3
SAMENESS_NGRAM = 4
SAMENESS_MIN_SHARE = 0.15  # a phrase in 15%+ of a batch's openings (or closes) reads as a formula


def batch_sameness(letters: list[str], ignore: tuple[str, ...] = ()) -> list[str]:
    """Four-word phrases that recur in the opening or closing paragraph of many letters in one
    batch. One letter never shows it, but a judge reading twenty does (round 3). `ignore` holds
    fixed wording that is meant to repeat, such as the call offer."""
    from app.services.cover_letter import is_signoff_line

    floor = max(3, round(len(letters) * SAMENESS_MIN_SHARE))
    found = []
    for part, index in (("opening", 0), ("close", -1)):
        counts: Counter = Counter()
        for letter in letters:
            paras = [
                p.strip() for p in re.split(r"\n\s*\n", letter)
                if len(p.split()) >= 4 and not is_signoff_line(p.strip().splitlines()[0])
            ]
            if not paras:
                continue
            para = paras[index].lower()
            for fixed in ignore:
                para = para.replace(fixed.lower(), " | ")
            grams = set()
            for chunk in para.split("|"):
                words = re.findall(r"[a-z0-9']+", chunk)
                grams.update(" ".join(words[i:i + SAMENESS_NGRAM]) for i in range(len(words) - SAMENESS_NGRAM + 1))
            counts.update(grams)
        found += [f'{part}: "{gram}" in {n} letters' for gram, n in counts.most_common() if n >= floor]
    return found


async def generate(email: str, golden: Path, out_dir: Path, seed: int) -> None:
    from sqlalchemy.exc import DBAPIError

    from app.services.llm import LLMError

    jobs = json.loads(golden.read_text())
    outputs, new_meta = {}, {}
    # Each finished job is saved, so a dropped connection costs one job and a rerun resumes.
    partial = out_dir / "partial"
    partial.mkdir(parents=True, exist_ok=True)
    for job in jobs:
        saved = partial / f"{job['id']}.json"
        if saved.exists():
            done = json.loads(saved.read_text())
            outputs[job["id"]], new_meta[job["id"]] = done["output"], done["meta"]
            print(f"resumed {job['id']}")
            continue
        for attempt in range(JOB_ATTEMPTS):
            try:
                old, new, evidence = await _generate_one(email, job)
                break
            except (OSError, DBAPIError, LLMError) as exc:  # LLMError: the AI proxy 504s on long writer calls
                if attempt == JOB_ATTEMPTS - 1:
                    raise
                print(f"retrying {job['id']} after {type(exc).__name__}")
        outputs[job["id"]] = {"old": old, "new": new.draft.cover_letter}
        new_meta[job["id"]] = {
            "warnings": new.warnings,
            "fact_ids_used": new.draft.fact_ids_used,
            "screening_answers": new.draft.screening_answers,
            "evidence": evidence,
        }
        saved.write_text(json.dumps({"output": outputs[job["id"]], "meta": new_meta[job["id"]]}, indent=2))
        print(f"generated {job['id']} ({len(new.draft.fact_ids_used)} facts, {len(new.warnings)} warnings)")

    from app.services.generation.voice import load_voice
    from app.services.generation.writer import call_offer_wording

    offer = call_offer_wording(load_voice(email))
    sameness = {
        side: batch_sameness([o[side] for o in outputs.values()], ignore=(offer,)) for side in ("old", "new")
    }
    for side, found in sameness.items():
        print(f"{side} sameness: {len(found)} repeated phrase(s)" + "".join(f"\n  {f}" for f in found[:10]))

    job_ids = [job["id"] for job in jobs]
    sides = assign_sides(job_ids, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pairs.md").write_text(render_pairs_markdown(jobs, outputs, sides))
    write_score_sheet(out_dir / "scores.csv", job_ids)
    (out_dir / "key.json").write_text(
        json.dumps(
            {"seed": seed, "sides": sides, "new_meta": new_meta, "outputs": outputs, "sameness": sameness}, indent=2
        )
    )
    print(f"wrote {out_dir}/pairs.md, scores.csv, key.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--email", required=True)
    gen.add_argument("--golden", required=True, type=Path)
    gen.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "evals" / date.today().isoformat())
    gen.add_argument("--seed", type=int, default=20261012)
    bg = sub.add_parser("build-golden", help="Select golden jobs from scraped proposals (read-only)")
    bg.add_argument("--email", required=True)
    bg.add_argument("--out", type=Path, default=ROOT / "docs" / "evals" / "golden.json")
    bg.add_argument("--n", type=int, default=20)
    sc = sub.add_parser("score")
    sc.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "build-golden":
        asyncio.run(build_golden(args.email, args.out, args.n))
    elif args.command == "generate":
        asyncio.run(generate(args.email, args.golden, args.out_dir, args.seed))
    else:
        rows = list(csv.DictReader((args.run_dir / "scores.csv").open()))
        key = json.loads((args.run_dir / "key.json").read_text())
        print(json.dumps(score(rows, key), indent=2))


if __name__ == "__main__":
    main()
