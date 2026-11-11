"""user_profiles.freelancer_location (migration 030): where the freelancer is, for location must-haves."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_location_round_trips_through_preferences(client: AsyncClient, auth_headers_with_profile):
    resp = await client.put("/api/v1/profile/preferences", headers=auth_headers_with_profile,
                            json={"freelancer_location": "United States"})
    assert resp.status_code == 200
    profile = (await client.get("/api/v1/profile", headers=auth_headers_with_profile)).json()
    assert profile["freelancer_location"] == "United States"
