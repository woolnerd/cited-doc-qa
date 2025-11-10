"""Tests for hybrid search service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.hybrid_search import HybridSearchService


@pytest.fixture
def mock_db():
    """Mock DatabaseService."""
    mock = MagicMock()
    mock.fetch = AsyncMock()
    return mock


@pytest.fixture
def mock_embedding_service():
    """Mock EmbeddingService."""
    mock = MagicMock()
    mock.generate_query_embedding.return_value = [0.1] * 768
    return mock


@pytest.fixture
def mock_vector_search():
    """Mock VectorSearchService."""
    mock = MagicMock()
    mock.search = AsyncMock()
    mock.search_by_document = AsyncMock()
    return mock


@pytest.fixture
def mock_fulltext_search():
    """Mock FullTextSearchService."""
    mock = MagicMock()
    mock.search = AsyncMock()
    mock.search_by_document = AsyncMock()
    return mock


@pytest.fixture
def hybrid_search_service(
    mock_db, mock_embedding_service, mock_vector_search, mock_fulltext_search
):
    """Create HybridSearchService with mocked dependencies."""
    return HybridSearchService(
        db=mock_db,
        embedding_service=mock_embedding_service,
        vector_search_service=mock_vector_search,
        full_text_search_service=mock_fulltext_search,
    )


@pytest.fixture
def sample_vector_results():
    """Sample results from vector search."""
    doc_id = str(uuid4())
    return [
        {
            "chunk_id": "chunk1",
            "document_id": doc_id,
            "content": "Python is a programming language.",
            "contextual_content": "Document: test.pdf\n\nPython is a programming language.",
            "similarity_score": 0.95,
            "rank": 1,
            "metadata": {"chunk_index": 0},
        },
        {
            "chunk_id": "chunk2",
            "document_id": doc_id,
            "content": "Machine learning with Python.",
            "contextual_content": "Document: test.pdf\n\nMachine learning with Python.",
            "similarity_score": 0.88,
            "rank": 2,
            "metadata": {"chunk_index": 1},
        },
        {
            "chunk_id": "chunk3",
            "document_id": doc_id,
            "content": "Data science applications.",
            "contextual_content": "Document: test.pdf\n\nData science applications.",
            "similarity_score": 0.82,
            "rank": 3,
            "metadata": {"chunk_index": 2},
        },
    ]


@pytest.fixture
def sample_fulltext_results():
    """Sample results from full-text search."""
    doc_id = str(uuid4())
    return [
        {
            "chunk_id": "chunk2",  # Overlaps with vector results
            "document_id": doc_id,
            "content": "Machine learning with Python.",
            "contextual_content": "Document: test.pdf\n\nMachine learning with Python.",
            "relevance_score": 0.9,
            "rank": 1,
            "metadata": {"chunk_index": 1},
        },
        {
            "chunk_id": "chunk4",
            "document_id": doc_id,
            "content": "Python programming best practices.",
            "contextual_content": "Document: test.pdf\n\nPython programming best practices.",
            "relevance_score": 0.85,
            "rank": 2,
            "metadata": {"chunk_index": 3},
        },
        {
            "chunk_id": "chunk1",  # Overlaps with vector results
            "document_id": doc_id,
            "content": "Python is a programming language.",
            "contextual_content": "Document: test.pdf\n\nPython is a programming language.",
            "relevance_score": 0.80,
            "rank": 3,
            "metadata": {"chunk_index": 0},
        },
    ]


def test_calculate_rrf_score(hybrid_search_service):
    """Test RRF score calculation."""
    # With default k=60
    score1 = hybrid_search_service._calculate_rrf_score(1)
    assert score1 == 1.0 / 61

    score2 = hybrid_search_service._calculate_rrf_score(2)
    assert score2 == 1.0 / 62

    # Test with custom k
    score_custom = hybrid_search_service._calculate_rrf_score(1, k=10)
    assert score_custom == 1.0 / 11


def test_merge_results_with_overlap(
    hybrid_search_service, sample_vector_results, sample_fulltext_results
):
    """Test merging results when there's overlap between searches."""
    merged = hybrid_search_service._merge_results(
        sample_vector_results, sample_fulltext_results
    )

    # Should have 4 unique chunks (chunk1, chunk2, chunk3, chunk4)
    assert len(merged) == 4

    # Check that overlapping chunks have combined scores
    chunk2 = next(r for r in merged if r["chunk_id"] == "chunk2")
    assert chunk2["source"] == "both"
    assert chunk2["vector_score"] == 0.88
    assert chunk2["fulltext_score"] == 0.9
    assert chunk2["vector_rank"] == 2
    assert chunk2["fulltext_rank"] == 1
    # RRF score should be sum of both ranks
    assert chunk2["rrf_score"] == (1.0 / 62) + (1.0 / 61)

    chunk1 = next(r for r in merged if r["chunk_id"] == "chunk1")
    assert chunk1["source"] == "both"
    assert chunk1["vector_score"] == 0.95
    assert chunk1["fulltext_score"] == 0.80


