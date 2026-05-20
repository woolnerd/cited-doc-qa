"""Query endpoint for RAG chatbot."""

import asyncio
from typing import Any, TypedDict, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import settings
from app.core.dependencies import Database
from app.core.exceptions import DemoLimitError, DocumentProcessingError
from app.core.logging import get_logger
from app.models.base import QueryMetadata, QueryRequest, QueryResponse, SearchResult
from app.services.cancellable_execution import run_blocking_in_process
from app.services.demo_limits import DemoLimitService
from app.services.hybrid_search import HybridSearchService
from app.services.llm import LLMService
from app.services.query_enhancement import QueryEnhancementService
from app.services.reranking import RerankingService

logger = get_logger(__name__)

router = APIRouter()


class RerankResponse(TypedDict):
    results: list[dict[str, Any]]
    metadata: dict[str, Any]


class LLMSource(TypedDict):
    citation_num: int
    chunk_id: str
    document_id: UUID
    document_name: str
    chunk_index: int
    rerank_score: float | None


class LLMMetadata(TypedDict):
    query: str
    model: str
    temperature: float
    max_tokens: int
    tokens_used: dict[str, int]
    context_chunks: int
    timing: dict[str, float]
    finish_reason: str | None


class LLMResponse(TypedDict):
    answer: str
    sources: list[LLMSource]
    metadata: LLMMetadata


def _enhance_query_worker(
    query: str, conversation_history: list[dict[str, str]]
) -> str:
    """Run query enhancement in a separate process."""
    query_enhancer = QueryEnhancementService()
    return query_enhancer.enhance_query(
        query=query,
        conversation_history=conversation_history,
    )


def _rerank_worker(
    query: str, search_results: list[dict], top_k: int
) -> RerankResponse:
    """Run reranking in a separate process."""
    reranking_service = RerankingService()
    return cast(
        RerankResponse,
        reranking_service.rerank_with_metadata(
            query=query,
            results=search_results,
            top_k=top_k,
        ),
    )


def _llm_worker(
    query: str,
    search_results: list[dict],
    conversation_history: list[dict[str, str]] | None,
) -> LLMResponse:
    """Run answer generation in a separate process."""
    llm_service = LLMService()
    return cast(
        LLMResponse,
        llm_service.generate_answer_with_retry(
            query=query,
            search_results=search_results,
            max_retries=3,
            conversation_history=conversation_history,
        ),
    )


