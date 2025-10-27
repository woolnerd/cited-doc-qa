"""Tests for contextual chunking service."""

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.chunking import ChunkingService


@pytest.fixture
def chunking_service():
    """Create a ChunkingService instance."""
    return ChunkingService()


@pytest.fixture
def sample_metadata():
    """Sample document metadata for testing."""
    return {"filename": "test_document.pdf", "file_type": "pdf"}


def test_count_tokens(chunking_service):
    """Test token counting."""
    text = "This is a test sentence."
    token_count = chunking_service.count_tokens(text)

    assert token_count > 0
    assert isinstance(token_count, int)
    # Should be around 6-7 tokens
    assert 5 <= token_count <= 10


def test_count_tokens_empty(chunking_service):
    """Test token counting with empty string."""
    token_count = chunking_service.count_tokens("")
    assert token_count == 0


def test_create_contextual_chunk(chunking_service, sample_metadata):
    """Test contextual chunk creation."""
    chunk_text = "This is the chunk content."
    contextual = chunking_service.create_contextual_chunk(chunk_text, sample_metadata)

    assert "Document: test_document.pdf" in contextual
    assert "Type: pdf" in contextual
    assert chunk_text in contextual
    assert contextual.startswith("Document:")


def test_create_contextual_chunk_unknown_filename(chunking_service):
    """Test contextual chunk with missing filename."""
    chunk_text = "Test content"
    metadata = {"file_type": "txt"}
    contextual = chunking_service.create_contextual_chunk(chunk_text, metadata)

    assert "Document: Unknown" in contextual
    assert chunk_text in contextual


def test_split_into_sentences(chunking_service):
    """Test sentence splitting."""
    text = "First sentence. Second sentence! Third sentence? Fourth sentence."
    sentences = chunking_service.split_into_sentences(text)

    assert len(sentences) == 4
    assert sentences[0] == "First sentence."
    assert sentences[1] == "Second sentence!"
    assert sentences[2] == "Third sentence?"
    assert sentences[3] == "Fourth sentence."


def test_split_into_sentences_no_spaces(chunking_service):
    """Test sentence splitting with no proper spacing."""
    text = "First.Second.Third."
    sentences = chunking_service.split_into_sentences(text)

    # Should not split without proper spacing
    assert len(sentences) >= 1


def test_chunk_text_basic(chunking_service, sample_metadata):
    """Test basic text chunking."""
    text = (
        "This is a test document. It contains multiple sentences. "
        "Each sentence should be processed correctly. "
        "The chunks should have appropriate sizes."
    )

    chunks = chunking_service.chunk_text(text, sample_metadata)

    assert len(chunks) > 0
    assert all("content" in chunk for chunk in chunks)
    assert all("contextual_content" in chunk for chunk in chunks)
    assert all("token_count" in chunk for chunk in chunks)
    assert all("chunk_index" in chunk for chunk in chunks)

    # Check chunk indices are sequential
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i


def test_chunk_text_respects_size_limits(chunking_service, sample_metadata):
    """Test that chunks respect size limits."""
    # Create a longer text
    text = " ".join([f"This is sentence number {i}." for i in range(100)])

    chunks = chunking_service.chunk_text(
        text, sample_metadata, min_chunk_size=50, max_chunk_size=150
    )

    # All chunks should be within size limits
    for chunk in chunks:
        assert chunk["token_count"] <= 150
        # Some chunks might be smaller than min due to context overhead


def test_chunk_text_single_sentence(chunking_service, sample_metadata):
    """Test chunking with single sentence."""
    text = "This is a single sentence document."
    chunks = chunking_service.chunk_text(text, sample_metadata)

    assert len(chunks) == 1
    assert chunks[0]["content"] == text
    assert "test_document.pdf" in chunks[0]["contextual_content"]


def test_chunk_text_long_sentence(chunking_service, sample_metadata):
    """Test chunking with very long sentence."""
    # Create a long sentence that exceeds max chunk size
    words = ["word"] * 200
    text = " ".join(words) + "."

    chunks = chunking_service.chunk_text(
        text, sample_metadata, min_chunk_size=50, max_chunk_size=150
    )

    # Should be split into multiple chunks
    assert len(chunks) > 1

    # Each chunk should respect max size
    for chunk in chunks:
        assert chunk["token_count"] <= 150


def test_chunk_text_multiple_paragraphs(chunking_service, sample_metadata):
    """Test chunking with multiple paragraphs."""
    text = """
    This is the first paragraph. It has multiple sentences. Each sentence adds to the content.

    This is the second paragraph. It also contains information. The chunker should handle this well.

    This is the third paragraph. It continues the document. More content here.
    """

    chunks = chunking_service.chunk_text(text, sample_metadata)

    assert len(chunks) >= 1
    # Verify all chunks have contextual content
    for chunk in chunks:
        assert "Document: test_document.pdf" in chunk["contextual_content"]


def test_chunk_text_empty_raises_error(chunking_service, sample_metadata):
    """Test that empty text raises error."""
    with pytest.raises(DocumentProcessingError, match="Cannot chunk empty text"):
        chunking_service.chunk_text("", sample_metadata)


def test_chunk_text_whitespace_only_raises_error(chunking_service, sample_metadata):
    """Test that whitespace-only text raises error."""
    with pytest.raises(DocumentProcessingError, match="Cannot chunk empty text"):
        chunking_service.chunk_text("   \n\n\t  ", sample_metadata)


def test_chunk_text_preserves_content(chunking_service, sample_metadata):
    """Test that chunking preserves all content."""
    text = "First. Second. Third. Fourth. Fifth. Sixth. Seventh. Eighth."
    chunks = chunking_service.chunk_text(text, sample_metadata)

    # Reconstruct text from chunks (without context)
    reconstructed = " ".join([chunk["content"] for chunk in chunks])

    # All sentences should be present
    assert "First." in reconstructed
    assert "Second." in reconstructed
    assert "Third." in reconstructed
    assert "Fourth." in reconstructed


def test_chunk_text_with_special_characters(chunking_service, sample_metadata):
    """Test chunking text with special characters."""
    text = (
        "This has special chars: é, ñ, ü! "
        "It also has symbols: @#$%. "
        "And numbers: 123, 456."
    )

    chunks = chunking_service.chunk_text(text, sample_metadata)

    assert len(chunks) >= 1
    # Verify content is preserved
    reconstructed = " ".join([chunk["content"] for chunk in chunks])
    assert "é" in reconstructed
    assert "@#$%" in reconstructed


def test_chunk_text_custom_size_limits(chunking_service, sample_metadata):
    """Test chunking with custom size limits."""
    text = " ".join([f"Sentence {i}." for i in range(50)])

    chunks = chunking_service.chunk_text(
        text, sample_metadata, min_chunk_size=100, max_chunk_size=200
    )

    # Verify chunks respect custom limits
    for chunk in chunks:
        assert chunk["token_count"] <= 200


def test_chunk_indices_sequential(chunking_service, sample_metadata):
    """Test that chunk indices are sequential and start at 0."""
    text = " ".join([f"This is sentence number {i}." for i in range(20)])

    chunks = chunking_service.chunk_text(text, sample_metadata)

    # Check indices
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i

    # First chunk should be index 0
    assert chunks[0]["chunk_index"] == 0


def test_contextual_content_includes_original(chunking_service, sample_metadata):
    """Test that contextual content includes original chunk content."""
    text = "This is the original content. It should be preserved."
    chunks = chunking_service.chunk_text(text, sample_metadata)

    for chunk in chunks:
        # Original content should be in contextual content
        assert chunk["content"] in chunk["contextual_content"]
