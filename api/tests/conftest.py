"""Test fixtures for UpApply API tests."""
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

# Set test environment before importing app modules
os.environ["ENVIRONMENT"] = "testing"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["OPENAI_API_KEY"] = "sk-test-fake-key"

from app.core.database import Base, get_db
from app.main import app

# Use the same DATABASE_URL but target a test database, or fall back to default
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://upapply:upapply@localhost:5432/upapply_test",
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def setup_database():
    """Create test database tables once per session."""
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def client(setup_database):
    """Provide an async HTTP client with the app using the test database."""

    async def override_get_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()

    # Truncate all tables after each test for isolation
    async with test_engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE TABLE beta_feedback, feedback, screening_answers, proposals, "
            "applications, cover_letters, jobs, search_queries, memories, "
            "job_reviews, work_logs, "
            "user_profiles, users RESTART IDENTITY CASCADE"
        ))


@pytest_asyncio.fixture(loop_scope="session")
async def auth_headers(client: AsyncClient):
    """Register a test user and return auth headers."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "testpass123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def auth_headers_with_profile(client: AsyncClient, auth_headers: dict):
    """Auth headers for a user with a completed profile."""
    # Complete minimal profile setup
    await client.put(
        "/api/v1/profile",
        headers=auth_headers,
        json={
            "full_name": "Test User",
            "professional_title": "Software Developer",
            "bio": "Experienced developer",
            "skills": [
                {"name": "Python", "level": "expert", "years": 5},
                {"name": "React", "level": "intermediate", "years": 3},
                {"name": "PostgreSQL", "level": "expert", "years": 4},
            ],
            "career_goals": "Build great software",
            "setup_step": 6,
        },
    )
    await client.post("/api/v1/profile/complete-setup", headers=auth_headers)
    return auth_headers
