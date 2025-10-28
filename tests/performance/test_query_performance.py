"""Performance benchmarks for query and retrieval."""

from unittest.mock import MagicMock, patch

import pytest
from app.services.rag import RAGService

pytestmark = pytest.mark.benchmark


@pytest.fixture
def rag_service():
    """Create RAG service instance."""
    return RAGService()


@pytest.mark.asyncio
async def test_query_processing_simple(benchmark, rag_service):
    """Benchmark simple query processing time."""
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch("app.services.retrieval.RetrievalService.hybrid_search") as mock_search,
        patch("cohere.Client") as mock_cohere,
        patch("requests.post") as mock_llm,
    ):
        # Setup mocks
        mock_embed.return_value = [0.1] * 768
        mock_search.return_value = [
            {
                "chunk_id": "1",
                "content": "Python is a programming language.",
                "document_name": "test.txt",
                "similarity": 0.9,
            }
        ]

        cohere_instance = mock_cohere.return_value
        cohere_instance.rerank.return_value = MagicMock(
            results=[MagicMock(index=0, relevance_score=0.95)]
        )

        mock_llm.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": "Python is a language [1]."}}],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 20,
                    "total_tokens": 70,
                },
            },
        )

        async def query():
            return await rag_service.query("What is Python?", top_k=3)

        result = await benchmark.pedantic(query, rounds=10, iterations=1)
        assert result is not None


@pytest.mark.asyncio
async def test_query_processing_complex(benchmark, rag_service):
    """Benchmark complex query processing with multiple results."""
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch("app.services.retrieval.RetrievalService.hybrid_search") as mock_search,
        patch("cohere.Client") as mock_cohere,
        patch("requests.post") as mock_llm,
    ):
        # Setup mocks with more results
        mock_embed.return_value = [0.1] * 768
        mock_search.return_value = [
            {
                "chunk_id": str(i),
                "content": f"Content chunk {i} about software engineering.",
                "document_name": "doc.txt",
                "similarity": 0.9 - (i * 0.05),
            }
            for i in range(10)
        ]

        cohere_instance = mock_cohere.return_value
        cohere_instance.rerank.return_value = MagicMock(
            results=[
                MagicMock(index=i, relevance_score=0.95 - (i * 0.05)) for i in range(10)
            ]
        )

        mock_llm.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [
                    {
                        "message": {
                            "content": "Detailed answer with citations [1][2][3]."
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 200,
                    "completion_tokens": 100,
                    "total_tokens": 300,
                },
            },
        )

        async def query():
            return await rag_service.query(
                "Explain software engineering best practices in detail", top_k=10
            )

        result = await benchmark.pedantic(query, rounds=10, iterations=1)
        assert result is not None


@pytest.mark.asyncio
async def test_embedding_generation(benchmark):
    """Benchmark embedding generation time."""
    from app.services.embeddings import EmbeddingService

    service = EmbeddingService()
    text = "This is a test query for embedding generation."

    async def generate():
        return await service.generate_embedding(text)

    # Note: This will actually call the real API, so use with caution
    # In production benchmarks, you might want to mock this
    with patch("app.services.embeddings.EmbeddingService.generate_embedding") as mock:
        mock.return_value = [0.1] * 768

        async def mock_generate():
            return mock.return_value

        result = await benchmark.pedantic(mock_generate, rounds=20, iterations=1)
        assert len(result) == 768


@pytest.mark.asyncio
async def test_reranking_performance(benchmark):
    """Benchmark reranking performance."""
    from app.services.reranking import RerankingService

    service = RerankingService()
    query = "What is machine learning?"
    documents = [
        "Machine learning is a subset of artificial intelligence.",
        "Deep learning uses neural networks with multiple layers.",
        "Python is a popular programming language.",
    ] * 5  # 15 documents

    with patch("cohere.Client") as mock_cohere:
        cohere_instance = mock_cohere.return_value
        cohere_instance.rerank.return_value = MagicMock(
            results=[
                MagicMock(index=i, relevance_score=0.95 - (i * 0.05))
                for i in range(len(documents))
            ]
        )

        def rerank():
            return service.rerank(query, documents, top_n=5)

        result = benchmark.pedantic(rerank, rounds=20, iterations=1)
        assert len(result) > 0
