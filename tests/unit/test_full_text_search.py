"""Tests for full-text search service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.full_text_search import FullTextSearchService


@pytest.fixture
def mock_db():
    """Mock DatabaseService."""
    mock = MagicMock()
    mock.fetch = AsyncMock()
    return mock


@pytest.fixture
def full_text_search_service(mock_db):
    """Create FullTextSearchService with mocked dependencies."""
    return FullTextSearchService(db=mock_db)


@pytest.fixture
def sample_search_results():
    """Sample search results from database."""
    doc_id = str(uuid4())
    return [
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "Python is a programming language.",
            "contextual_content": "Document: test.pdf\n\nPython is a programming language.",
            "rank": 0.95,
            "metadata": {"chunk_index": 0},
        },
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "Python has many libraries for data science.",
            "contextual_content": "Document: test.pdf\n\nPython has many libraries for data science.",
            "rank": 0.88,
            "metadata": {"chunk_index": 1},
        },
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "Programming in Python is efficient.",
            "contextual_content": "Document: test.pdf\n\nProgramming in Python is efficient.",
            "rank": 0.82,
            "metadata": {"chunk_index": 2},
        },
    ]


@pytest.mark.asyncio
async def test_search_success(full_text_search_service, mock_db, sample_search_results):
    """Test successful full-text search."""
    # Mock database fetch
    mock_db.fetch.return_value = sample_search_results

    results = await full_text_search_service.search(
        "Python programming", session_id="test-session"
    )

    assert len(results) == 3
    assert results[0]["relevance_score"] == 0.95
    assert results[0]["rank"] == 1
    assert results[1]["rank"] == 2
    assert results[2]["rank"] == 3

    # Verify database fetch was called
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_custom_limit(
    full_text_search_service, mock_db, sample_search_results
):
    """Test search with custom limit."""
    mock_db.fetch.return_value = sample_search_results[:2]

    results = await full_text_search_service.search(
        "Python", session_id="test-session", limit=2
    )

    assert len(results) == 2

    # Verify database fetch was called
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_no_results(full_text_search_service, mock_db):
    """Test search with no matching results."""
    mock_db.fetch.return_value = []

    results = await full_text_search_service.search(
        "nonexistent query", session_id="test-session"
    )

    assert results == []


@pytest.mark.asyncio
async def test_search_none_results(full_text_search_service, mock_db):
    """Test search when database returns None."""
    mock_db.fetch.return_value = None

    results = await full_text_search_service.search(
        "test query", session_id="test-session"
    )

    assert results == []


@pytest.mark.asyncio
async def test_search_formats_results_correctly(
    full_text_search_service, mock_db, sample_search_results
):
    """Test that search results are formatted correctly."""
    mock_db.fetch.return_value = sample_search_results

    results = await full_text_search_service.search("Python", session_id="test-session")

    # Check all expected fields are present
    for result in results:
        assert "chunk_id" in result
        assert "document_id" in result
        assert "content" in result
        assert "contextual_content" in result
        assert "relevance_score" in result
        assert "rank" in result
        assert "metadata" in result

    # Check rank ordering
    assert [r["rank"] for r in results] == [1, 2, 3]

    # Check relevance scores are floats
    assert all(isinstance(r["relevance_score"], float) for r in results)


@pytest.mark.asyncio
async def test_search_empty_query(full_text_search_service):
    """Test search with empty query."""
    with pytest.raises(DocumentProcessingError, match="Search query cannot be empty"):
        await full_text_search_service.search("", session_id="test-session")


@pytest.mark.asyncio
async def test_search_whitespace_query(full_text_search_service):
    """Test search with whitespace-only query."""
    with pytest.raises(DocumentProcessingError, match="Search query cannot be empty"):
        await full_text_search_service.search("   ", session_id="test-session")


@pytest.mark.asyncio
async def test_search_database_error(full_text_search_service, mock_db):
    """Test handling of database errors during search."""
    mock_db.fetch.side_effect = Exception("Database error")

    with pytest.raises(DocumentProcessingError, match="Full-text search failed"):
        await full_text_search_service.search("test query", session_id="test-session")


@pytest.mark.asyncio
async def test_search_by_document_success(
    full_text_search_service, mock_db, sample_search_results
):
    """Test successful search within a specific document."""
    document_id = str(uuid4())
    mock_db.fetch.return_value = sample_search_results

    results = await full_text_search_service.search_by_document(
        "Python", document_id, session_id="test-session"
    )

    assert len(results) == 3

    # Verify database fetch was called
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_by_document_custom_limit(
    full_text_search_service, mock_db, sample_search_results
):
    """Test search by document with custom limit."""
    document_id = str(uuid4())
    mock_db.fetch.return_value = sample_search_results[:2]

    results = await full_text_search_service.search_by_document(
        "Python", document_id, session_id="test-session", limit=2
    )

    assert len(results) == 2

    # Verify database fetch was called
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_by_document_no_results(full_text_search_service, mock_db):
    """Test search by document with no matching results."""
    document_id = str(uuid4())
    mock_db.fetch.return_value = []

    results = await full_text_search_service.search_by_document(
        "test query", document_id, session_id="test-session"
    )

    assert results == []


@pytest.mark.asyncio
async def test_search_by_document_empty_query(full_text_search_service):
    """Test search by document with empty query."""
    document_id = str(uuid4())

    with pytest.raises(DocumentProcessingError, match="Search query cannot be empty"):
        await full_text_search_service.search_by_document(
            "", document_id, session_id="test-session"
        )


@pytest.mark.asyncio
async def test_search_by_document_database_error(full_text_search_service, mock_db):
    """Test handling of database errors during search by document."""
    document_id = str(uuid4())
    mock_db.fetch.side_effect = Exception("Database error")

    with pytest.raises(
        DocumentProcessingError, match="Full-text search by document failed"
    ):
        await full_text_search_service.search_by_document(
            "test query", document_id, session_id="test-session"
        )


@pytest.mark.asyncio
async def test_search_uses_default_limit(
    full_text_search_service, mock_db, sample_search_results
):
    """Test that search uses default limit from config."""
    mock_db.fetch.return_value = sample_search_results

    await full_text_search_service.search("test query", session_id="test-session")

    # Verify database fetch was called
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_result_without_contextual_content(
    full_text_search_service, mock_db
):
    """Test handling of results without contextual_content field."""
    # Result without contextual_content
    result_data = [
        {
            "id": str(uuid4()),
            "document_id": str(uuid4()),
            "content": "Test content about Python",
            "rank": 0.9,
            "metadata": {},
        }
    ]

    mock_db.fetch.return_value = result_data

    results = await full_text_search_service.search("Python", session_id="test-session")

    # Should use content as fallback for contextual_content
    assert results[0]["contextual_content"] == "Test content about Python"


@pytest.mark.asyncio
async def test_search_result_without_metadata(full_text_search_service, mock_db):
    """Test handling of results without metadata field."""
    result_data = [
        {
            "id": str(uuid4()),
            "document_id": str(uuid4()),
            "content": "Test content",
            "contextual_content": "Context",
            "rank": 0.9,
        }
    ]

    mock_db.fetch.return_value = result_data

    results = await full_text_search_service.search("test", session_id="test-session")

    # Should use empty dict as default metadata
    assert results[0]["metadata"] == {}


@pytest.mark.asyncio
async def test_search_result_without_rank(full_text_search_service, mock_db):
    """Test handling of results without rank field."""
    result_data = [
        {
            "id": str(uuid4()),
            "document_id": str(uuid4()),
            "content": "Test content",
            "contextual_content": "Context",
            "metadata": {},
        }
    ]

    mock_db.fetch.return_value = result_data

    results = await full_text_search_service.search("test", session_id="test-session")

    # Should use 0.0 as default relevance score
    assert results[0]["relevance_score"] == 0.0


def test_service_initialization(mock_db):
    """Test that service initializes correctly."""
    service = FullTextSearchService(db=mock_db)

    assert service.db is mock_db


@pytest.mark.asyncio
async def test_search_logs_query(
    full_text_search_service, mock_db, sample_search_results, caplog
):
    """Test that search logs the query."""
    import logging

    caplog.set_level(logging.INFO)

    mock_db.fetch.return_value = sample_search_results

    await full_text_search_service.search(
        "Python programming query", session_id="test-session"
    )

    assert "Full-text search for query" in caplog.text
    assert "Python programming query" in caplog.text


@pytest.mark.asyncio
async def test_search_logs_results_count(
    full_text_search_service, mock_db, sample_search_results, caplog
):
    """Test that search logs the number of results found."""
    import logging

    caplog.set_level(logging.INFO)

    mock_db.fetch.return_value = sample_search_results

    await full_text_search_service.search("Python", session_id="test-session")

    assert "Found 3 results for full-text query" in caplog.text


@pytest.mark.asyncio
async def test_search_with_special_characters(
    full_text_search_service, mock_db, sample_search_results
):
    """Test search with special characters in query."""
    mock_db.fetch.return_value = sample_search_results

    # Query with special characters
    query = "Python & data-science | machine-learning"
    results = await full_text_search_service.search(query, session_id="test-session")

    assert len(results) == 3

    # Verify database fetch was called
    mock_db.fetch.assert_called_once()
