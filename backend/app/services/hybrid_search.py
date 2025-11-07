"""Hybrid search service combining vector and full-text search with RRF."""

import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger
from app.services.database import DatabaseService
from app.services.embeddings import EmbeddingService
from app.services.full_text_search import FullTextSearchService
from app.services.vector_search import VectorSearchService

logger = get_logger(__name__)


class HybridSearchService:
    """Service for hybrid search using vector and full-text search with RRF."""

    def __init__(
        self,
        db: DatabaseService,
        embedding_service: EmbeddingService | None = None,
        vector_search_service: VectorSearchService | None = None,
        full_text_search_service: FullTextSearchService | None = None,
    ):
        """Initialize the hybrid search service.

        Args:
            db: PostgreSQL database service
            embedding_service: Embedding service (creates new if None)
            vector_search_service: Vector search service (creates new if None)
            full_text_search_service: Full-text search service (creates new if None)
        """
        self.db = db
        self.embedding_service = embedding_service or EmbeddingService()

        # Initialize search services
        self.vector_search = vector_search_service or VectorSearchService(
            db=db,
            embedding_service=self.embedding_service,
        )
        self.full_text_search = full_text_search_service or FullTextSearchService(db=db)

    def _calculate_rrf_score(self, rank: int, k: int = settings.RRF_K) -> float:
        """Calculate RRF score for a given rank.

        Args:
            rank: The rank position (1-indexed)
            k: RRF constant (default 60)

        Returns:
            RRF score
        """
        return 1.0 / (k + rank)

    def _merge_results(
        self,
        vector_results: list[dict[str, Any]],
        fulltext_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge vector and full-text search results using RRF.

        Args:
            vector_results: Results from vector similarity search
            fulltext_results: Results from full-text search

        Returns:
            Merged and deduplicated results with RRF scores
        """
        # Create a dictionary to store combined scores
        chunk_scores: dict[str, dict[str, Any]] = {}

        # Process vector search results
        for result in vector_results:
            chunk_id = result["chunk_id"]
            rrf_score = self._calculate_rrf_score(result["rank"])

            chunk_scores[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": result["document_id"],
                "content": result["content"],
                "contextual_content": result["contextual_content"],
                "metadata": result["metadata"],
                "rrf_score": rrf_score,
                "vector_score": result.get("similarity_score"),
                "fulltext_score": None,
                "vector_rank": result["rank"],
                "fulltext_rank": None,
                "source": "vector",
            }

        # Process full-text search results
        for result in fulltext_results:
            chunk_id = result["chunk_id"]
            rrf_score = self._calculate_rrf_score(result["rank"])

            if chunk_id in chunk_scores:
                # Chunk found in both searches - combine scores
                chunk_scores[chunk_id]["rrf_score"] += rrf_score
                chunk_scores[chunk_id]["fulltext_score"] = result.get("relevance_score")
                chunk_scores[chunk_id]["fulltext_rank"] = result["rank"]
                chunk_scores[chunk_id]["source"] = "both"
            else:
                # Chunk only in full-text search
                chunk_scores[chunk_id] = {
                    "chunk_id": chunk_id,
                    "document_id": result["document_id"],
                    "content": result["content"],
                    "contextual_content": result["contextual_content"],
                    "metadata": result["metadata"],
                    "rrf_score": rrf_score,
                    "vector_score": None,
                    "fulltext_score": result.get("relevance_score"),
                    "vector_rank": None,
                    "fulltext_rank": result["rank"],
                    "source": "fulltext",
                }

        # Sort by RRF score (descending) and add final rank
        sorted_results = sorted(
            chunk_scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )

        # Add final ranking
        for idx, result in enumerate(sorted_results):
            result["final_rank"] = idx + 1

        return sorted_results

    async def search(
        self,
        query: str,
        top_k: int = 30,
        vector_limit: int | None = None,
        fulltext_limit: int | None = None,
    ) -> dict[str, Any]:
        """Perform hybrid search combining vector and full-text search.

        Args:
            query: Search query text
            top_k: Number of final results to return (default 30)
            vector_limit: Limit for vector search (default from settings)
            fulltext_limit: Limit for full-text search (default from settings)

        Returns:
            Dictionary with merged results and performance metrics

        Raises:
            DocumentProcessingError: If search fails
        """
        try:
            vector_limit = vector_limit or settings.VECTOR_SEARCH_LIMIT
            fulltext_limit = fulltext_limit or settings.FULL_TEXT_SEARCH_LIMIT

            logger.info(f"Hybrid search for query: '{query[:50]}...'")

            # Track timing for each search
            start_time = time.time()

            # Run vector search
            vector_start = time.time()
            vector_results = await self.vector_search.search(
                query=query,
                top_k=vector_limit,
            )
            vector_time = time.time() - vector_start

            # Run full-text search
            fulltext_start = time.time()
            fulltext_results = await self.full_text_search.search(
                query=query,
                limit=fulltext_limit,
            )
            fulltext_time = time.time() - fulltext_start

            logger.info(
                f"Vector search: {len(vector_results)} results in {vector_time:.3f}s"
            )
            logger.info(
                f"Full-text search: {len(fulltext_results)} results in {fulltext_time:.3f}s"
            )

            # Merge results using RRF
            merged_results = self._merge_results(vector_results, fulltext_results)

            # Limit to top_k results
            final_results = merged_results[:top_k]

            total_time = time.time() - start_time

            logger.info(
                f"Hybrid search completed: {len(final_results)} results in {total_time:.3f}s"
            )

            # Count sources
            sources_count = {
                "vector_only": sum(1 for r in final_results if r["source"] == "vector"),
                "fulltext_only": sum(
                    1 for r in final_results if r["source"] == "fulltext"
                ),
                "both": sum(1 for r in final_results if r["source"] == "both"),
            }

            return {
                "results": final_results,
                "metadata": {
                    "total_results": len(final_results),
                    "vector_results_count": len(vector_results),
                    "fulltext_results_count": len(fulltext_results),
                    "merged_results_count": len(merged_results),
                    "sources": sources_count,
                    "timing": {
                        "vector_search_ms": round(vector_time * 1000, 2),
                        "fulltext_search_ms": round(fulltext_time * 1000, 2),
                        "total_ms": round(total_time * 1000, 2),
                    },
                    "query": query,
                    "top_k": top_k,
                    "rrf_k": settings.RRF_K,
                },
            }

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            raise DocumentProcessingError(f"Hybrid search failed: {e}") from e

    async def search_by_document(
        self,
        query: str,
        document_id: str,
        top_k: int = 30,
        vector_limit: int | None = None,
        fulltext_limit: int | None = None,
    ) -> dict[str, Any]:
        """Perform hybrid search within a specific document.

        Args:
            query: Search query text
            document_id: UUID of the document to search within
            top_k: Number of final results to return (default 30)
            vector_limit: Limit for vector search (default from settings)
            fulltext_limit: Limit for full-text search (default from settings)

        Returns:
            Dictionary with merged results and performance metrics

        Raises:
            DocumentProcessingError: If search fails
        """
        try:
            vector_limit = vector_limit or settings.VECTOR_SEARCH_LIMIT
            fulltext_limit = fulltext_limit or settings.FULL_TEXT_SEARCH_LIMIT

            logger.info(
                f"Hybrid search in document {document_id} for query: '{query[:50]}...'"
            )

            # Track timing for each search
            start_time = time.time()

            # Run vector search
            vector_start = time.time()
            vector_results = await self.vector_search.search_by_document(
                query=query,
                document_id=document_id,
                top_k=vector_limit,
            )
            vector_time = time.time() - vector_start

            # Run full-text search
            fulltext_start = time.time()
            fulltext_results = await self.full_text_search.search_by_document(
                query=query,
                document_id=document_id,
                limit=fulltext_limit,
            )
            fulltext_time = time.time() - fulltext_start

            logger.info(
                f"Vector search: {len(vector_results)} results in {vector_time:.3f}s"
            )
            logger.info(
                f"Full-text search: {len(fulltext_results)} results in {fulltext_time:.3f}s"
            )

            # Merge results using RRF
            merged_results = self._merge_results(vector_results, fulltext_results)

            # Limit to top_k results
            final_results = merged_results[:top_k]

            total_time = time.time() - start_time

            logger.info(
                f"Hybrid search in document completed: {len(final_results)} results in {total_time:.3f}s"
            )

            # Count sources
            sources_count = {
                "vector_only": sum(1 for r in final_results if r["source"] == "vector"),
                "fulltext_only": sum(
                    1 for r in final_results if r["source"] == "fulltext"
                ),
                "both": sum(1 for r in final_results if r["source"] == "both"),
            }

            return {
                "results": final_results,
                "metadata": {
                    "total_results": len(final_results),
                    "vector_results_count": len(vector_results),
                    "fulltext_results_count": len(fulltext_results),
                    "merged_results_count": len(merged_results),
                    "sources": sources_count,
                    "timing": {
                        "vector_search_ms": round(vector_time * 1000, 2),
                        "fulltext_search_ms": round(fulltext_time * 1000, 2),
                        "total_ms": round(total_time * 1000, 2),
                    },
                    "query": query,
                    "document_id": document_id,
                    "top_k": top_k,
                    "rrf_k": settings.RRF_K,
                },
            }

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Hybrid search by document failed: {e}", exc_info=True)
            raise DocumentProcessingError(
                f"Hybrid search by document failed: {e}"
            ) from e
