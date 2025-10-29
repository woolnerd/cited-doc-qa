"""Tests for health check endpoint."""

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_check_success(client):
    """Test health check endpoint returns healthy status."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Check required fields
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data

    # Check version format (should be semver or similar)
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0

    # Check environment is valid
    assert data["environment"] in ["development", "staging", "production"]

    # Check timestamp is ISO format
    assert isinstance(data["timestamp"], str)
    assert "T" in data["timestamp"]  # ISO format has T separator


def test_health_check_returns_json(client):
    """Test health check returns JSON content type."""
    response = client.get("/health")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
