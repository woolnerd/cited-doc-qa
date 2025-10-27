"""Vector similarity search service using embeddings."""

from typing import Any

from supabase import Client

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger
from app.services.embeddings import EmbeddingService

logger = get_logger(__name__)


class VectorSearchService:
    """Service for performing vector similarity search on document chunks."""

    def __init__(
        self,
        supabase_client: Client,
        embedding_service: EmbeddingService | None = None,
    ):
        """Initialize the vector search service.

        Args:
            supabase_client: Supabase client for database operations
            embedding_service: Embedding service (creates new if None)
        """
        self.supabase = supabase_client
        self.embedding_service = embedding_service or EmbeddingService()

    def search(
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

            # Perform vector similarity search using Supabase RPC
            # Note: This assumes a PostgreSQL function 'search_chunks' exists
            # that performs cosine similarity search using pgvector
            result = self.supabase.rpc(
                "search_chunks",
                {
                    "query_embedding": query_embedding,
                    "match_count": top_k,
                    "similarity_threshold": similarity_threshold,
                },
            ).execute()

            if not result.data:
                logger.info("No results found for query")
                return []

            results = result.data
            logger.info(f"Found {len(results)} results for query")

            # Format results
            formatted_results = []
            for idx, row in enumerate(results):
                formatted_results.append(
                    {
                        "chunk_id": row["id"],
                        "document_id": row["document_id"],
                        "content": row["content"],
                        "contextual_content": row.get(
                            "contextual_content", row["content"]
                        ),
                        "similarity_score": float(row["similarity"]),
                        "rank": idx + 1,
                        "metadata": row.get("metadata", {}),
                    }
                )

            return formatted_results

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            raise DocumentProcessingError(f"Vector search failed: {e}") from e

    def search_by_document(
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

            # Perform vector similarity search filtered by document_id
            result = self.supabase.rpc(
                "search_chunks_by_document",
                {
                    "query_embedding": query_embedding,
                    "target_document_id": document_id,
                    "match_count": top_k,
                    "similarity_threshold": similarity_threshold,
                },
            ).execute()

            if not result.data:
                logger.info(f"No results found in document {document_id}")
                return []

            results = result.data
            logger.info(f"Found {len(results)} results in document {document_id}")

            # Format results
            formatted_results = []
            for idx, row in enumerate(results):
                formatted_results.append(
                    {
                        "chunk_id": row["id"],
                        "document_id": row["document_id"],
                        "content": row["content"],
                        "contextual_content": row.get(
                            "contextual_content", row["content"]
                        ),
                        "similarity_score": float(row["similarity"]),
                        "rank": idx + 1,
                        "metadata": row.get("metadata", {}),
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
