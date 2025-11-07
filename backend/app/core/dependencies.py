"""FastAPI dependencies for dependency injection."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from supabase import Client, create_client

from app.core.config import settings
from app.core.logging import get_logger
from app.services.database import DatabaseService, db

logger = get_logger(__name__)


def get_supabase_client() -> Client:
    """Get Supabase client instance.

    Returns:
        Configured Supabase client

    Raises:
        HTTPException: If Supabase client cannot be created
    """
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return client
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        ) from e


def get_database() -> DatabaseService:
    """Get PostgreSQL database service instance.

    Returns:
        DatabaseService instance

    Raises:
        HTTPException: If database not connected
    """
    if not db.pool:
        logger.error("Database pool not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )
    return db


# Type aliases for dependency injection
SupabaseClient = Annotated[Client, Depends(get_supabase_client)]
Database = Annotated[DatabaseService, Depends(get_database)]
