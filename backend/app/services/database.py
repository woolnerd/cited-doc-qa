"""PostgreSQL database service using asyncpg."""

from typing import Any

import asyncpg

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DatabaseService:
    """PostgreSQL database service for RAG operations."""

    def __init__(self):
        """Initialize database service."""
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create connection pool to PostgreSQL."""
        try:
            self.pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                database=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            logger.info(
                f"Connected to PostgreSQL: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from PostgreSQL")

    async def execute(self, query: str, *args: Any, timeout: float = 60.0) -> str:
        """Execute a query that doesn't return rows (INSERT, UPDATE, DELETE).

        Args:
            query: SQL query to execute
            *args: Query parameters
            timeout: Query timeout in seconds

        Returns:
            Status message from database

        Raises:
            RuntimeError: If pool not initialized
            Exception: If query execution fails
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            result: str = await conn.execute(query, *args, timeout=timeout)
            return result

    async def fetch(
        self, query: str, *args: Any, timeout: float = 60.0
    ) -> list[dict[str, Any]]:
        """Fetch multiple rows from database.

        Args:
            query: SQL query to execute
            *args: Query parameters
            timeout: Query timeout in seconds

        Returns:
            List of row dictionaries

        Raises:
            RuntimeError: If pool not initialized
            Exception: If query execution fails
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args, timeout=timeout)
            return [dict(row) for row in rows]

    async def fetchrow(
        self, query: str, *args: Any, timeout: float = 60.0
    ) -> dict[str, Any] | None:
        """Fetch single row from database.

        Args:
            query: SQL query to execute
            *args: Query parameters
            timeout: Query timeout in seconds

        Returns:
            Row dictionary or None if no results

        Raises:
            RuntimeError: If pool not initialized
            Exception: If query execution fails
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args, timeout=timeout)
            return dict(row) if row else None

    async def fetchval(
        self, query: str, *args: Any, column: int = 0, timeout: float = 60.0
    ) -> Any:
        """Fetch single value from database.

        Args:
            query: SQL query to execute
            *args: Query parameters
            column: Column index to return (default 0)
            timeout: Query timeout in seconds

        Returns:
            Single value from query result

        Raises:
            RuntimeError: If pool not initialized
            Exception: If query execution fails
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column, timeout=timeout)


# Global database instance
db = DatabaseService()
