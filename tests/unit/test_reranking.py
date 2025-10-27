"""Tests for reranking service."""

from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.reranking import RerankingService
from cohere.core.api_error import ApiError as CohereApiError


# Create a simple exception class for testing that properly inherits from Exception
class MockCohereError(Exception):
    """Mock Cohere error for testing."""

    pass


@pytest.fixture
def mock_cohere_client():
    """Mock Cohere client."""
    with patch("app.services.reranking.cohere.ClientV2") as mock_client:
        client_instance = MagicMock()
        mock_client.return_value = client_instance
        yield client_instance


@pytest.fixture
def reranking_service(mock_cohere_client):
    """Create RerankingService with mocked Cohere client."""
    return RerankingService(api_key="test-api-key")


@pytest.fixture
def sample_search_results():
    """Sample search results from hybrid search."""
    doc_id = str(uuid4())
    return [
        {
            "chunk_id": "chunk1",
            "document_id": doc_id,
            "content": "Python is a programming language.",
            "contextual_content": "Document: test.pdf\n\nPython is a programming language.",
            "rrf_score": 0.032,
            "final_rank": 1,
            "metadata": {"chunk_index": 0},
        },
        {
            "chunk_id": "chunk2",
            "document_id": doc_id,
            "content": "Machine learning with Python.",
            "contextual_content": "Document: test.pdf\n\nMachine learning with Python.",
            "rrf_score": 0.030,
            "final_rank": 2,
            "metadata": {"chunk_index": 1},
        },
        {
            "chunk_id": "chunk3",
            "document_id": doc_id,
            "content": "Data science applications.",
            "contextual_content": "Document: test.pdf\n\nData science applications.",
            "rrf_score": 0.028,
            "final_rank": 3,
            "metadata": {"chunk_index": 2},
        },
    ]


@pytest.fixture
def mock_rerank_response():
    """Mock successful Cohere rerank response."""
    response = Mock()
    response.results = [
        Mock(index=1, relevance_score=0.95),  # chunk2 ranked first
        Mock(index=0, relevance_score=0.88),  # chunk1 ranked second
        Mock(index=2, relevance_score=0.75),  # chunk3 ranked third
    ]
    return response


def test_service_initialization_success(mock_cohere_client):
    """Test successful service initialization."""
    service = RerankingService(api_key="test-key")

    assert service.api_key == "test-key"
    assert service.client is mock_cohere_client
    assert service.model == "rerank-english-v3.0"


def test_service_initialization_uses_settings(mock_cohere_client):
    """Test that service uses settings when no API key provided."""
    service = RerankingService()

    # Just verify that an API key was set from settings
    assert service.api_key is not None
    assert len(service.api_key) > 0


def test_service_initialization_failure():
    """Test handling of initialization failure."""
    with patch(
        "app.services.reranking.cohere.ClientV2",
        side_effect=Exception("API error"),
    ):
        with pytest.raises(
            DocumentProcessingError, match="Failed to initialize Cohere client"
        ):
            RerankingService(api_key="test-key")


def test_exponential_backoff(reranking_service):
    """Test exponential backoff calculation."""
    # With default retry_delay of 1.0
    assert reranking_service._exponential_backoff(0) == 1.0
    assert reranking_service._exponential_backoff(1) == 2.0
    assert reranking_service._exponential_backoff(2) == 4.0
    assert reranking_service._exponential_backoff(3) == 8.0


def test_rerank_success(
    reranking_service, mock_cohere_client, sample_search_results, mock_rerank_response
):
    """Test successful reranking."""
    mock_cohere_client.rerank.return_value = mock_rerank_response

    results = reranking_service.rerank("test query", sample_search_results)

    # Check that rerank was called correctly
    mock_cohere_client.rerank.assert_called_once()
    call_args = mock_cohere_client.rerank.call_args[1]
    assert call_args["model"] == "rerank-english-v3.0"
    assert call_args["query"] == "test query"
    assert len(call_args["documents"]) == 3
    assert call_args["top_n"] == 3  # min(top_k=5, len(results)=3)

    # Check reranked results
    assert len(results) == 3

    # First result should be chunk2 (index 1 in original, highest relevance)
    assert results[0]["chunk_id"] == "chunk2"
    assert results[0]["rerank_score"] == 0.95
    assert results[0]["rerank_rank"] == 1
    assert results[0]["original_rank"] == 2

    # Second result should be chunk1
    assert results[1]["chunk_id"] == "chunk1"
    assert results[1]["rerank_score"] == 0.88
    assert results[1]["rerank_rank"] == 2

    # Third result should be chunk3
    assert results[2]["chunk_id"] == "chunk3"
    assert results[2]["rerank_score"] == 0.75
    assert results[2]["rerank_rank"] == 3


def test_rerank_empty_results(reranking_service):
    """Test reranking with empty results list."""
    results = reranking_service.rerank("test query", [])

    assert results == []


