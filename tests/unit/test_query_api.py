"""Tests for query API endpoint."""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    return Mock()


@pytest.fixture
def sample_hybrid_search_response():
    """Sample hybrid search response."""
    doc_id = str(uuid4())
    return {
        "results": [
            {
                "chunk_id": "chunk1",
                "document_id": doc_id,
                "content": "Python is a programming language.",
                "contextual_content": "Document: python_guide.pdf\n\nPython is a programming language.",
                "metadata": {"document_name": "python_guide.pdf", "chunk_index": 0},
                "rrf_score": 0.032,
                "vector_score": 0.9,
                "fulltext_score": 0.85,
                "final_rank": 1,
            },
            {
                "chunk_id": "chunk2",
                "document_id": doc_id,
                "content": "Python supports multiple paradigms.",
                "contextual_content": "Document: python_guide.pdf\n\nPython supports multiple paradigms.",
                "metadata": {"document_name": "python_guide.pdf", "chunk_index": 1},
                "rrf_score": 0.030,
                "vector_score": 0.85,
                "fulltext_score": 0.80,
                "final_rank": 2,
            },
        ],
        "metadata": {
            "timing": {
                "vector_search_ms": 100.0,
                "fulltext_search_ms": 50.0,
                "total_ms": 150.0,
            }
        },
    }


@pytest.fixture
def sample_rerank_response():
    """Sample reranking response."""
    doc_id = str(uuid4())
    return {
        "results": [
            {
                "chunk_id": "chunk1",
                "document_id": doc_id,
                "content": "Python is a programming language.",
                "contextual_content": "Document: python_guide.pdf\n\nPython is a programming language.",
                "metadata": {"document_name": "python_guide.pdf", "chunk_index": 0},
                "rerank_score": 0.95,
                "rrf_score": 0.032,
                "vector_score": 0.9,
                "fulltext_score": 0.85,
            }
        ],
        "metadata": {
            "used_fallback": False,
            "timing": {"rerank_ms": 200.0},
        },
    }


@pytest.fixture
def sample_llm_response():
    """Sample LLM response."""
    doc_id = str(uuid4())
    return {
        "answer": "Python is a high-level programming language [1].",
        "sources": [
            {
                "citation_num": 1,
                "chunk_id": "chunk1",
                "document_id": doc_id,
                "document_name": "python_guide.pdf",
                "chunk_index": 0,
                "rerank_score": 0.95,
            }
        ],
        "metadata": {
            "model": "anthropic/claude-3.5-sonnet",
            "temperature": 0.3,
            "tokens_used": {
                "prompt_tokens": 150,
                "completion_tokens": 50,
                "total_tokens": 200,
            },
            "timing": {"generation_ms": 1500.0},
        },
    }


def test_query_success(
    client,
    sample_hybrid_search_response,
    sample_rerank_response,
    sample_llm_response,
):
    """Test successful query processing."""
    with (
        patch("app.api.query.HybridSearchService") as MockHybridSearch,
        patch("app.api.query.RerankingService") as MockReranking,
        patch("app.api.query.LLMService") as MockLLM,
        patch("app.core.dependencies.get_supabase_client"),
    ):
        # Setup mocks
        mock_hybrid = MockHybridSearch.return_value
        mock_hybrid.search.return_value = sample_hybrid_search_response

        mock_rerank = MockReranking.return_value
        mock_rerank.rerank_with_metadata.return_value = sample_rerank_response

        mock_llm = MockLLM.return_value
        mock_llm.generate_answer_with_retry.return_value = sample_llm_response

        # Make request
        response = client.post("/api/query", json={"query": "What is Python?"})

        # Check response
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["answer"] == "Python is a high-level programming language [1]."
        assert len(data["sources"]) == 1
        assert data["sources"][0]["citation_num"] == 1
        assert data["sources"][0]["document_name"] == "python_guide.pdf"

        # Check metadata
        assert data["metadata"]["query"] == "What is Python?"
        assert data["metadata"]["model"] == "anthropic/claude-3.5-sonnet"
        assert data["metadata"]["tokens_used"]["total_tokens"] == 200
        assert "total_ms" in data["metadata"]["timing"]


def test_query_with_top_k(
    client,
    sample_hybrid_search_response,
    sample_rerank_response,
    sample_llm_response,
):
    """Test query with custom top_k."""
    with (
        patch("app.api.query.HybridSearchService") as MockHybridSearch,
        patch("app.api.query.RerankingService") as MockReranking,
        patch("app.api.query.LLMService") as MockLLM,
        patch("app.core.dependencies.get_supabase_client"),
    ):
        # Setup mocks
        mock_hybrid = MockHybridSearch.return_value
        mock_hybrid.search.return_value = sample_hybrid_search_response

        mock_rerank = MockReranking.return_value
        mock_rerank.rerank_with_metadata.return_value = sample_rerank_response

        mock_llm = MockLLM.return_value
        mock_llm.generate_answer_with_retry.return_value = sample_llm_response

        # Make request with custom top_k
        response = client.post(
            "/api/query", json={"query": "What is Python?", "top_k": 3}
        )

        assert response.status_code == 200

        # Verify rerank was called with correct top_k
        mock_rerank.rerank_with_metadata.assert_called_once()
        call_args = mock_rerank.rerank_with_metadata.call_args[1]
        assert call_args["top_k"] == 3