def test_merge_results_vector_only(hybrid_search_service, sample_vector_results):
    """Test merging when there are only vector results."""
    merged = hybrid_search_service._merge_results(sample_vector_results, [])

    assert len(merged) == 3
    for result in merged:
        assert result["source"] == "vector"
        assert result["vector_score"] is not None
        assert result["fulltext_score"] is None
        assert result["fulltext_rank"] is None


def test_merge_results_fulltext_only(hybrid_search_service, sample_fulltext_results):
    """Test merging when there are only full-text results."""
    merged = hybrid_search_service._merge_results([], sample_fulltext_results)

    assert len(merged) == 3
    for result in merged:
        assert result["source"] == "fulltext"
        assert result["vector_score"] is None
        assert result["fulltext_score"] is not None
        assert result["vector_rank"] is None


def test_merge_results_no_overlap(hybrid_search_service):
    """Test merging when there's no overlap between searches."""
    vector_results = [
        {
            "chunk_id": "chunk1",
            "document_id": str(uuid4()),
            "content": "Content 1",
            "contextual_content": "Context 1",
            "similarity_score": 0.9,
            "rank": 1,
            "metadata": {},
        }
    ]

    fulltext_results = [
        {
            "chunk_id": "chunk2",
            "document_id": str(uuid4()),
            "content": "Content 2",
            "contextual_content": "Context 2",
            "relevance_score": 0.85,
            "rank": 1,
            "metadata": {},
        }
    ]

    merged = hybrid_search_service._merge_results(vector_results, fulltext_results)

    assert len(merged) == 2
    assert merged[0]["source"] in ["vector", "fulltext"]
    assert merged[1]["source"] in ["vector", "fulltext"]


def test_merge_results_sorting(
    hybrid_search_service, sample_vector_results, sample_fulltext_results
):
    """Test that merged results are sorted by RRF score."""
    merged = hybrid_search_service._merge_results(
        sample_vector_results, sample_fulltext_results
    )

    # Check results are sorted by RRF score (descending)
    for i in range(len(merged) - 1):
        assert merged[i]["rrf_score"] >= merged[i + 1]["rrf_score"]

    # Check final ranks are assigned correctly
    for idx, result in enumerate(merged):
        assert result["final_rank"] == idx + 1


@pytest.mark.asyncio
async def test_search_success(
    hybrid_search_service,
    mock_vector_search,
    mock_fulltext_search,
    sample_vector_results,
    sample_fulltext_results,
):
    """Test successful hybrid search."""
    mock_vector_search.search.return_value = sample_vector_results
    mock_fulltext_search.search.return_value = sample_fulltext_results

    result = await hybrid_search_service.search("test query", session_id="test-session")

    # Check structure
    assert "results" in result
    assert "metadata" in result

    # Check results
    assert len(result["results"]) == 4  # 4 unique chunks

    # Check metadata
    metadata = result["metadata"]
    assert metadata["total_results"] == 4
    assert metadata["vector_results_count"] == 3
    assert metadata["fulltext_results_count"] == 3
    assert metadata["merged_results_count"] == 4
    assert "sources" in metadata
    assert "timing" in metadata
    assert metadata["query"] == "test query"

    # Check timing metrics
    timing = metadata["timing"]
    assert "vector_search_ms" in timing
    assert "fulltext_search_ms" in timing
    assert "total_ms" in timing

    # Verify both searches were called
    mock_vector_search.search.assert_called_once()
    mock_fulltext_search.search.assert_called_once()


