"""GET /profile exposes generation_v2 (read-only) so the Apply panel shows v2-only controls."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_profile_reports_the_generation_flag(client: AsyncClient, auth_headers_with_profile):
    profile = (await client.get("/api/v1/profile", headers=auth_headers_with_profile)).json()
    assert profile["generation_v2"] is False
