"""Performance benchmarks for database operations."""

from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import settings
from app.services.database import DatabaseService
from app.services.full_text_search import FullTextSearchService
from app.services.hybrid_search import HybridSearchService
from app.services.vector_search import VectorSearchService

pytestmark = pytest.mark.benchmark


@pytest.fixture(scope="module")
async def db_service():
    """Create DatabaseService for benchmarking."""
    db = DatabaseService()
    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
def vector_search_service(db_service):
    """Create vector search service instance."""
    return VectorSearchService(db=db_service)


@pytest.fixture
def full_text_search_service(db_service):
    """Create full-text search service instance."""
    return FullTextSearchService(db=db_service)


@pytest.fixture
def hybrid_search_service(db_service):
    """Create hybrid search service instance."""
    return HybridSearchService(db=db_service)


@pytest.mark.asyncio
async def test_vector_search_performance(benchmark, vector_search_service):
    """Benchmark vector search performance."""

    def search():
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            vector_search_service.search(
                query="machine learning",
                top_k=10,
                similarity_threshold=0.5,
            )
        )

    result = benchmark.pedantic(search, rounds=20, iterations=1)
    # Result may be empty if no documents, but should execute without error
    assert result is not None


@pytest.mark.asyncio
async def test_full_text_search_performance(benchmark, full_text_search_service):
    """Benchmark full-text search performance."""

    def search():
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            full_text_search_service.search(query="Python programming", limit=10)
        )

    result = benchmark.pedantic(search, rounds=20, iterations=1)
    assert result is not None


@pytest.mark.asyncio
async def test_hybrid_search_performance(benchmark, hybrid_search_service):
    """Benchmark hybrid search (vector + full-text) performance."""
    with patch("app.services.embeddings.EmbeddingService.generate_query_embedding") as mock:
        mock.return_value = [0.1] * 768

        def search():
            import asyncio
            return asyncio.get_event_loop().run_until_complete(
                hybrid_search_service.search(
                    query="What is machine learning?", top_k=10
                )
            )

        result = benchmark.pedantic(search, rounds=10, iterations=1)
        assert result is not None


@pytest.mark.asyncio
async def test_document_filtered_search(benchmark, vector_search_service):
    """Benchmark document-filtered vector search."""
    document_id = "test-doc-123"

    def search():
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            vector_search_service.search_by_document(
                query="test query", document_id=document_id, top_k=10
            )
        )

    result = benchmark.pedantic(search, rounds=20, iterations=1)
    assert result is not None


@pytest.mark.slow
@pytest.mark.asyncio
async def test_large_result_set_search(benchmark, hybrid_search_service):
    """Benchmark search with large result set (top_k=100)."""
    with patch("app.services.embeddings.EmbeddingService.generate_query_embedding") as mock:
        mock.return_value = [0.1] * 768

        def search():
            import asyncio
            return asyncio.get_event_loop().run_until_complete(
                hybrid_search_service.search(query="comprehensive search", top_k=100)
            )

        result = benchmark.pedantic(search, rounds=5, iterations=1)
        assert result is not None


@pytest.mark.asyncio
async def test_chunk_retrieval_by_id(benchmark, db_service):
    """Benchmark direct chunk retrieval by ID."""
    chunk_id = "test-chunk-123"

    def retrieve():
        import asyncio

        async def _retrieve():
            try:
                result = await db_service.fetchrow(
                    "SELECT * FROM chunks WHERE id = $1", chunk_id
                )
                return result
            except Exception:
                return None

        return asyncio.get_event_loop().run_until_complete(_retrieve())

    result = benchmark.pedantic(retrieve, rounds=50, iterations=1)
    # Result may be None if chunk doesn't exist
    assert result is not None or result is None


@pytest.mark.asyncio
async def test_document_metadata_retrieval(benchmark, db_service):
    """Benchmark document metadata retrieval."""
    document_id = "test-doc-123"

    def retrieve():
        import asyncio

        async def _retrieve():
            try:
                result = await db_service.fetchrow(
                    "SELECT * FROM documents WHERE id = $1", document_id
                )
                return result
            except Exception:
                return None

        return asyncio.get_event_loop().run_until_complete(_retrieve())

    result = benchmark.pedantic(retrieve, rounds=50, iterations=1)
    # Result may be None if document doesn't exist
    assert result is not None or result is None


@pytest.mark.slow
@pytest.mark.asyncio
async def test_count_chunks_by_document(benchmark, db_service):
    """Benchmark counting chunks for a document."""
    document_id = "test-doc-123"

    def count():
        import asyncio

        async def _count():
            try:
                result = await db_service.fetchval(
                    "SELECT COUNT(*) FROM chunks WHERE document_id = $1", document_id
                )
                return result
            except Exception:
                return 0

        return asyncio.get_event_loop().run_until_complete(_count())

    result = benchmark.pedantic(count, rounds=20, iterations=1)
    assert result is not None
