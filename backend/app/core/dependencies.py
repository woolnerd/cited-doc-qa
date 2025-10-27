"""FastAPI dependencies for dependency injection."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from supabase import Client, create_client

from app.core.config import settings
from app.core.logging import get_logger

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


# Type alias for dependency injection
SupabaseClient = Annotated[Client, Depends(get_supabase_client)]