@pytest.mark.asyncio
async def test_search_with_custom_limits(
    hybrid_search_service, mock_vector_search, mock_fulltext_search
):
    """Test search with custom limits."""
    mock_vector_search.search.return_value = []
    mock_fulltext_search.search.return_value = []

    await hybrid_search_service.search(
        "test query",
        session_id="test-session",
        top_k=10,
        vector_limit=20,
        fulltext_limit=25,
    )

    # Check that limits were passed correctly
    vector_call = mock_vector_search.search.call_args
    assert vector_call[1]["top_k"] == 20

    fulltext_call = mock_fulltext_search.search.call_args
    assert fulltext_call[1]["limit"] == 25


@pytest.mark.asyncio
async def test_search_top_k_limiting(
    hybrid_search_service,
    mock_vector_search,
    mock_fulltext_search,
    sample_vector_results,
    sample_fulltext_results,
):
    """Test that top_k limits final results."""
    mock_vector_search.search.return_value = sample_vector_results
    mock_fulltext_search.search.return_value = sample_fulltext_results

    result = await hybrid_search_service.search(
        "test query", session_id="test-session", top_k=2
    )

    # Should only return top 2 results
    assert len(result["results"]) == 2
    assert result["metadata"]["total_results"] == 2
    assert result["metadata"]["merged_results_count"] == 4  # Before limiting


@pytest.mark.asyncio
async def test_search_sources_tracking(
    hybrid_search_service,
    mock_vector_search,
    mock_fulltext_search,
    sample_vector_results,
    sample_fulltext_results,
):
    """Test that source provenance is tracked correctly."""
    mock_vector_search.search.return_value = sample_vector_results
    mock_fulltext_search.search.return_value = sample_fulltext_results

    result = await hybrid_search_service.search("test query", session_id="test-session")

    sources = result["metadata"]["sources"]
    assert "vector_only" in sources
    assert "fulltext_only" in sources
    assert "both" in sources

    # chunk1 and chunk2 appear in both searches
    assert sources["both"] == 2
    # chunk3 only in vector
    assert sources["vector_only"] == 1
    # chunk4 only in fulltext
    assert sources["fulltext_only"] == 1


@pytest.mark.asyncio
async def test_search_empty_vector_results(
    hybrid_search_service,
    mock_vector_search,
    mock_fulltext_search,
    sample_fulltext_results,
):
    """Test search when vector search returns no results."""
    mock_vector_search.search.return_value = []
    mock_fulltext_search.search.return_value = sample_fulltext_results

    result = await hybrid_search_service.search("test query", session_id="test-session")

    assert len(result["results"]) == 3
    assert result["metadata"]["vector_results_count"] == 0
    assert result["metadata"]["fulltext_results_count"] == 3

    # All results should be from fulltext only
    for res in result["results"]:
        assert res["source"] == "fulltext"


@pytest.mark.asyncio
async def test_search_empty_fulltext_results(
    hybrid_search_service,
    mock_vector_search,
    mock_fulltext_search,
    sample_vector_results,
):
    """Test search when full-text search returns no results."""
    mock_vector_search.search.return_value = sample_vector_results
    mock_fulltext_search.search.return_value = []

    result = await hybrid_search_service.search("test query", session_id="test-session")

    assert len(result["results"]) == 3
    assert result["metadata"]["vector_results_count"] == 3
    assert result["metadata"]["fulltext_results_count"] == 0

    # All results should be from vector only
    for res in result["results"]:
        assert res["source"] == "vector"


@pytest.mark.asyncio
async def test_search_both_empty(
    hybrid_search_service, mock_vector_search, mock_fulltext_search
):
    """Test search when both searches return no results."""
    mock_vector_search.search.return_value = []
    mock_fulltext_search.search.return_value = []

    result = await hybrid_search_service.search("test query", session_id="test-session")

    assert len(result["results"]) == 0
    assert result["metadata"]["total_results"] == 0
    assert result["metadata"]["vector_results_count"] == 0
    assert result["metadata"]["fulltext_results_count"] == 0


@pytest.mark.asyncio
async def test_search_error_handling(
    hybrid_search_service, mock_vector_search, mock_fulltext_search
):
    """Test error handling during search."""
    mock_vector_search.search.side_effect = Exception("Search error")

    with pytest.raises(DocumentProcessingError, match="Hybrid search failed"):
        await hybrid_search_service.search("test query", session_id="test-session")


