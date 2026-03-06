#!/bin/bash
set -e

echo "=== UpApply API Startup ==="
echo "DATABASE_URL prefix: ${DATABASE_URL:0:20}..."
echo "PORT: ${PORT:-8000}"
echo "ENVIRONMENT: ${ENVIRONMENT:-not_set}"
echo "OPENAI_API_KEY present: $([ -n "$OPENAI_API_KEY" ] && echo yes || echo NO)"
echo "SECRET_KEY present: $([ -n "$SECRET_KEY" ] && echo yes || echo NO)"

# Transform DATABASE_URL from postgres:// to postgresql+asyncpg://
if [[ $DATABASE_URL == postgres://* ]]; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgres://|postgresql+asyncpg://|')
elif [[ $DATABASE_URL == postgresql://* ]]; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgresql://|postgresql+asyncpg://|')
fi

echo "Transformed DATABASE_URL prefix: ${DATABASE_URL:0:30}..."
echo "Running database migrations..."

# Run database migrations
if ! alembic upgrade head 2>&1; then
    echo "ALEMBIC FAILED - checking current version..."
    alembic current 2>&1 || true
    exit 1
fi

echo "Migrations complete. Starting server..."

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
