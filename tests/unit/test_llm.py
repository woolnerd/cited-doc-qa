"""Tests for LLM service."""

from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.llm import LLMService


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    with patch("app.services.llm.OpenAI") as mock_client_class:
        client_instance = MagicMock()
        mock_client_class.return_value = client_instance
        yield client_instance


@pytest.fixture
def llm_service(mock_openai_client):
    """Create LLMService with mocked OpenAI client."""
    return LLMService(api_key="test-api-key", base_url="https://test.openrouter.ai")


@pytest.fixture
def sample_search_results():
    """Sample reranked search results."""
    doc_id = str(uuid4())
    return [
        {
            "chunk_id": "chunk1",
            "document_id": doc_id,
            "content": "Python is a high-level programming language.",
            "contextual_content": "Document: python_guide.pdf\n\nPython is a high-level programming language.",
            "metadata": {
                "document_name": "python_guide.pdf",
                "chunk_index": 0,
            },
            "rerank_score": 0.95,
        },
        {
            "chunk_id": "chunk2",
            "document_id": doc_id,
            "content": "Python supports multiple programming paradigms.",
            "contextual_content": "Document: python_guide.pdf\n\nPython supports multiple programming paradigms.",
            "metadata": {
                "document_name": "python_guide.pdf",
                "chunk_index": 1,
            },
            "rerank_score": 0.88,
        },
    ]


@pytest.fixture
def mock_completion_response():
    """Mock successful OpenAI completion response."""
    response = Mock()
    response.choices = [
        Mock(
            message=Mock(content="Python is a high-level programming language [1]."),
            finish_reason="stop",
        )
    ]
    response.usage = Mock(
        prompt_tokens=150,
        completion_tokens=50,
        total_tokens=200,
    )
    return response


def test_service_initialization_success(mock_openai_client):
    """Test successful service initialization."""
    service = LLMService(api_key="test-key", base_url="https://test.openrouter.ai")

    assert service.api_key == "test-key"
    assert service.base_url == "https://test.openrouter.ai"
    assert service.client is mock_openai_client
    assert service.model == "anthropic/claude-4.5-sonnet"


def test_service_initialization_uses_settings(mock_openai_client):
    """Test that service uses settings when no params provided."""
    service = LLMService()

    # Just verify that settings were used
    assert service.api_key is not None
    assert service.base_url is not None
    assert len(service.api_key) > 0


def test_service_initialization_failure():
    """Test handling of initialization failure."""
    with patch("app.services.llm.OpenAI", side_effect=Exception("API error")):
        with pytest.raises(
            DocumentProcessingError, match="Failed to initialize LLM client"
        ):
            LLMService(api_key="test-key")


def test_format_context_with_results(llm_service, sample_search_results):
    """Test context formatting with search results."""
    context = llm_service._format_context(sample_search_results)

    # Check that both results are included
    assert "[1]" in context
    assert "[2]" in context
    assert "Python is a high-level programming language" in context
    assert "Python supports multiple programming paradigms" in context

    # Check that source information is included
    assert "Source: python_guide.pdf, chunk 1" in context
    assert "Source: python_guide.pdf, chunk 2" in context


def test_format_context_empty_results(llm_service):
    """Test context formatting with empty results."""
    context = llm_service._format_context([])

    assert context == "No relevant information found."


def test_format_context_missing_contextual_content(llm_service):
    """Test context formatting falls back to content field."""
    results = [
        {
            "chunk_id": "chunk1",
            "content": "Test content without contextual",
            "metadata": {
                "document_name": "test.pdf",
                "chunk_index": 0,
            },
        }
    ]

    context = llm_service._format_context(results)

    assert "[1] Test content without contextual" in context
    assert "Source: test.pdf, chunk 1" in context


def test_format_context_missing_metadata(llm_service):
    """Test context formatting with missing metadata."""
    results = [
        {
            "chunk_id": "chunk1",
            "content": "Test content",
            "metadata": {},  # Empty metadata
        }
    ]

    context = llm_service._format_context(results)

    assert "[1] Test content" in context
    assert "Source: Unknown Document, chunk 1" in context


def test_create_system_prompt(llm_service):
    """Test system prompt creation."""
    prompt = llm_service._create_system_prompt()

    # Check key elements
    assert "helpful AI assistant" in prompt
    assert "context from documents" in prompt
    assert "citations" in prompt
    assert "Do not make up information" in prompt


