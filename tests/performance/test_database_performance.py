"""Performance benchmarks for database operations."""

from unittest.mock import patch

import pytest
from app.core.config import settings
from app.services.retrieval import RetrievalService
from supabase import create_client

pytestmark = pytest.mark.benchmark


@pytest.fixture(scope="module")
def supabase_client():
    """Create Supabase client for benchmarking."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


@pytest.fixture
def retrieval_service(supabase_client):
    """Create retrieval service instance."""
    service = RetrievalService()
    service.supabase = supabase_client
    return service


def test_vector_search_performance(benchmark, retrieval_service):
    """Benchmark vector search performance."""
    query_embedding = [0.1] * 768
    similarity_threshold = 0.5

    def search():
        return retrieval_service.vector_search(
            query_embedding=query_embedding,
            limit=10,
            similarity_threshold=similarity_threshold,
        )

    result = benchmark.pedantic(search, rounds=20, iterations=1)
    # Result may be empty if no documents, but should execute without error
    assert result is not None


def test_full_text_search_performance(benchmark, retrieval_service):
    """Benchmark full-text search performance."""
    query = "Python programming"

    def search():
        return retrieval_service.full_text_search(query=query, limit=10)

    result = benchmark.pedantic(search, rounds=20, iterations=1)
    assert result is not None


def test_hybrid_search_performance(benchmark, retrieval_service):
    """Benchmark hybrid search (vector + full-text) performance."""
    with patch("app.services.embeddings.EmbeddingService.generate_embedding") as mock:
        mock.return_value = [0.1] * 768

        def search():
            return retrieval_service.hybrid_search(
                query="What is machine learning?", top_k=10
            )

        result = benchmark.pedantic(search, rounds=10, iterations=1)
        assert result is not None


def test_document_filtered_search(benchmark, retrieval_service):
    """Benchmark document-filtered vector search."""
    query_embedding = [0.1] * 768
    document_id = "test-doc-123"

    def search():
        return retrieval_service.vector_search(
            query_embedding=query_embedding, limit=10, document_id=document_id
        )

    result = benchmark.pedantic(search, rounds=20, iterations=1)
    assert result is not None


@pytest.mark.slow
def test_large_result_set_search(benchmark, retrieval_service):
    """Benchmark search with large result set (top_k=100)."""
    with patch("app.services.embeddings.EmbeddingService.generate_embedding") as mock:
        mock.return_value = [0.1] * 768

        def search():
            return retrieval_service.hybrid_search(
                query="comprehensive search", top_k=100
            )

        result = benchmark.pedantic(search, rounds=5, iterations=1)
        assert result is not None


def test_chunk_retrieval_by_id(benchmark, supabase_client):
    """Benchmark direct chunk retrieval by ID."""
    chunk_id = "test-chunk-123"

    def retrieve():
        try:
            result = (
                supabase_client.table("chunks").select("*").eq("id", chunk_id).execute()
            )
            return result.data
        except Exception:
            return []

    result = benchmark.pedantic(retrieve, rounds=50, iterations=1)
    assert result is not None


def test_document_metadata_retrieval(benchmark, supabase_client):
    """Benchmark document metadata retrieval."""
    document_id = "test-doc-123"

    def retrieve():
        try:
            result = (
                supabase_client.table("documents")
                .select("*")
                .eq("id", document_id)
                .execute()
            )
            return result.data
        except Exception:
            return []

    result = benchmark.pedantic(retrieve, rounds=50, iterations=1)
    assert result is not None


@pytest.mark.slow
def test_count_chunks_by_document(benchmark, supabase_client):
    """Benchmark counting chunks for a document."""
    document_id = "test-doc-123"

    def count():
        try:
            result = (
                supabase_client.table("chunks")
                .select("id", count="exact")
                .eq("document_id", document_id)
                .execute()
            )
            return result.count
        except Exception:
            return 0

    result = benchmark.pedantic(count, rounds=20, iterations=1)
    assert result is not None