def test_query_with_document_id(
    client,
    sample_hybrid_search_response,
    sample_rerank_response,
    sample_llm_response,
):
    """Test query scoped to specific document."""
    doc_id = str(uuid4())

    with (
        patch("app.api.query.HybridSearchService") as MockHybridSearch,
        patch("app.api.query.RerankingService") as MockReranking,
        patch("app.api.query.LLMService") as MockLLM,
        patch("app.core.dependencies.get_supabase_client"),
    ):
        # Setup mocks
        mock_hybrid = MockHybridSearch.return_value
        mock_hybrid.search_by_document.return_value = sample_hybrid_search_response

        mock_rerank = MockReranking.return_value
        mock_rerank.rerank_with_metadata.return_value = sample_rerank_response

        mock_llm = MockLLM.return_value
        mock_llm.generate_answer_with_retry.return_value = sample_llm_response

        # Make request with document_id
        response = client.post(
            "/api/query",
            json={"query": "What is Python?", "document_id": doc_id},
        )

        assert response.status_code == 200

        # Verify search_by_document was called
        mock_hybrid.search_by_document.assert_called_once()
        call_args = mock_hybrid.search_by_document.call_args[1]
        assert call_args["document_id"] == doc_id


def test_query_no_results(client):
    """Test query when no search results found."""
    with (
        patch("app.api.query.HybridSearchService") as MockHybridSearch,
        patch("app.core.dependencies.get_supabase_client"),
    ):
        # Setup mock to return empty results
        mock_hybrid = MockHybridSearch.return_value
        mock_hybrid.search.return_value = {
            "results": [],
            "metadata": {"timing": {"total_ms": 100.0}},
        }

        # Make request
        response = client.post("/api/query", json={"query": "What is Python?"})

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "No relevant information found" in data["message"]
        assert len(data["sources"]) == 0


def test_query_invalid_request(client):
    """Test query with invalid request data."""
    # Empty query
    response = client.post("/api/query", json={"query": ""})
    assert response.status_code == 422  # Validation error

    # Query too long
    response = client.post("/api/query", json={"query": "x" * 1001})
    assert response.status_code == 422

    # Invalid top_k
    response = client.post("/api/query", json={"query": "test", "top_k": 0})
    assert response.status_code == 422

    response = client.post("/api/query", json={"query": "test", "top_k": 21})
    assert response.status_code == 422


def test_query_service_error(client):
    """Test query handling of service errors."""
    with (
        patch("app.api.query.HybridSearchService") as MockHybridSearch,
        patch("app.core.dependencies.get_supabase_client"),
    ):
        # Setup mock to raise error
        mock_hybrid = MockHybridSearch.return_value
        mock_hybrid.search.side_effect = Exception("Service error")

        # Make request
        response = client.post("/api/query", json={"query": "What is Python?"})

        assert response.status_code == 500
        data = response.json()
        # Check error response structure (from main.py exception handler)
        assert "error" in data or "detail" in data


def test_query_combines_timing_correctly(
    client,
    sample_hybrid_search_response,
    sample_rerank_response,
    sample_llm_response,
):
    """Test that query combines timing from all stages."""
    with (
        patch("app.api.query.HybridSearchService") as MockHybridSearch,
        patch("app.api.query.RerankingService") as MockReranking,
        patch("app.api.query.LLMService") as MockLLM,
        patch("app.core.dependencies.get_supabase_client"),
    ):
        # Setup mocks
        mock_hybrid = MockHybridSearch.return_value
        mock_hybrid.search.return_value = sample_hybrid_search_response

        mock_rerank = MockReranking.return_value
        mock_rerank.rerank_with_metadata.return_value = sample_rerank_response

        mock_llm = MockLLM.return_value
        mock_llm.generate_answer_with_retry.return_value = sample_llm_response

        # Make request
        response = client.post("/api/query", json={"query": "What is Python?"})

        data = response.json()
        timing = data["metadata"]["timing"]

        # Check that all timing components are present
        assert "vector_search_ms" in timing
        assert "fulltext_search_ms" in timing
        assert "rerank_ms" in timing
        assert "generation_ms" in timing
        assert "total_ms" in timing

        # Check total is sum of components
        expected_total = (
            sample_hybrid_search_response["metadata"]["timing"]["total_ms"]
            + sample_rerank_response["metadata"]["timing"]["rerank_ms"]
            + sample_llm_response["metadata"]["timing"]["generation_ms"]
        )
        assert timing["total_ms"] == expected_total


def test_query_preserves_all_scores(
    client,
    sample_hybrid_search_response,
    sample_rerank_response,
    sample_llm_response,
):
    """Test that query preserves all search scores in sources."""
    with (
        patch("app.api.query.HybridSearchService") as MockHybridSearch,
        patch("app.api.query.RerankingService") as MockReranking,
        patch("app.api.query.LLMService") as MockLLM,
        patch("app.core.dependencies.get_supabase_client"),
    ):
        # Setup mocks
        mock_hybrid = MockHybridSearch.return_value
        mock_hybrid.search.return_value = sample_hybrid_search_response

        mock_rerank = MockReranking.return_value
        mock_rerank.rerank_with_metadata.return_value = sample_rerank_response

        mock_llm = MockLLM.return_value
        mock_llm.generate_answer_with_retry.return_value = sample_llm_response

        # Make request
        response = client.post("/api/query", json={"query": "What is Python?"})

        data = response.json()
        source = data["sources"][0]

        # Check all scores are present
        assert source["rerank_score"] == 0.95
        assert source["rrf_score"] == 0.032
        assert source["vector_score"] == 0.9
        assert source["fulltext_score"] == 0.85
