#!/usr/bin/env python3
"""Golden-set blind A/B evaluation: legacy generator vs generation v2 (spec §4.2).

Golden JSON (list of jobs where Chris's real submitted letter is known):
    [{"id": "p-123", "title": "...", "description": "...", "skills": ["..."],
      "questions": ["..."], "chris_letter": "...", "outcome": "replied"}]

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
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

PASS_PREFERENCE = 0.75
MIN_FACTS_CITED = 2


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
    """Spec §4.2 pass bar: new preferred in >=75% of judged pairs (ties count against),
    zero unsupported claims, every new draft cites >=2 facts."""
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
    thin = sorted(job_id for job_id, meta in new_meta.items() if len(meta["fact_ids_used"]) < MIN_FACTS_CITED)
    return {
        "judged": len(judged),
        "new_preferred": new_wins,
        "preference": round(preference, 3),
        "unsupported_claims": unsupported,
        "drafts_under_2_facts": thin,
        "passed": bool(judged) and preference >= PASS_PREFERENCE and unsupported == 0 and not thin,
    }


async def _generate_one(email: str, job: dict) -> tuple[str, object]:
    from sqlalchemy import select

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
        old = await generate_cover_letter(
            job_title=job["title"], job_description=job["description"], job_skills=skills, budget=None,
            skill_matches=analysis.skill_matches, missing_skills=analysis.missing_skills,
            relevant_memories=analysis.relevant_memories, profile=profile, past_proposals=past,
        )
        new = await generate_application(
            db=db, user=user, profile=profile, title=job["title"], description=job["description"],
            skills=skills, questions=job.get("questions") or [], credit_usage=False,
        )
        await db.rollback()
    return old, new


async def generate(email: str, golden: Path, out_dir: Path, seed: int) -> None:
    jobs = json.loads(golden.read_text())
    outputs, new_meta = {}, {}
    for job in jobs:
        old, new = await _generate_one(email, job)
        outputs[job["id"]] = {"old": old, "new": new.draft.cover_letter}
        new_meta[job["id"]] = {
            "warnings": new.warnings,
            "fact_ids_used": new.draft.fact_ids_used,
            "screening_answers": new.draft.screening_answers,
        }
        print(f"generated {job['id']} ({len(new.draft.fact_ids_used)} facts, {len(new.warnings)} warnings)")

    job_ids = [job["id"] for job in jobs]
    sides = assign_sides(job_ids, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pairs.md").write_text(render_pairs_markdown(jobs, outputs, sides))
    write_score_sheet(out_dir / "scores.csv", job_ids)
    (out_dir / "key.json").write_text(
        json.dumps({"seed": seed, "sides": sides, "new_meta": new_meta, "outputs": outputs}, indent=2)
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
    sc = sub.add_parser("score")
    sc.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "generate":
        asyncio.run(generate(args.email, args.golden, args.out_dir, args.seed))
    else:
        rows = list(csv.DictReader((args.run_dir / "scores.csv").open()))
        key = json.loads((args.run_dir / "key.json").read_text())
        print(json.dumps(score(rows, key), indent=2))


if __name__ == "__main__":
    main()
