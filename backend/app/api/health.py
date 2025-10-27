"""Health check endpoint."""

from datetime import datetime

from fastapi import APIRouter

from app.core.config import settings
from app.models.base import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health status with version and environment info
    """
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.utcnow(),
    )


@router.get("/", response_model=dict, tags=["Health"])
async def root() -> dict:
    """Root endpoint.

    Returns:
        Welcome message with API info
    """
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }
