"""Tests for conversation history functionality."""

from unittest.mock import Mock, patch

from app.models.base import ConversationMessage, QueryRequest
from app.services.llm import LLMService


class TestConversationHistoryModels:
    """Test conversation history data models."""

    def test_conversation_message_creation(self):
        """Test creating a conversation message."""
        message = ConversationMessage(role="user", content="Hello")
        assert message.role == "user"
        assert message.content == "Hello"

    def test_query_request_with_conversation_history(self):
        """Test QueryRequest with conversation history."""
        history = [
            ConversationMessage(role="user", content="First question"),
            ConversationMessage(role="assistant", content="First answer"),
        ]
        request = QueryRequest(
            session_id="test-session",
            query="Second question",
            conversation_history=history,
        )
        assert request.session_id == "test-session"
        assert request.query == "Second question"
        assert len(request.conversation_history) == 2
        assert request.conversation_history[0].role == "user"
        assert request.conversation_history[1].role == "assistant"

    def test_query_request_without_conversation_history(self):
        """Test QueryRequest without conversation history."""
        request = QueryRequest(session_id="test-session", query="Single question")
        assert request.session_id == "test-session"
        assert request.query == "Single question"
        assert request.conversation_history is None


class TestLLMServiceConversationHistory:
    """Test LLM service conversation history handling."""

    def test_truncate_conversation_history_no_truncation(self):
        """Test that short conversation history is not truncated."""
        service = LLMService()
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]
        result = service._truncate_conversation_history(history, max_messages=10)
        assert len(result) == 2
        assert result == history

    def test_truncate_conversation_history_with_truncation(self):
        """Test that long conversation history is truncated."""
        service = LLMService()
        history = [{"role": "user", "content": f"Q{i}"} for i in range(20)]
        result = service._truncate_conversation_history(history, max_messages=5)
        assert len(result) == 5
        # Should keep the most recent messages
        assert result[-1]["content"] == "Q19"
        assert result[0]["content"] == "Q15"

    @patch("app.services.llm.OpenAI")
    def test_generate_answer_with_conversation_history(self, mock_openai):
        """Test generating answer with conversation history."""
        # Mock the OpenAI client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="Test answer"), finish_reason="stop")
        ]
        mock_response.usage = Mock(
            prompt_tokens=100, completion_tokens=50, total_tokens=150
        )
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = LLMService()
        service.client = mock_client

        # Test with conversation history
        conversation_history = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
        ]

        search_results = [
            {
                "chunk_id": "test-chunk",
                "document_id": "test-doc",
                "content": "Test content",
                "metadata": {
                    "document_name": "test.pdf",
                    "chunk_index": 0,
                },
            }
        ]

        result = service.generate_answer(
            query="Second question",
            search_results=search_results,
            conversation_history=conversation_history,
        )

        # Verify the response
        assert result["answer"] == "Test answer"
        assert "sources" in result
        assert "metadata" in result

        # Verify that the client was called with conversation history
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]

        # Should have: system + 2 history messages + current user message
        assert len(messages) >= 4
        assert messages[0]["role"] == "system"
        assert any(msg["content"] == "First question" for msg in messages)
        assert any(msg["content"] == "First answer" for msg in messages)

    @patch("app.services.llm.OpenAI")
    def test_generate_answer_without_conversation_history(self, mock_openai):
        """Test generating answer without conversation history."""
        # Mock the OpenAI client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="Test answer"), finish_reason="stop")
        ]
        mock_response.usage = Mock(
            prompt_tokens=100, completion_tokens=50, total_tokens=150
        )
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = LLMService()
        service.client = mock_client

        search_results = [
            {
                "chunk_id": "test-chunk",
                "document_id": "test-doc",
                "content": "Test content",
                "metadata": {
                    "document_name": "test.pdf",
                    "chunk_index": 0,
                },
            }
        ]

        result = service.generate_answer(
            query="Single question",
            search_results=search_results,
            conversation_history=None,
        )

        # Verify the response
        assert result["answer"] == "Test answer"

        # Verify that the client was called without conversation history
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]

        # Should have: system + current user message
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