@pytest.mark.asyncio
async def test_search_by_document_success(
    hybrid_search_service,
    mock_vector_search,
    mock_fulltext_search,
    sample_vector_results,
    sample_fulltext_results,
):
    """Test successful hybrid search by document."""
    document_id = str(uuid4())
    mock_vector_search.search_by_document.return_value = sample_vector_results
    mock_fulltext_search.search_by_document.return_value = sample_fulltext_results

    result = await hybrid_search_service.search_by_document(
        "test query", document_id, session_id="test-session"
    )

    # Check structure
    assert "results" in result
    assert "metadata" in result
    assert result["metadata"]["document_id"] == document_id

    # Verify both searches were called with document_id
    mock_vector_search.search_by_document.assert_called_once()
    vector_call = mock_vector_search.search_by_document.call_args
    assert vector_call[1]["document_id"] == document_id

    mock_fulltext_search.search_by_document.assert_called_once()
    fulltext_call = mock_fulltext_search.search_by_document.call_args
    assert fulltext_call[1]["document_id"] == document_id


@pytest.mark.asyncio
async def test_search_by_document_with_limits(
    hybrid_search_service, mock_vector_search, mock_fulltext_search
):
    """Test search by document with custom limits."""
    document_id = str(uuid4())
    mock_vector_search.search_by_document.return_value = []
    mock_fulltext_search.search_by_document.return_value = []

    await hybrid_search_service.search_by_document(
        "test query",
        document_id,
        session_id="test-session",
        top_k=10,
        vector_limit=20,
        fulltext_limit=25,
    )

    # Check that limits were passed correctly
    vector_call = mock_vector_search.search_by_document.call_args
    assert vector_call[1]["top_k"] == 20

    fulltext_call = mock_fulltext_search.search_by_document.call_args
    assert fulltext_call[1]["limit"] == 25


@pytest.mark.asyncio
async def test_search_by_document_error_handling(
    hybrid_search_service, mock_vector_search, mock_fulltext_search
):
    """Test error handling during search by document."""
    document_id = str(uuid4())
    mock_fulltext_search.search_by_document.side_effect = Exception("Search error")

    with pytest.raises(
        DocumentProcessingError, match="Hybrid search by document failed"
    ):
        await hybrid_search_service.search_by_document(
            "test query", document_id, session_id="test-session"
        )


def test_service_initialization(mock_db):
    """Test that service initializes correctly with minimal dependencies."""
    service = HybridSearchService(db=mock_db)

    assert service.db is mock_db
    assert service.embedding_service is not None
    assert service.vector_search is not None
    assert service.full_text_search is not None


def test_service_initialization_with_all_dependencies(
    mock_db, mock_embedding_service, mock_vector_search, mock_fulltext_search
):
    """Test that service uses provided dependencies."""
    service = HybridSearchService(
        db=mock_db,
        embedding_service=mock_embedding_service,
        vector_search_service=mock_vector_search,
        full_text_search_service=mock_fulltext_search,
    )

    assert service.embedding_service is mock_embedding_service
    assert service.vector_search is mock_vector_search
    assert service.full_text_search is mock_fulltext_search


@pytest.mark.asyncio
async def test_search_logs_query(
    hybrid_search_service,
    mock_vector_search,
    mock_fulltext_search,
    sample_vector_results,
    caplog,
):
    """Test that search logs the query and results."""
    import logging

    caplog.set_level(logging.INFO)

    mock_vector_search.search.return_value = sample_vector_results
    mock_fulltext_search.search.return_value = []

    await hybrid_search_service.search(
        "test query for logging", session_id="test-session"
    )

    assert "Hybrid search for query" in caplog.text
    assert "test query for logging" in caplog.text
    assert "Hybrid search completed" in caplog.text


@pytest.mark.asyncio
async def test_search_logs_timing(
    hybrid_search_service,
    mock_vector_search,
    mock_fulltext_search,
    sample_vector_results,
    sample_fulltext_results,
    caplog,
):
    """Test that search logs timing information."""
    import logging

    caplog.set_level(logging.INFO)

    mock_vector_search.search.return_value = sample_vector_results
    mock_fulltext_search.search.return_value = sample_fulltext_results

    await hybrid_search_service.search("test query", session_id="test-session")

    assert "Vector search:" in caplog.text
    assert "results in" in caplog.text
    assert "Full-text search:" in caplog.text