def test_rerank_custom_top_k(
    reranking_service, mock_cohere_client, sample_search_results
):
    """Test reranking with custom top_k."""
    mock_response = Mock()
    mock_response.results = [
        Mock(index=1, relevance_score=0.95),
        Mock(index=0, relevance_score=0.88),
    ]
    mock_cohere_client.rerank.return_value = mock_response

    results = reranking_service.rerank("test query", sample_search_results, top_k=2)

    # Check that top_n was set correctly
    call_args = mock_cohere_client.rerank.call_args[1]
    assert call_args["top_n"] == 2

    assert len(results) == 2


def test_rerank_uses_contextual_content(
    reranking_service, mock_cohere_client, sample_search_results, mock_rerank_response
):
    """Test that reranking uses contextual_content for better accuracy."""
    mock_cohere_client.rerank.return_value = mock_rerank_response

    reranking_service.rerank("test query", sample_search_results)

    call_args = mock_cohere_client.rerank.call_args[1]
    documents = call_args["documents"]

    # Check that contextual_content was used
    assert "Document: test.pdf" in documents[0]
    assert "Python is a programming language." in documents[0]


def test_rerank_retry_on_cohere_error(
    reranking_service, mock_cohere_client, sample_search_results, mock_rerank_response
):
    """Test retry logic on Cohere API error."""
    # Fail first two attempts, succeed on third
    # Use real Exception objects that can be raised
    api_error1 = MockCohereError("API error 1")
    api_error2 = MockCohereError("API error 2")
    mock_cohere_client.rerank.side_effect = [
        api_error1,
        api_error2,
        mock_rerank_response,
    ]

    # Patch isinstance to make MockCohereError be recognized as CohereApiError
    with (
        patch("time.sleep"),
        patch(
            "app.services.reranking.isinstance",
            side_effect=lambda obj, cls: (
                isinstance(obj, MockCohereError)
                if cls == CohereApiError
                else isinstance(obj, cls)
            ),
        ),
    ):
        results = reranking_service.rerank("test query", sample_search_results)

    # Should have succeeded on third attempt
    assert len(results) == 3
    assert mock_cohere_client.rerank.call_count == 3


def test_rerank_fallback_after_max_retries(
    reranking_service, mock_cohere_client, sample_search_results
):
    """Test fallback to RRF scores after max retries exceeded."""
    # Fail all attempts
    api_error = MockCohereError("API error")
    mock_cohere_client.rerank.side_effect = api_error

    with (
        patch("time.sleep"),
        patch(
            "app.services.reranking.isinstance",
            side_effect=lambda obj, cls: (
                isinstance(obj, MockCohereError)
                if cls == CohereApiError
                else isinstance(obj, cls)
            ),
        ),
    ):
        results = reranking_service.rerank("test query", sample_search_results)

    # Should have fallen back to RRF scores
    assert len(results) == 3  # Returns top_k=5, but only 3 results available
    assert mock_cohere_client.rerank.call_count == 3  # max_retries

    # Results should be sorted by RRF score
    assert results[0]["chunk_id"] == "chunk1"  # Highest RRF score (0.032)
    assert results[1]["chunk_id"] == "chunk2"  # Second (0.030)
    assert results[2]["chunk_id"] == "chunk3"  # Third (0.028)

    # Check fallback indicators
    for result in results:
        assert result["rerank_score"] is None
        assert result["rerank_fallback"] is True


def test_rerank_fallback_on_unexpected_error(
    reranking_service, mock_cohere_client, sample_search_results
):
    """Test fallback on unexpected non-Cohere error."""
    # Unexpected error
    mock_cohere_client.rerank.side_effect = Exception("Unexpected error")

    with patch("time.sleep"):
        results = reranking_service.rerank("test query", sample_search_results)

    # Should have fallen back to RRF scores
    assert len(results) == 3
    assert all(r.get("rerank_fallback") for r in results)


def test_fallback_to_rrf(reranking_service, sample_search_results):
    """Test _fallback_to_rrf method directly."""
    results = reranking_service._fallback_to_rrf(sample_search_results, top_k=2)

    # Should return top 2 by RRF score
    assert len(results) == 2
    assert results[0]["chunk_id"] == "chunk1"  # Highest RRF
    assert results[1]["chunk_id"] == "chunk2"  # Second highest

    # Check fallback indicators
    for result in results:
        assert result["rerank_score"] is None
        assert result["rerank_fallback"] is True
        assert "rerank_rank" in result
        assert "original_rank" in result


def test_rerank_with_metadata_success(
    reranking_service, mock_cohere_client, sample_search_results, mock_rerank_response
):
    """Test rerank_with_metadata returns correct structure."""
    mock_cohere_client.rerank.return_value = mock_rerank_response

    result = reranking_service.rerank_with_metadata(
        "test query", sample_search_results, top_k=3
    )

    # Check structure
    assert "results" in result
    assert "metadata" in result

    # Check results
    assert len(result["results"]) == 3

    # Check metadata
    metadata = result["metadata"]
    assert metadata["total_results"] == 3
    assert metadata["input_results_count"] == 3
    assert metadata["query"] == "test query"
    assert metadata["top_k"] == 3
    assert metadata["model"] == "rerank-english-v3.0"
    assert metadata["used_fallback"] is False
    assert "timing" in metadata
    assert "rerank_ms" in metadata["timing"]