@router.post("/query", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def query(
    request: QueryRequest,
    http_request: Request,
    db: Database,
) -> QueryResponse:
    """Process a user query through the RAG pipeline.

    Pipeline:
    1. Query enhancement (with conversation context)
    2. Hybrid search (vector + full-text with RRF)
    3. Cohere reranking
    4. Claude answer generation with citations

    Args:
        request: Query request with query text and optional parameters
        db: PostgreSQL database service dependency

    Returns:
        QueryResponse with answer, sources, and metadata

    Raises:
        HTTPException: If query processing fails
    """
    try:
        logger.info(f"Processing query: '{request.query[:50]}...'")

        demo_limits = DemoLimitService(db=db)
        client_host = http_request.client.host if http_request.client else None
        await demo_limits.check_query_allowed(
            session_id=request.session_id,
            ip_address=client_host,
            query=request.query,
        )

        # Log conversation history for debugging
        if request.conversation_history:
            logger.info(
                f"Conversation history: {len(request.conversation_history)} messages"
            )
            for idx, msg in enumerate(request.conversation_history):
                logger.info(f"  [{idx}] {msg.role}: {msg.content[:80]}...")
        else:
            logger.info("No conversation history provided")

        hybrid_search = HybridSearchService(db=db)
        query_enhancer = QueryEnhancementService()
        reranking_service = RerankingService()
        llm_service = LLMService()

        async def process_query() -> QueryResponse:
            retrieval_top_k = (
                settings.DEMO_MAX_RETRIEVED_CHUNKS if settings.DEMO_MODE else 30
            )

            # Step 1: Query enhancement (if conversation context exists)
            enhanced_query = request.query
            if request.conversation_history:
                conversation_history = [
                    {"role": msg.role, "content": msg.content}
                    for msg in request.conversation_history
                ]
                if settings.DEMO_MODE:
                    enhanced_query = await run_blocking_in_process(
                        _enhance_query_worker,
                        request.query,
                        conversation_history,
                        timeout_seconds=settings.DEMO_REQUEST_TIMEOUT_SECONDS,
                    )
                else:
                    enhanced_query = await asyncio.to_thread(
                        query_enhancer.enhance_query,
                        request.query,
                        conversation_history,
                    )
                if enhanced_query != request.query:
                    logger.info(
                        f"Query enhanced: '{request.query}' → '{enhanced_query}'"
                    )

            # Step 2: Hybrid search (use enhanced query with session filtering)
            logger.info(f"Running hybrid search for session: {request.session_id}")
            if request.document_id:
                search_response = await hybrid_search.search_by_document(
                    query=enhanced_query,
                    document_id=str(request.document_id),
                    session_id=request.session_id,
                    top_k=retrieval_top_k,
                )
            else:
                search_response = await hybrid_search.search(
                    query=enhanced_query,
                    session_id=request.session_id,
                    top_k=retrieval_top_k,
                )

            search_results = search_response["results"]
            search_timing = search_response["metadata"]["timing"]

            if not search_results:
                logger.warning("No search results found")
                response = QueryResponse(
                    success=True,
                    message="No relevant information found for your query",
                    answer="I couldn't find any relevant information in the documents to answer your question.",
                    sources=[],
                    metadata=QueryMetadata(
                        query=request.query,
                        results_count=0,
                        model="",
                        temperature=0.0,
                        tokens_used={
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                        },
                        timing=search_timing,
                    ),
                )
                await demo_limits.record_query(
                    session_id=request.session_id,
                    ip_address=client_host,
                    query=request.query,
                    metadata={"results_count": 0},
                )
                return response

            # Step 3: Reranking (use enhanced query for better relevance)
            logger.info(f"Reranking {len(search_results)} results...")
            if settings.DEMO_MODE:
                rerank_response = await run_blocking_in_process(
                    _rerank_worker,
                    enhanced_query,
                    search_results,
                    request.top_k,
                    timeout_seconds=settings.DEMO_REQUEST_TIMEOUT_SECONDS,
                )
            else:
                rerank_response = cast(
                    RerankResponse,
                    await asyncio.to_thread(
                        reranking_service.rerank_with_metadata,
                        enhanced_query,
                        search_results,
                        request.top_k,
                    ),
                )

            reranked_results = rerank_response["results"]
            rerank_metadata = rerank_response["metadata"]

            # Step 4: LLM answer generation (use original query for natural answer)
            logger.info("Generating answer with Claude...")

            conversation_history = None
            if request.conversation_history:
                conversation_history = [
                    {"role": msg.role, "content": msg.content}
                    for msg in request.conversation_history
                ]

            if settings.DEMO_MODE:
                llm_response = await run_blocking_in_process(
                    _llm_worker,
                    request.query,
                    reranked_results,
                    conversation_history,
                    timeout_seconds=settings.DEMO_REQUEST_TIMEOUT_SECONDS,
                )
            else:
                llm_response = cast(
                    LLMResponse,
                    await asyncio.to_thread(
                        llm_service.generate_answer_with_retry,
                        request.query,
                        reranked_results,
                        3,
                        1.0,
                        None,
                        None,
                        conversation_history,
                    ),
                )

            sources = [
                SearchResult(
                    chunk_id=source["chunk_id"],
                    document_id=UUID(str(source["document_id"])),
                    document_name=source["document_name"],
                    chunk_index=source["chunk_index"],
                    content=reranked_results[idx].get("content", ""),
                    citation_num=source["citation_num"],
                    rerank_score=source.get("rerank_score"),
                    rrf_score=reranked_results[idx].get("rrf_score"),
                    vector_score=reranked_results[idx].get("vector_score"),
                    fulltext_score=reranked_results[idx].get("fulltext_score"),
                )
                for idx, source in enumerate(llm_response["sources"])
            ]

            combined_timing = {
                **search_timing,
                "rerank_ms": rerank_metadata["timing"]["rerank_ms"],
                "generation_ms": llm_response["metadata"]["timing"]["generation_ms"],
                "total_ms": (
                    search_timing["total_ms"]
                    + rerank_metadata["timing"]["rerank_ms"]
                    + llm_response["metadata"]["timing"]["generation_ms"]
                ),
            }

            metadata = QueryMetadata(
                query=request.query,
                results_count=len(sources),
                model=llm_response["metadata"]["model"],
                temperature=llm_response["metadata"]["temperature"],
                tokens_used=llm_response["metadata"]["tokens_used"],
                timing=combined_timing,
                used_fallback=rerank_metadata.get("used_fallback", False),
            )

            logger.info(
                f"Query processed successfully in {combined_timing['total_ms']:.2f}ms"
            )

            response = QueryResponse(
                success=True,
                message="Query processed successfully",
                answer=llm_response["answer"],
                sources=sources,
                metadata=metadata,
            )
            await demo_limits.record_query(
                session_id=request.session_id,
                ip_address=client_host,
                query=request.query,
                metadata={"results_count": len(sources)},
            )
            return response

        if settings.DEMO_MODE:
            try:
                async with asyncio.timeout(settings.DEMO_REQUEST_TIMEOUT_SECONDS):
                    return await process_query()
            except TimeoutError as exc:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=(
                        "This demo request took too long. Please try again or ask a "
                        "smaller question."
                    ),
                ) from exc

        return await process_query()

    except HTTPException:
        raise
    except DocumentProcessingError as e:
        logger.error(f"Query processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}",
        ) from e
    except DemoLimitError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        ) from e
