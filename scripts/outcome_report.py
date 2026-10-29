#!/usr/bin/env python3
"""Results report: reply/interview rates of v2-engine proposals vs the 90 days before.

Groups (one user):
  v2        proposals whose sent letter (outcomes.find_sent_letter, the link outcome sync uses)
            has cover_letters.prompt_version = 'v2', sent on or after --since
  baseline  every other proposal sent in the 90 days before --since
Each group is also broken down by jobs.match_score band (<50, 50-69, 70-84, 85+, no score).

Rates (viewed, replied, interview, hired) are over "sent": proposals still at submitted/viewed
and younger than 14 days are "pending" and proposals with no known stage are "unknown"; both
are excluded from the denominators and listed separately. A rate whose denominator is under 5
prints "n<5". Median days to first reply comes from the proposal_stage_events ledger.
Proposals with no submitted_at are skipped (counted in the output).

Usage (read-only: the transaction is READ ONLY and rolled back; nothing is written):
    cd api && doppler run --project upapply --config prd -- \\
        ./venv/bin/python ../scripts/outcome_report.py --email chris@servicevision.net
    ... --since 2026-10-20     # default: the user's first v2 cover letter
    ... --json                 # machine-readable output
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))


def parse_since(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def run(email: str, since, as_json: bool) -> int:
    from sqlalchemy import select, text

    from app.core.database import async_session_maker
    from app.models.user import User
    from app.services.outcome_report import build_report, first_v2_letter_at, load_rows, render_text

    async with async_session_maker() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        try:
            user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
            if user is None:
                print(f"no user {email}", file=sys.stderr)
                return 1
            since = since or await first_v2_letter_at(db, user.id)
            if since is None:
                print("no v2 cover letters yet; pass --since", file=sys.stderr)
                return 1
            rows, undated = await load_rows(db, user.id)
        finally:
            await db.rollback()
    report = build_report(rows, since, datetime.now(timezone.utc))
    report["skipped_undated"] = undated
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))
        print(f"Skipped {undated} proposal(s) with no submitted_at.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--since", type=parse_since, default=None,
                        help="ISO date/time; default: the user's first v2 cover letter")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.email, args.since, args.as_json)))


if __name__ == "__main__":
    main()