def test_rerank_with_metadata_fallback(
    reranking_service, mock_cohere_client, sample_search_results
):
    """Test rerank_with_metadata indicates fallback was used."""
    api_error = MockCohereError("API error")
    mock_cohere_client.rerank.side_effect = api_error

    with (
        patch("time.sleep"),
        patch(
            "app.services.reranking.isinstance",
            side_effect=lambda obj, cls: (
                isinstance(obj, MockCohereError)
                if cls == CohereApiError
                else isinstance(obj, cls)
            ),
        ),
    ):
        result = reranking_service.rerank_with_metadata(
            "test query", sample_search_results
        )

    # Check that fallback was indicated
    assert result["metadata"]["used_fallback"] is True


def test_rerank_preserves_original_fields(
    reranking_service, mock_cohere_client, mock_rerank_response
):
    """Test that reranking preserves all original result fields."""
    results_with_extra_fields = [
        {
            "chunk_id": "chunk1",
            "document_id": str(uuid4()),
            "content": "Test content",
            "contextual_content": "Test context",
            "rrf_score": 0.032,
            "final_rank": 1,
            "vector_score": 0.9,
            "fulltext_score": 0.85,
            "source": "both",
            "custom_field": "custom_value",
        }
    ]

    mock_response = Mock()
    mock_response.results = [Mock(index=0, relevance_score=0.95)]
    mock_cohere_client.rerank.return_value = mock_response

    results = reranking_service.rerank("test query", results_with_extra_fields)

    # Check that all original fields are preserved
    assert results[0]["chunk_id"] == "chunk1"
    assert results[0]["vector_score"] == 0.9
    assert results[0]["fulltext_score"] == 0.85
    assert results[0]["source"] == "both"
    assert results[0]["custom_field"] == "custom_value"

    # Check that new fields were added
    assert results[0]["rerank_score"] == 0.95
    assert results[0]["rerank_rank"] == 1


def test_rerank_logs_query(
    reranking_service,
    mock_cohere_client,
    sample_search_results,
    mock_rerank_response,
    caplog,
):
    """Test that reranking logs the query and results."""
    import logging

    caplog.set_level(logging.INFO)

    mock_cohere_client.rerank.return_value = mock_rerank_response

    reranking_service.rerank("test query for logging", sample_search_results)

    assert "Reranking 3 results for query" in caplog.text
    assert "test query for logging" in caplog.text
    assert "Reranking completed" in caplog.text


def test_rerank_logs_retry_attempts(
    reranking_service,
    mock_cohere_client,
    sample_search_results,
    mock_rerank_response,
    caplog,
):
    """Test that retry attempts are logged."""
    import logging

    caplog.set_level(logging.INFO)

    # Fail first attempt, succeed on second
    api_error = MockCohereError("API error")
    mock_cohere_client.rerank.side_effect = [
        api_error,
        mock_rerank_response,
    ]

    with (
        patch("time.sleep"),
        patch(
            "app.services.reranking.isinstance",
            side_effect=lambda obj, cls: (
                isinstance(obj, MockCohereError)
                if cls == CohereApiError
                else isinstance(obj, cls)
            ),
        ),
    ):
        reranking_service.rerank("test query", sample_search_results)

    # Check that error was logged and retry happened
    assert (
        "Cohere API error on attempt 1" in caplog.text
        or "Unexpected error during reranking on attempt 1" in caplog.text
    )
    assert "Retrying in" in caplog.text
    assert "Reranking successful on attempt 2" in caplog.text


def test_rerank_logs_fallback(
    reranking_service, mock_cohere_client, sample_search_results, caplog
):
    """Test that fallback is logged."""
    import logging

    caplog.set_level(logging.INFO)

    api_error = MockCohereError("API error")
    mock_cohere_client.rerank.side_effect = api_error

    with (
        patch("time.sleep"),
        patch(
            "app.services.reranking.isinstance",
            side_effect=lambda obj, cls: (
                isinstance(obj, MockCohereError)
                if cls == CohereApiError
                else isinstance(obj, cls)
            ),
        ),
    ):
        reranking_service.rerank("test query", sample_search_results)

    assert "Reranking failed after 3 attempts" in caplog.text
    assert "falling back to RRF scores" in caplog.text
    assert "Using fallback" in caplog.text


def test_rerank_handles_missing_contextual_content(
    reranking_service, mock_cohere_client, mock_rerank_response
):
    """Test that reranking handles results without contextual_content."""
    results_without_contextual = [
        {
            "chunk_id": "chunk1",
            "document_id": str(uuid4()),
            "content": "Test content without contextual",
            "rrf_score": 0.032,
            "final_rank": 1,
        }
    ]

    mock_response = Mock()
    mock_response.results = [Mock(index=0, relevance_score=0.95)]
    mock_cohere_client.rerank.return_value = mock_response

    reranking_service.rerank("test query", results_without_contextual)

    # Check that content was used as fallback
    call_args = mock_cohere_client.rerank.call_args[1]
    documents = call_args["documents"]
    assert documents[0] == "Test content without contextual"
