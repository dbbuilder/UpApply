#!/usr/bin/env python3
"""Import client feedback from an Upwork profile's work history as fact candidates for review.

Copy the work-history section from the profile page (one page at a time is fine) into a text
file, then:

    api/venv/bin/python scripts/import_upwork_feedback.py feedback.txt --dry-run
    doppler run --project upapply --config prd -- env DATABASE_URL=... \\
        api/venv/bin/python scripts/import_upwork_feedback.py feedback.txt --email chris@servicevision.net

Candidates are kind client_quote, source client_feedback, so they always wait for approval in
the Facts review. Amounts, rates and hours on the page are dropped. Re-running a page is safe:
the facts service merges near-duplicates.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from app.services.upwork_feedback import parse_work_history, to_candidates  # noqa: E402


async def write(email: str, candidates) -> None:
    from sqlalchemy import select

    from app.core.database import async_session_maker
    from app.models.user import User
    from app.services.facts import upsert_candidate

    async with async_session_maker() as db:
        user_id = (await db.execute(select(User.id).where(User.email == email.lower()))).scalar_one()
        for cand in candidates:
            fact = await upsert_candidate(db, user_id, cand)
            print(f"{fact.status:9} {fact.id}  {cand.statement[:90]}")
        await db.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path, help="text copied from the profile's work history ('-' for stdin)")
    ap.add_argument("--email", help="UpApply account to add the candidates to (required unless --dry-run)")
    ap.add_argument("--include-endorsements", action="store_true", help="also add endorsement-only jobs")
    ap.add_argument("--dry-run", action="store_true", help="print the candidates; write nothing")
    args = ap.parse_args()
    text = sys.stdin.read() if str(args.file) == "-" else args.file.read_text(encoding="utf-8")
    candidates = to_candidates(parse_work_history(text), args.include_endorsements)
    if args.dry_run or not args.email:
        for c in candidates:
            print(f"- {c.statement}\n    {c.detail or ''}")
        print(f"{len(candidates)} candidate(s); nothing written")
        return
    asyncio.run(write(args.email, candidates))


if __name__ == "__main__":
    main()
