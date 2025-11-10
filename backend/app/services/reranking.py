"""Reranking service using Cohere's rerank API."""

import time
from typing import Any

import cohere
from cohere.core.api_error import ApiError as CohereApiError

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger

logger = get_logger(__name__)


class RerankingService:
    """Service for reranking search results using Cohere."""

    def __init__(self, api_key: str | None = None):
        """Initialize the reranking service.

        Args:
            api_key: Cohere API key (uses settings if None)

        Raises:
            DocumentProcessingError: If Cohere client initialization fails
        """
        try:
            self.api_key = api_key or settings.COHERE_API_KEY
            self.client = cohere.ClientV2(api_key=self.api_key)
            self.model = settings.RERANK_MODEL
            self.max_retries = settings.RERANK_MAX_RETRIES
            self.retry_delay = settings.RERANK_RETRY_DELAY
            logger.info(f"Reranking service initialized with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize Cohere client: {e}", exc_info=True)
            raise DocumentProcessingError(
                f"Failed to initialize Cohere client: {e}"
            ) from e

    def _exponential_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        return float(self.retry_delay * (2**attempt))

    def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Rerank search results using Cohere's rerank API.

        Args:
            query: Search query text
            results: List of search results to rerank
            top_k: Number of top results to return (default from settings)

        Returns:
            Reranked results with Cohere relevance scores

        Raises:
            DocumentProcessingError: If reranking fails after all retries
        """
        if not results:
            logger.info("No results to rerank, returning empty list")
            return []

        top_k = top_k or settings.RERANK_TOP_K

        logger.info(
            f"Reranking {len(results)} results for query: '{query[:50]}...', top_k={top_k}"
        )

        # Prepare documents for reranking (use contextual_content for better accuracy)
        documents = [
            result.get("contextual_content", result.get("content", ""))
            for result in results
        ]

        # Attempt reranking with retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()

                # Call Cohere rerank API
                response = self.client.rerank(
                    model=self.model,
                    query=query,
                    documents=documents,
                    top_n=min(top_k, len(documents)),
                )

                rerank_time = time.time() - start_time
                logger.info(
                    f"Reranking completed in {rerank_time:.3f}s, returned {len(response.results)} results"
                )

                # Process reranked results and filter by threshold
                reranked_results = []
                for idx, rerank_result in enumerate(response.results):
                    original_result = results[rerank_result.index]
                    rerank_score = rerank_result.relevance_score

                    # Filter out results below threshold
                    if rerank_score < settings.RERANK_SCORE_THRESHOLD:
                        logger.debug(
                            f"Filtering out result with rerank score {rerank_score:.3f} (below threshold {settings.RERANK_SCORE_THRESHOLD})"
                        )
                        continue

                    # Add Cohere relevance score
                    reranked_results.append(
                        {
                            **original_result,
                            "rerank_score": rerank_score,
                            "rerank_rank": idx + 1,
                            "original_rank": original_result.get("final_rank"),
                            "original_rrf_score": original_result.get("rrf_score"),
                        }
                    )

                logger.info(
                    f"Reranking successful on attempt {attempt + 1}/{self.max_retries}"
                )
                return reranked_results

            except CohereApiError as e:
                last_error = e
                logger.warning(
                    f"Cohere API error on attempt {attempt + 1}/{self.max_retries}: {e}"
                )

                if attempt < self.max_retries - 1:
                    delay = self._exponential_backoff(attempt)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(
                        f"Reranking failed after {self.max_retries} attempts, falling back to RRF scores"
                    )
                    # Fallback: return original results sorted by RRF score
                    return self._fallback_to_rrf(results, top_k)

            except Exception as e:
                last_error = e
                logger.error(
                    f"Unexpected error during reranking on attempt {attempt + 1}/{self.max_retries}: {e}",
                    exc_info=True,
                )

                if attempt < self.max_retries - 1:
                    delay = self._exponential_backoff(attempt)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(
                        f"Reranking failed after {self.max_retries} attempts, falling back to RRF scores"
                    )
                    # Fallback: return original results sorted by RRF score
                    return self._fallback_to_rrf(results, top_k)

        # Should not reach here, but just in case
        logger.error(f"Reranking failed: {last_error}, falling back to RRF scores")
        return self._fallback_to_rrf(results, top_k)

    def _fallback_to_rrf(
        self, results: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]]:
        """Fallback method when reranking fails: return top results by RRF score.

        Args:
            results: Original search results
            top_k: Number of top results to return

        Returns:
            Top results sorted by RRF score
        """
        logger.info(f"Using fallback: returning top {top_k} results by RRF score")

        # Sort by RRF score (descending) and take top_k
        sorted_results = sorted(
            results,
            key=lambda x: x.get("rrf_score", 0.0),
            reverse=True,
        )[:top_k]

        # Add fallback indicators
        for idx, result in enumerate(sorted_results):
            result["rerank_score"] = None
            result["rerank_rank"] = idx + 1
            result["original_rank"] = result.get("final_rank")
            result["original_rrf_score"] = result.get("rrf_score")
            result["rerank_fallback"] = True

        return sorted_results

    def rerank_with_metadata(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """Rerank results and return with metadata.

        Args:
            query: Search query text
            results: List of search results to rerank
            top_k: Number of top results to return (default from settings)

        Returns:
            Dictionary with reranked results and metadata
        """
        top_k = top_k or settings.RERANK_TOP_K

        start_time = time.time()
        reranked_results = self.rerank(query, results, top_k)
        total_time = time.time() - start_time

        # Check if fallback was used
        used_fallback = any(
            result.get("rerank_fallback", False) for result in reranked_results
        )

        return {
            "results": reranked_results,
            "metadata": {
                "total_results": len(reranked_results),
                "input_results_count": len(results),
                "query": query,
                "top_k": top_k,
                "model": self.model,
                "used_fallback": used_fallback,
                "timing": {
                    "rerank_ms": round(total_time * 1000, 2),
                },
            },
        }
