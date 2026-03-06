#!/bin/bash
set -e

# Transform DATABASE_URL from postgres:// to postgresql+asyncpg://
if [[ $DATABASE_URL == postgres://* ]]; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgres://|postgresql+asyncpg://|')
elif [[ $DATABASE_URL == postgresql://* ]]; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgresql://|postgresql+asyncpg://|')
fi

echo "Starting UpApply API..."
echo "Running database migrations..."

# Run database migrations
alembic upgrade head

echo "Migrations complete. Starting server..."

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
