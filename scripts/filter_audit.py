#!/usr/bin/env python3
"""Filter audit: why one user's jobs were skipped, and whether the pre-filter threw out good jobs.

Sections (one user, items created or reviewed in the last --days):
  user skips   rejected queue items counted by canonical skip reason
               (app/services/skip_reasons.py; legacy free text maps to "other" unless it is one
               of the extension's old labels), plus the most common "other" texts
  pre-filter   for each automatic rule (pre_filter:too_old, pre_filter:blocked_country,
               pre_filter:budget_too_low, pre_filter:hourly_top_too_low, pre_filter:avoid_keyword,
               pre_filter:score_cap_reached): items blocked, how many were scored via
               score-anyway and their score distribution, and how many blocked items have an
               ai_score >= 70. A rule that blocked any job scoring >= 70 is flagged.
A percentage whose denominator is under 5 prints "n<5".

Usage (read-only: the transaction is READ ONLY and rolled back; nothing is written):
    cd api && doppler run --project upapply --config prd -- \\
        ./venv/bin/python ../scripts/filter_audit.py --email chris@servicevision.net
    ... --days 30              # window (default 90)
    ... --json                 # machine-readable output
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))


async def run(email: str, days: int, as_json: bool) -> int:
    from sqlalchemy import select, text

    from app.core.database import async_session_maker
    from app.models.user import User
    from app.services.filter_audit import build_audit, load_items, render_text

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        try:
            user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
            if user is None:
                print(f"no user {email}", file=sys.stderr)
                return 1
            items = await load_items(db, user.id, now - timedelta(days=days))
        finally:
            await db.rollback()
    report = build_audit(items, days, now)
    print(json.dumps(report, indent=2) if as_json else render_text(report))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--days", type=int, default=90, help="window in days (default 90)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.email, args.days, args.as_json)))


if __name__ == "__main__":
    main()
