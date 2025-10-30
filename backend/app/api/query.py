"""Query endpoint for RAG chatbot."""

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import SupabaseClient
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger
from app.models.base import QueryMetadata, QueryRequest, QueryResponse, SearchResult
from app.services.hybrid_search import HybridSearchService
from app.services.llm import LLMService
from app.services.reranking import RerankingService

logger = get_logger(__name__)

router = APIRouter()


@router.post("/query", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def query(
    request: QueryRequest,
    supabase: SupabaseClient,
) -> QueryResponse:
    """Process a user query through the RAG pipeline.

    Pipeline:
    1. Hybrid search (vector + full-text with RRF)
    2. Cohere reranking
    3. Claude answer generation with citations

    Args:
        request: Query request with query text and optional parameters
        supabase: Supabase client dependency

    Returns:
        QueryResponse with answer, sources, and metadata

    Raises:
        HTTPException: If query processing fails
    """
    try:
        logger.info(f"Processing query: '{request.query[:50]}...'")

        # Log conversation history for debugging
        if request.conversation_history:
            logger.info(
                f"Conversation history: {len(request.conversation_history)} messages"
            )
            for idx, msg in enumerate(request.conversation_history):
                logger.info(f"  [{idx}] {msg.role}: {msg.content[:80]}...")
        else:
            logger.info("No conversation history provided")

        # Initialize services
        hybrid_search = HybridSearchService(supabase_client=supabase)
        reranking_service = RerankingService()
        llm_service = LLMService()

        # Step 1: Hybrid search
        logger.info("Running hybrid search...")
        if request.document_id:
            search_response = hybrid_search.search_by_document(
                query=request.query,
                document_id=str(request.document_id),
                top_k=30,  # Get more results for reranking
            )
        else:
            search_response = hybrid_search.search(
                query=request.query,
                top_k=30,  # Get more results for reranking
            )

        search_results = search_response["results"]
        search_timing = search_response["metadata"]["timing"]

        if not search_results:
            logger.warning("No search results found")
            return QueryResponse(
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

        # Step 2: Reranking
        logger.info(f"Reranking {len(search_results)} results...")
        rerank_response = reranking_service.rerank_with_metadata(
            query=request.query,
            results=search_results,
            top_k=request.top_k,
        )

        reranked_results = rerank_response["results"]
        rerank_metadata = rerank_response["metadata"]

        # Step 3: LLM answer generation
        logger.info("Generating answer with Claude...")

        # Convert conversation history to dict format if provided
        conversation_history = None
        if request.conversation_history:
            conversation_history = [
                {"role": msg.role, "content": msg.content}
                for msg in request.conversation_history
            ]

        llm_response = llm_service.generate_answer_with_retry(
            query=request.query,
            search_results=reranked_results,
            max_retries=3,
            conversation_history=conversation_history,
        )

        # Format sources for response
        sources = [
            SearchResult(
                chunk_id=source["chunk_id"],
                document_id=source["document_id"],
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

        # Combine timing from all stages
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

        return QueryResponse(
            success=True,
            message="Query processed successfully",
            answer=llm_response["answer"],
            sources=sources,
            metadata=metadata,
        )

    except DocumentProcessingError as e:
        logger.error(f"Query processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error during query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        ) from e
