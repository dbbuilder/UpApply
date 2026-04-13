#!/bin/bash
set -e

# Transform DATABASE_URL from postgres:// to postgresql+asyncpg://
if [[ $DATABASE_URL == postgres://* ]]; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgres://|postgresql+asyncpg://|')
elif [[ $DATABASE_URL == postgresql://* ]]; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgresql://|postgresql+asyncpg://|')
fi

echo "Starting UpApply API..."

# Pre-flight: detect stale alembic_version (version stamp exists but schema is
# missing). This happens when the DB was replaced/reset but the version table
# survived, causing Alembic to skip early migrations that built the base schema.
echo "Checking migration state..."
python3 - <<'PYEOF'
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def repair_if_stale():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("""
                SELECT
                  (SELECT EXISTS(
                    SELECT 1 FROM pg_tables
                    WHERE schemaname = 'public' AND tablename = 'alembic_version'
                  )) AS av_exists,
                  (SELECT EXISTS(
                    SELECT 1 FROM pg_tables
                    WHERE schemaname = 'public' AND tablename = 'users'
                  )) AS users_exists
            """))
            av_exists, users_exists = row.fetchone()

            if av_exists and not users_exists:
                print("[start.sh] Stale alembic_version detected (version stamp present "
                      "but schema is missing). Resetting to base so all migrations "
                      "run from scratch.", flush=True)
                await conn.execute(text("DELETE FROM alembic_version"))
            elif not av_exists:
                print("[start.sh] Fresh database — no alembic_version table yet.", flush=True)
            else:
                print("[start.sh] Schema looks healthy — proceeding normally.", flush=True)
    finally:
        await engine.dispose()

asyncio.run(repair_if_stale())
PYEOF

echo "Running database migrations..."

# Run database migrations
alembic upgrade head

echo "Migrations complete. Starting server..."

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
