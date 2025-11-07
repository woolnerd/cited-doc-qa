"""Vector similarity search service using embeddings."""

import json
from typing import Any

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger
from app.services.database import DatabaseService
from app.services.embeddings import EmbeddingService

logger = get_logger(__name__)


class VectorSearchService:
    """Service for performing vector similarity search on document chunks."""

    def __init__(
        self,
        db: DatabaseService,
        embedding_service: EmbeddingService | None = None,
    ):
        """Initialize the vector search service.

        Args:
            db: PostgreSQL database service
            embedding_service: Embedding service (creates new if None)
        """
        self.db = db
        self.embedding_service = embedding_service or EmbeddingService()

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search for a query.

        Args:
            query: Search query text
            top_k: Number of top results to return (default from settings)
            similarity_threshold: Minimum similarity score (0-1, default from settings)

        Returns:
            List of matching chunks with similarity scores and metadata

        Raises:
            DocumentProcessingError: If search fails
        """
        try:
            top_k = top_k or settings.SEARCH_TOP_K
            similarity_threshold = (
                similarity_threshold or settings.SEARCH_SIMILARITY_THRESHOLD
            )

            logger.info(f"Vector search for query: '{query[:50]}...'")

            # Generate embedding for query
            query_embedding = self.embedding_service.generate_query_embedding(query)
            logger.debug(
                f"Generated query embedding with {len(query_embedding)} dimensions"
            )

            # Convert embedding list to PostgreSQL vector format string
            vector_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            # Perform vector similarity search using PostgreSQL function
            results = await self.db.fetch(
                "SELECT * FROM search_chunks($1::vector, $2, $3)",
                vector_str,
                top_k,
                similarity_threshold,
            )

            if not results:
                logger.info("No results found for query")
                return []

            logger.info(f"Found {len(results)} results for query")

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
                        "similarity_score": float(row["similarity"]),
                        "rank": idx + 1,
                        "metadata": metadata,
                    }
                )

            return formatted_results

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            raise DocumentProcessingError(f"Vector search failed: {e}") from e

    async def search_by_document(
        self,
        query: str,
        document_id: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search within a specific document.

        Args:
            query: Search query text
            document_id: UUID of the document to search within
            top_k: Number of top results to return (default from settings)
            similarity_threshold: Minimum similarity score (0-1, default from settings)

        Returns:
            List of matching chunks from the specified document

        Raises:
            DocumentProcessingError: If search fails
        """
        try:
            top_k = top_k or settings.SEARCH_TOP_K
            similarity_threshold = (
                similarity_threshold or settings.SEARCH_SIMILARITY_THRESHOLD
            )

            logger.info(
                f"Vector search in document {document_id} for query: '{query[:50]}...'"
            )

            # Generate embedding for query
            query_embedding = self.embedding_service.generate_query_embedding(query)

            # Convert embedding list to PostgreSQL vector format string
            vector_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            # Perform vector similarity search filtered by document_id
            results = await self.db.fetch(
                "SELECT * FROM search_chunks_by_document($1::vector, $2::uuid, $3, $4)",
                vector_str,
                document_id,
                top_k,
                similarity_threshold,
            )

            if not results:
                logger.info(f"No results found in document {document_id}")
                return []

            logger.info(f"Found {len(results)} results in document {document_id}")

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
                        "similarity_score": float(row["similarity"]),
                        "rank": idx + 1,
                        "metadata": metadata,
                    }
                )

            return formatted_results

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Vector search by document failed: {e}", exc_info=True)
            raise DocumentProcessingError(
                f"Vector search by document failed: {e}"
            ) from e
