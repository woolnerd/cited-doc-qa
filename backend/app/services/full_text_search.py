"""Full-text search service using PostgreSQL text search."""

import json
from typing import Any

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger
from app.services.database import DatabaseService

logger = get_logger(__name__)


class FullTextSearchService:
    """Service for performing full-text keyword search on document chunks."""

    def __init__(self, db: DatabaseService):
        """Initialize the full-text search service.

        Args:
            db: PostgreSQL database service
        """
        self.db = db

    async def search(
        self,
        query: str,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Perform full-text search for a query with session filtering.

        Args:
            query: Search query text
            session_id: Session identifier for filtering results
            limit: Maximum number of results to return (default from settings)

        Returns:
            List of matching chunks with relevance scores and metadata

        Raises:
            DocumentProcessingError: If search fails
        """
        try:
            limit = limit or settings.FULL_TEXT_SEARCH_LIMIT

            if not query or not query.strip():
                raise DocumentProcessingError("Search query cannot be empty")

            logger.info(f"Full-text search for query: '{query[:50]}...'")

            # Perform full-text search using PostgreSQL function with session filtering
            results = await self.db.fetch(
                "SELECT * FROM search_chunks_fulltext_by_session($1, $2, $3)",
                query,
                session_id,
                limit,
            )

            if not results:
                logger.info("No results found for full-text query")
                return []

            logger.info(f"Found {len(results)} results for full-text query")

            # Format results
            formatted_results = []
            for idx, row in enumerate(results):
                # Parse metadata from JSON string if needed
                metadata = row.get("metadata", {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {}

                formatted_results.append(
                    {
                        "chunk_id": str(row["id"]),
                        "document_id": str(row["document_id"]),
                        "content": row["content"],
                        "contextual_content": row.get(
                            "contextual_content", row["content"]
                        ),
                        "relevance_score": float(row.get("rank", 0.0)),
                        "rank": idx + 1,
                        "metadata": metadata,
                    }
                )

            return formatted_results

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Full-text search failed: {e}", exc_info=True)
            raise DocumentProcessingError(f"Full-text search failed: {e}") from e

    async def search_by_document(
        self,
        query: str,
        document_id: str,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Perform full-text search within a specific document with session verification.

        Args:
            query: Search query text
            document_id: UUID of the document to search within
            session_id: Session identifier for verifying document access
            limit: Maximum number of results to return (default from settings)

        Returns:
            List of matching chunks from the specified document

        Raises:
            DocumentProcessingError: If search fails
        """
        try:
            limit = limit or settings.FULL_TEXT_SEARCH_LIMIT

            if not query or not query.strip():
                raise DocumentProcessingError("Search query cannot be empty")

            logger.info(
                f"Full-text search in document {document_id} for query: '{query[:50]}...'"
            )

            # Perform full-text search filtered by document_id with session verification
            results = await self.db.fetch(
                "SELECT * FROM search_chunks_fulltext_by_document_and_session($1, $2::uuid, $3, $4)",
                query,
                document_id,
                session_id,
                limit,
            )

            if not results:
                logger.info(f"No full-text results found in document {document_id}")
                return []

            logger.info(
                f"Found {len(results)} full-text results in document {document_id}"
            )

            # Format results
            formatted_results = []
            for idx, row in enumerate(results):
                # Parse metadata from JSON string if needed
                metadata = row.get("metadata", {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {}

                formatted_results.append(
                    {
                        "chunk_id": str(row["id"]),
                        "document_id": str(row["document_id"]),
                        "content": row["content"],
                        "contextual_content": row.get(
                            "contextual_content", row["content"]
                        ),
                        "relevance_score": float(row.get("rank", 0.0)),
                        "rank": idx + 1,
                        "metadata": metadata,
                    }
                )

            return formatted_results

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Full-text search by document failed: {e}", exc_info=True)
            raise DocumentProcessingError(
                f"Full-text search by document failed: {e}"
            ) from e