def test_generate_answer_success(
    llm_service, mock_openai_client, sample_search_results, mock_completion_response
):
    """Test successful answer generation."""
    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    result = llm_service.generate_answer(
        query="What is Python?",
        search_results=sample_search_results,
    )

    # Check that API was called correctly
    mock_openai_client.chat.completions.create.assert_called_once()
    call_args = mock_openai_client.chat.completions.create.call_args[1]
    assert call_args["model"] == "anthropic/claude-3.5-sonnet"
    assert call_args["temperature"] == 0.3
    assert call_args["max_tokens"] == 2048
    assert len(call_args["messages"]) == 2
    assert call_args["messages"][0]["role"] == "system"
    assert call_args["messages"][1]["role"] == "user"

    # Check result structure
    assert "answer" in result
    assert "sources" in result
    assert "metadata" in result

    # Check answer
    assert result["answer"] == "Python is a high-level programming language [1]."

    # Check sources
    assert len(result["sources"]) == 2
    assert result["sources"][0]["citation_num"] == 1
    assert result["sources"][0]["document_name"] == "python_guide.pdf"
    assert result["sources"][0]["rerank_score"] == 0.95

    # Check metadata
    metadata = result["metadata"]
    assert metadata["query"] == "What is Python?"
    assert metadata["model"] == "anthropic/claude-3.5-sonnet"
    assert metadata["temperature"] == 0.3
    assert metadata["context_chunks"] == 2
    assert metadata["tokens_used"]["total_tokens"] == 200
    assert metadata["finish_reason"] == "stop"
    assert "generation_ms" in metadata["timing"]


def test_generate_answer_empty_results(
    llm_service, mock_openai_client, mock_completion_response
):
    """Test answer generation with empty search results."""
    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    result = llm_service.generate_answer(
        query="What is Python?",
        search_results=[],
    )

    # Check that context includes "No relevant information found"
    call_args = mock_openai_client.chat.completions.create.call_args[1]
    user_message = call_args["messages"][1]["content"]
    assert "No relevant information found" in user_message

    # Check sources are empty
    assert len(result["sources"]) == 0


def test_generate_answer_custom_temperature_and_tokens(
    llm_service, mock_openai_client, sample_search_results, mock_completion_response
):
    """Test answer generation with custom temperature and max_tokens."""
    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    result = llm_service.generate_answer(
        query="What is Python?",
        search_results=sample_search_results,
        temperature=0.7,
        max_tokens=1000,
    )

    # Check that custom values were used
    call_args = mock_openai_client.chat.completions.create.call_args[1]
    assert call_args["temperature"] == 0.7
    assert call_args["max_tokens"] == 1000

    # Check metadata reflects custom values
    assert result["metadata"]["temperature"] == 0.7
    assert result["metadata"]["max_tokens"] == 1000


def test_generate_answer_no_usage_info(
    llm_service, mock_openai_client, sample_search_results
):
    """Test answer generation when usage info is missing."""
    response = Mock()
    response.choices = [
        Mock(
            message=Mock(content="Test answer"),
            finish_reason="stop",
        )
    ]
    response.usage = None  # No usage info
    mock_openai_client.chat.completions.create.return_value = response

    result = llm_service.generate_answer(
        query="What is Python?",
        search_results=sample_search_results,
    )

    # Check that token counts default to 0
    assert result["metadata"]["tokens_used"]["total_tokens"] == 0
    assert result["metadata"]["tokens_used"]["prompt_tokens"] == 0
    assert result["metadata"]["tokens_used"]["completion_tokens"] == 0


def test_generate_answer_empty_response(
    llm_service, mock_openai_client, sample_search_results
):
    """Test answer generation with empty response content."""
    response = Mock()
    response.choices = [
        Mock(
            message=Mock(content=None),  # Empty content
            finish_reason="stop",
        )
    ]
    response.usage = Mock(prompt_tokens=100, completion_tokens=0, total_tokens=100)
    mock_openai_client.chat.completions.create.return_value = response

    result = llm_service.generate_answer(
        query="What is Python?",
        search_results=sample_search_results,
    )

    # Check that answer is empty string
    assert result["answer"] == ""


def test_generate_answer_api_error(
    llm_service, mock_openai_client, sample_search_results
):
    """Test error handling when API call fails."""
    mock_openai_client.chat.completions.create.side_effect = Exception("API error")

    with pytest.raises(DocumentProcessingError, match="Failed to generate answer"):
        llm_service.generate_answer(
            query="What is Python?",
            search_results=sample_search_results,
        )


def test_generate_answer_with_retry_success_first_attempt(
    llm_service, mock_openai_client, sample_search_results, mock_completion_response
):
    """Test retry method succeeds on first attempt."""
    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    result = llm_service.generate_answer_with_retry(
        query="What is Python?",
        search_results=sample_search_results,
        max_retries=3,
    )

    # Should succeed without retries
    assert mock_openai_client.chat.completions.create.call_count == 1
    assert result["answer"] == "Python is a high-level programming language [1]."


