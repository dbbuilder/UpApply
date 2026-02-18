"""Tests for profile CRUD operations via API."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_profile_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/profile")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_default(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/profile", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["setup_completed"] is False


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient, auth_headers: dict):
    response = await client.put(
        "/api/v1/profile",
        headers=auth_headers,
        json={
            "full_name": "Test User",
            "professional_title": "Developer",
            "bio": "I build things",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Test User"
    assert data["professional_title"] == "Developer"


@pytest.mark.asyncio
async def test_update_goals(client: AsyncClient, auth_headers: dict):
    response = await client.put(
        "/api/v1/profile/goals",
        headers=auth_headers,
        json={
            "career_goals": "Build great products",
            "skills_to_highlight": ["Python", "React"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["career_goals"] == "Build great products"
    assert "Python" in data["skills_to_highlight"]


@pytest.mark.asyncio
async def test_update_preferences(client: AsyncClient, auth_headers: dict):
    response = await client.put(
        "/api/v1/profile/preferences",
        headers=auth_headers,
        json={
            "preferred_project_types": ["web_app", "api"],
            "preferred_team_size": "small",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "web_app" in data["preferred_project_types"]


@pytest.mark.asyncio
async def test_update_dealbreakers(client: AsyncClient, auth_headers: dict):
    response = await client.put(
        "/api/v1/profile/dealbreakers",
        headers=auth_headers,
        json={
            "avoid_keywords": ["crypto", "blockchain"],
            "minimum_budget": 500,
            "minimum_hourly_rate": 50,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "crypto" in data["avoid_keywords"]
    assert data["minimum_budget"] == 500


@pytest.mark.asyncio
async def test_update_pricing(client: AsyncClient, auth_headers: dict):
    response = await client.put(
        "/api/v1/profile/pricing",
        headers=auth_headers,
        json={
            "hourly_rate_min": 40,
            "hourly_rate_max": 100,
            "hourly_rate_preferred": 75,
            "hours_per_week_available": 30,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["hourly_rate_preferred"] == 75


@pytest.mark.asyncio
async def test_complete_setup(client: AsyncClient, auth_headers: dict):
    # Set up profile first
    await client.put(
        "/api/v1/profile",
        headers=auth_headers,
        json={"full_name": "Test User", "professional_title": "Dev"},
    )
    response = await client.post(
        "/api/v1/profile/complete-setup",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["setup_completed"] is True

    # Verify user now has_profile
    me_response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_response.json()["has_profile"] is True
