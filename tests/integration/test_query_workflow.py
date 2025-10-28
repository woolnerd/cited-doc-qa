"""Integration tests for query and retrieval workflow."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from app.core.dependencies import get_supabase_client
from app.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def client(supabase_client):
    """Create test client with real database."""
    app.dependency_overrides[get_supabase_client] = lambda: supabase_client
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def prepared_document(client, cleanup_test_data, sample_text_content):
    """Prepare a processed document for query tests."""
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch(
            "app.services.text_extraction.TextExtractor.extract_from_txt"
        ) as mock_extract,
    ):
        mock_extract.return_value = "Python is a programming language. It is widely used for data science and web development."
        mock_embed.return_value = [0.1] * 768

        # Upload
        files = {"file": ("python_doc.txt", BytesIO(sample_text_content), "text/plain")}
        upload_response = client.post("/api/documents/upload", files=files)
        document_id = upload_response.json()["document_id"]
        cleanup_test_data(document_id)

        # Process
        files = {"file": ("python_doc.txt", BytesIO(sample_text_content), "text/plain")}
        client.post(f"/api/documents/{document_id}/process", files=files)

        return document_id


@pytest.mark.slow
def test_query_retrieval_generation_flow(client, prepared_document):
    """Test complete query flow: query → search → rerank → generate.

    This integration test verifies:
    1. Query triggers hybrid search (vector + full-text)
    2. Results are retrieved from real database
    3. Reranking service processes results
    4. LLM generates answer with citations
    """
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch("cohere.Client") as MockCohere,
        patch("requests.post") as mock_llm,
    ):
        # Setup mocks for external APIs
        mock_embed.return_value = [0.1] * 768

        # Mock Cohere reranking
        mock_cohere = MockCohere.return_value
        mock_cohere.rerank.return_value = MagicMock(
            results=[
                MagicMock(index=0, relevance_score=0.95),
            ]
        )

        # Mock LLM response
        mock_llm.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [
                    {"message": {"content": "Python is a programming language [1]."}}
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

        # Execute query
        query_response = client.post(
            "/api/query",
            json={"query": "What is Python?", "top_k": 3},
        )

        # Verify response
        assert query_response.status_code == 200
        data = query_response.json()

        assert data["success"] is True
        assert "answer" in data
        assert len(data["sources"]) > 0
        assert data["metadata"]["query"] == "What is Python?"

        # Verify sources have proper structure
        source = data["sources"][0]
        assert "citation_num" in source
        assert "document_name" in source
        assert "content" in source
        assert "rerank_score" in source


@pytest.mark.slow
def test_query_with_no_results(client):
    """Test query when no relevant documents exist."""
    with patch(
        "app.services.embeddings.EmbeddingService.generate_embedding"
    ) as mock_embed:
        mock_embed.return_value = [0.1] * 768

        # Query for something that doesn't exist
        query_response = client.post(
            "/api/query",
            json={"query": "quantum mechanics in underwater basket weaving"},
        )

        assert query_response.status_code == 200
        data = query_response.json()
        assert data["success"] is True
        assert len(data["sources"]) == 0


@pytest.mark.slow
def test_query_with_specific_document(client, prepared_document):
    """Test querying scoped to a specific document."""
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch("cohere.Client") as MockCohere,
        patch("requests.post") as mock_llm,
    ):
        mock_embed.return_value = [0.1] * 768

        # Mock reranking
        mock_cohere = MockCohere.return_value
        mock_cohere.rerank.return_value = MagicMock(
            results=[MagicMock(index=0, relevance_score=0.9)]
        )

        # Mock LLM
        mock_llm.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": "Answer from document [1]."}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

        # Query specific document
        query_response = client.post(
            "/api/query",
            json={
                "query": "What is this about?",
                "document_id": prepared_document,
                "top_k": 5,
            },
        )

        assert query_response.status_code == 200
        data = query_response.json()
        assert data["success"] is True


@pytest.mark.slow
def test_concurrent_queries(client, prepared_document):
    """Test multiple concurrent queries don't interfere."""
    import concurrent.futures

    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch("cohere.Client") as MockCohere,
        patch("requests.post") as mock_llm,
    ):
        mock_embed.return_value = [0.1] * 768

        mock_cohere = MockCohere.return_value
        mock_cohere.rerank.return_value = MagicMock(
            results=[MagicMock(index=0, relevance_score=0.9)]
        )

        mock_llm.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": "Concurrent answer [1]."}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

        def make_query(query_text):
            response = client.post("/api/query", json={"query": query_text})
            return response.status_code == 200

        # Execute multiple queries concurrently
        queries = [f"Query {i}" for i in range(5)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(make_query, queries))

        # All should succeed
        assert all(results), "All concurrent queries should succeed"
