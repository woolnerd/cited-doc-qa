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


def test_root_endpoint_success(client):
    """Test root endpoint returns welcome message."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()

    # Check required fields
    assert "message" in data
    assert "version" in data
    assert "docs" in data
    assert "health" in data

    # Check message contains app name
    assert "Welcome to" in data["message"]

    # Check endpoints are documented
    assert data["docs"] == "/docs"
    assert data["health"] == "/health"


def test_health_check_returns_json(client):
    """Test health check returns JSON content type."""
    response = client.get("/health")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]


def test_root_returns_json(client):
    """Test root endpoint returns JSON content type."""
    response = client.get("/")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
