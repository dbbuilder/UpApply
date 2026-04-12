"""Render cron entry point for the daily job discovery run.

Designed to be invoked as:
  python -m agent.run_discovery

For each active user with a completed profile, this script:
  1. Mints a service JWT for the user
  2. Runs JobDiscoveryAgent
  3. Logs results

Render cron schedule (in render.yaml):
  schedule: "0 13 * * *"   # 6am PT (UTC-7 in summer / UTC-8 in winter)
  command: "python -m agent.run_discovery"

Environment variables required:
  DATABASE_URL      — PostgreSQL connection string
  ANTHROPIC_API_KEY — Anthropic API key
  SECRET_KEY        — same JWT secret as the API
  API_BASE_URL      — base URL of the UpApply API (default: http://localhost:8000)
  OPENAI_API_KEY    — needed by /jobs/analyze internally
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

# Allow running as a module from the api/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from agent.job_discovery import JobDiscoveryAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_discovery")

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
ALGORITHM = "HS256"
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
TOKEN_TTL_HOURS = 2


def _mint_service_jwt(user_id: str) -> str:
    """Create a short-lived JWT for a user, same format as the auth service."""
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    payload = {"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

async def _get_active_user_ids(session: AsyncSession) -> list[str]:
    """Return IDs of users that have a completed profile (setup_complete=True).

    A user is considered active if:
      - their account is active
      - they have a user_profile row with setup_complete = true
      - they have at least one active search_query (so the agent has something to search)
    """
    result = await session.execute(
        text("""
            SELECT DISTINCT u.id
            FROM users u
            JOIN user_profiles up ON up.user_id = u.id
            JOIN search_queries sq ON sq.user_id = u.id
            WHERE u.is_active = true
              AND up.setup_complete = true
              AND sq.active = true
            ORDER BY u.id
        """)
    )
    return [row[0] for row in result.fetchall()]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

async def run() -> None:
    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set — aborting")
        sys.exit(1)

    # Make sure asyncpg driver is used
    db_url = DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user_ids = await _get_active_user_ids(session)

    await engine.dispose()

    if not user_ids:
        logger.info("No active users with completed profiles — nothing to do")
        return

    logger.info("Starting discovery run for %d user(s): %s", len(user_ids), user_ids)

    total_queued = 0
    total_errors = 0

    for user_id in user_ids:
        token = _mint_service_jwt(user_id)
        agent = JobDiscoveryAgent(api_base=API_BASE_URL, token=token)

        try:
            result = await agent.run(user_id=user_id)
            total_queued += result.jobs_queued
            total_errors += len(result.errors)
            logger.info(
                "User %s: fetched=%d skipped=%d scored=%d queued=%d errors=%d",
                user_id,
                result.jobs_fetched,
                result.jobs_skipped_duplicate,
                result.jobs_scored,
                result.jobs_queued,
                len(result.errors),
            )
            if result.errors:
                for err in result.errors:
                    logger.warning("  error: %s", err)
        except Exception as exc:
            logger.error("Discovery failed for user %s: %s", user_id, exc, exc_info=True)
            total_errors += 1

    logger.info(
        "Discovery run complete. total_queued=%d total_errors=%d",
        total_queued, total_errors,
    )


if __name__ == "__main__":
    asyncio.run(run())