def test_generate_answer_with_retry_success_after_retries(
    llm_service, mock_openai_client, sample_search_results, mock_completion_response
):
    """Test retry method succeeds after failures."""
    # Fail first two attempts, succeed on third
    mock_openai_client.chat.completions.create.side_effect = [
        Exception("API error 1"),
        Exception("API error 2"),
        mock_completion_response,
    ]

    with patch("time.sleep"):  # Mock sleep to speed up test
        result = llm_service.generate_answer_with_retry(
            query="What is Python?",
            search_results=sample_search_results,
            max_retries=3,
        )

    # Should have tried 3 times
    assert mock_openai_client.chat.completions.create.call_count == 3
    assert result["answer"] == "Python is a high-level programming language [1]."


def test_generate_answer_with_retry_all_attempts_fail(
    llm_service, mock_openai_client, sample_search_results
):
    """Test retry method fails after all attempts."""
    mock_openai_client.chat.completions.create.side_effect = Exception("API error")

    with patch("time.sleep"):  # Mock sleep to speed up test
        with pytest.raises(
            DocumentProcessingError,
            match="Answer generation failed after 3 attempts",
        ):
            llm_service.generate_answer_with_retry(
                query="What is Python?",
                search_results=sample_search_results,
                max_retries=3,
            )

    # Should have tried 3 times
    assert mock_openai_client.chat.completions.create.call_count == 3


def test_generate_answer_with_retry_custom_parameters(
    llm_service, mock_openai_client, sample_search_results, mock_completion_response
):
    """Test retry method with custom temperature and max_tokens."""
    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    llm_service.generate_answer_with_retry(
        query="What is Python?",
        search_results=sample_search_results,
        temperature=0.8,
        max_tokens=500,
    )

    # Check that custom values were passed through
    call_args = mock_openai_client.chat.completions.create.call_args[1]
    assert call_args["temperature"] == 0.8
    assert call_args["max_tokens"] == 500


def test_generate_answer_includes_query_in_message(
    llm_service, mock_openai_client, sample_search_results, mock_completion_response
):
    """Test that the query is included in the user message."""
    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    llm_service.generate_answer(
        query="What is Python used for?",
        search_results=sample_search_results,
    )

    call_args = mock_openai_client.chat.completions.create.call_args[1]
    user_message = call_args["messages"][1]["content"]
    assert "What is Python used for?" in user_message


def test_generate_answer_includes_context_in_message(
    llm_service, mock_openai_client, sample_search_results, mock_completion_response
):
    """Test that context is included in the user message."""
    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    llm_service.generate_answer(
        query="What is Python?",
        search_results=sample_search_results,
    )

    call_args = mock_openai_client.chat.completions.create.call_args[1]
    user_message = call_args["messages"][1]["content"]

    # Check that context content is present
    assert "Python is a high-level programming language" in user_message
    assert "Python supports multiple programming paradigms" in user_message
    assert "[1]" in user_message
    assert "[2]" in user_message


def test_generate_answer_logs_query(
    llm_service,
    mock_openai_client,
    sample_search_results,
    mock_completion_response,
    caplog,
):
    """Test that answer generation logs the query."""
    import logging

    caplog.set_level(logging.INFO)

    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    llm_service.generate_answer(
        query="What is Python used for?",
        search_results=sample_search_results,
    )

    assert "Generating answer for query" in caplog.text
    assert "What is Python used for?" in caplog.text
    assert "Answer generated" in caplog.text


def test_generate_answer_with_retry_logs_attempts(
    llm_service,
    mock_openai_client,
    sample_search_results,
    mock_completion_response,
    caplog,
):
    """Test that retry attempts are logged."""
    import logging

    caplog.set_level(logging.INFO)

    # Fail first attempt, succeed on second
    mock_openai_client.chat.completions.create.side_effect = [
        Exception("API error"),
        mock_completion_response,
    ]

    with patch("time.sleep"):
        llm_service.generate_answer_with_retry(
            query="What is Python?",
            search_results=sample_search_results,
            max_retries=2,
        )

    assert "Answer generation failed on attempt 1/2" in caplog.text
    assert "Retrying in" in caplog.text


def test_generate_answer_preserves_source_fields(
    llm_service, mock_openai_client, mock_completion_response
):
    """Test that all relevant source fields are preserved in citations."""
    results_with_extra_fields = [
        {
            "chunk_id": "chunk1",
            "document_id": str(uuid4()),
            "content": "Test content",
            "metadata": {
                "document_name": "test.pdf",
                "chunk_index": 5,
            },
            "rerank_score": 0.95,
            "rrf_score": 0.032,
        }
    ]

    mock_openai_client.chat.completions.create.return_value = mock_completion_response

    result = llm_service.generate_answer(
        query="Test query",
        search_results=results_with_extra_fields,
    )

    # Check that source contains expected fields
    source = result["sources"][0]
    assert source["citation_num"] == 1
    assert source["chunk_id"] == "chunk1"
    assert source["document_name"] == "test.pdf"
    assert source["chunk_index"] == 5
    assert source["rerank_score"] == 0.95
