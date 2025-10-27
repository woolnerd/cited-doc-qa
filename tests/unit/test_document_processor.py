"""Tests for document processing pipeline."""

import logging
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.document_processor import DocumentProcessor


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    mock = MagicMock()
    # Mock the table().insert().execute() chain
    mock_result = Mock()
    mock_result.data = [{"id": str(uuid4())}] * 3  # 3 chunks stored
    mock.table.return_value.insert.return_value.execute.return_value = mock_result
    return mock


@pytest.fixture
def mock_text_extractor():
    """Mock TextExtractor."""
    mock = MagicMock()
    mock.extract_text.return_value = (
        "This is extracted text. It has multiple sentences. More content here."
    )
    return mock


@pytest.fixture
def mock_chunking_service():
    """Mock ChunkingService."""
    mock = MagicMock()
    mock.chunk_text.return_value = [
        {
            "content": "This is extracted text.",
            "contextual_content": "Document: test.pdf (Type: pdf)\n\nThis is extracted text.",
            "token_count": 50,
            "chunk_index": 0,
        },
        {
            "content": "It has multiple sentences.",
            "contextual_content": "Document: test.pdf (Type: pdf)\n\nIt has multiple sentences.",
            "token_count": 45,
            "chunk_index": 1,
        },
        {
            "content": "More content here.",
            "contextual_content": "Document: test.pdf (Type: pdf)\n\nMore content here.",
            "token_count": 40,
            "chunk_index": 2,
        },
    ]
    return mock


@pytest.fixture
def mock_embedding_service():
    """Mock EmbeddingService."""
    mock = MagicMock()
    mock.generate_embeddings_batch.return_value = [
        [0.1] * 768,  # 768-dim embedding
        [0.2] * 768,
        [0.3] * 768,
    ]
    return mock


@pytest.fixture
def document_processor(
    mock_supabase, mock_text_extractor, mock_chunking_service, mock_embedding_service
):
    """Create DocumentProcessor with mocked dependencies."""
    return DocumentProcessor(
        supabase_client=mock_supabase,
        text_extractor=mock_text_extractor,
        chunking_service=mock_chunking_service,
        embedding_service=mock_embedding_service,
    )


@pytest.fixture
def sample_document_data():
    """Sample document data for testing."""
    return {
        "document_id": uuid4(),
        "file_content": b"Mock PDF content",
        "filename": "test_document.pdf",
        "file_type": "pdf",
    }


def test_process_document_success(document_processor, sample_document_data):
    """Test successful document processing through full pipeline."""
    result = document_processor.process_document(**sample_document_data)

    assert result["status"] == "completed"
    assert result["document_id"] == str(sample_document_data["document_id"])
    assert result["text_length"] > 0
    assert result["num_chunks"] == 3
    assert result["chunks_stored"] == 3


def test_process_document_calls_text_extractor(
    document_processor, sample_document_data, mock_text_extractor
):
    """Test that document processor calls text extractor correctly."""
    document_processor.process_document(**sample_document_data)

    mock_text_extractor.extract_text.assert_called_once_with(
        sample_document_data["file_content"], sample_document_data["file_type"]
    )


def test_process_document_calls_chunking_service(
    document_processor, sample_document_data, mock_chunking_service
):
    """Test that document processor calls chunking service correctly."""
    document_processor.process_document(**sample_document_data)

    mock_chunking_service.chunk_text.assert_called_once()
    call_args = mock_chunking_service.chunk_text.call_args
    assert "test_document.pdf" in str(call_args)  # Filename in metadata


def test_process_document_calls_embedding_service(
    document_processor, sample_document_data, mock_embedding_service
):
    """Test that document processor calls embedding service correctly."""
    document_processor.process_document(**sample_document_data)

    mock_embedding_service.generate_embeddings_batch.assert_called_once()
    call_args = mock_embedding_service.generate_embeddings_batch.call_args[0][0]
    # Should pass contextual content, not just content
    assert all("Document:" in text for text in call_args)


def test_process_document_stores_chunks_in_database(
    document_processor, sample_document_data, mock_supabase
):
    """Test that chunks are stored in database correctly."""
    document_processor.process_document(**sample_document_data)

    mock_supabase.table.assert_called_with("chunks")
    mock_supabase.table().insert.assert_called_once()

    # Check inserted data structure
    inserted_data = mock_supabase.table().insert.call_args[0][0]
    assert len(inserted_data) == 3
    assert all("document_id" in chunk for chunk in inserted_data)
    assert all("content" in chunk for chunk in inserted_data)
    assert all("contextual_content" in chunk for chunk in inserted_data)
    assert all("embedding" in chunk for chunk in inserted_data)
    assert all("chunk_index" in chunk for chunk in inserted_data)


def test_process_document_text_extraction_failure(
    document_processor, sample_document_data, mock_text_extractor
):
    """Test handling of text extraction failure."""
    mock_text_extractor.extract_text.side_effect = DocumentProcessingError(
        "Failed to extract text"
    )

    with pytest.raises(DocumentProcessingError, match="Failed to extract text"):
        document_processor.process_document(**sample_document_data)


def test_process_document_chunking_failure(
    document_processor, sample_document_data, mock_chunking_service
):
    """Test handling of chunking failure."""
    mock_chunking_service.chunk_text.side_effect = DocumentProcessingError(
        "Chunking failed"
    )

    with pytest.raises(DocumentProcessingError, match="Failed to process document"):
        document_processor.process_document(**sample_document_data)


def test_process_document_embedding_failure(
    document_processor, sample_document_data, mock_embedding_service
):
    """Test handling of embedding generation failure."""
    mock_embedding_service.generate_embeddings_batch.side_effect = (
        DocumentProcessingError("Embedding generation failed")
    )

    with pytest.raises(DocumentProcessingError, match="Failed to process document"):
        document_processor.process_document(**sample_document_data)


def test_process_document_storage_failure(
    document_processor, sample_document_data, mock_supabase
):
    """Test handling of database storage failure."""
    mock_result = Mock()
    mock_result.data = None  # Simulate storage failure
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        mock_result
    )

    with pytest.raises(DocumentProcessingError, match="Failed to store chunks"):
        document_processor.process_document(**sample_document_data)


def test_process_document_chunk_embedding_mismatch(
    document_processor, sample_document_data, mock_embedding_service
):
    """Test handling of chunk/embedding count mismatch."""
    # Return wrong number of embeddings
    mock_embedding_service.generate_embeddings_batch.return_value = [
        [0.1] * 768,
        [0.2] * 768,
    ]  # Only 2 embeddings for 3 chunks

    with pytest.raises(DocumentProcessingError, match="does not match"):
        document_processor.process_document(**sample_document_data)


def test_process_document_logs_progress(
    document_processor, sample_document_data, caplog
):
    """Test that processing logs progress at each step."""
    # Set log level to INFO to capture all logs
    caplog.set_level(logging.INFO)

    document_processor.process_document(**sample_document_data)

    # Check that all steps are logged
    assert "Starting document processing" in caplog.text
    assert "Step 1: Extracting text" in caplog.text
    assert "Step 2: Chunking text" in caplog.text
    assert "Step 3: Generating embeddings" in caplog.text
    assert "Step 4: Storing chunks in database" in caplog.text
    assert "Document processing complete" in caplog.text


def test_process_document_with_different_file_types(mock_supabase):
    """Test processing different file types."""
    processor = DocumentProcessor(supabase_client=mock_supabase)

    # Mock the table().insert().execute() chain
    mock_result = Mock()
    mock_result.data = [{"id": str(uuid4())}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        mock_result
    )

    file_types = ["pdf", "docx", "txt"]

    for file_type in file_types:
        with patch.object(processor.text_extractor, "extract_text") as mock_extract:
            mock_extract.return_value = "Extracted text."

            with patch.object(processor.chunking_service, "chunk_text") as mock_chunk:
                mock_chunk.return_value = [
                    {
                        "content": "Extracted text.",
                        "contextual_content": f"Document: test.{file_type} (Type: {file_type})\n\nExtracted text.",
                        "token_count": 10,
                        "chunk_index": 0,
                    }
                ]

                with patch.object(
                    processor.embedding_service, "generate_embeddings_batch"
                ) as mock_embed:
                    mock_embed.return_value = [[0.1] * 768]

                    result = processor.process_document(
                        document_id=uuid4(),
                        file_content=b"test content",
                        filename=f"test.{file_type}",
                        file_type=file_type,
                    )

                    assert result["status"] == "completed"
                    mock_extract.assert_called_with(b"test content", file_type)


def test_store_chunks_validates_counts(mock_supabase):
    """Test that _store_chunks validates chunk and embedding counts."""
    processor = DocumentProcessor(supabase_client=mock_supabase)

    chunks = [
        {
            "content": "Test",
            "contextual_content": "Context Test",
            "chunk_index": 0,
            "token_count": 10,
        }
    ]
    embeddings = [[0.1] * 768, [0.2] * 768]  # Mismatched count

    with pytest.raises(DocumentProcessingError, match="does not match"):
        processor._store_chunks(
            document_id=uuid4(), chunks=chunks, embeddings=embeddings
        )


def test_store_chunks_includes_metadata(mock_supabase):
    """Test that stored chunks include proper metadata."""
    processor = DocumentProcessor(supabase_client=mock_supabase)

    mock_result = Mock()
    mock_result.data = [{"id": str(uuid4())}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        mock_result
    )

    chunks = [
        {
            "content": "Test content",
            "contextual_content": "Document: test.pdf\n\nTest content",
            "chunk_index": 0,
            "token_count": 10,
        }
    ]
    embeddings = [[0.1] * 768]

    processor._store_chunks(document_id=uuid4(), chunks=chunks, embeddings=embeddings)

    # Check metadata is included
    inserted_data = mock_supabase.table().insert.call_args[0][0]
    assert "metadata" in inserted_data[0]
    assert "content_length" in inserted_data[0]["metadata"]
    assert "contextual_length" in inserted_data[0]["metadata"]


def test_processor_initialization_creates_default_services(mock_supabase):
    """Test that processor creates default services if none provided."""
    processor = DocumentProcessor(supabase_client=mock_supabase)

    assert processor.text_extractor is not None
    assert processor.chunking_service is not None
    assert processor.embedding_service is not None
    assert processor.supabase is mock_supabase


def test_processor_initialization_uses_provided_services(
    mock_supabase, mock_text_extractor, mock_chunking_service, mock_embedding_service
):
    """Test that processor uses provided services."""
    processor = DocumentProcessor(
        supabase_client=mock_supabase,
        text_extractor=mock_text_extractor,
        chunking_service=mock_chunking_service,
        embedding_service=mock_embedding_service,
    )

    assert processor.text_extractor is mock_text_extractor
    assert processor.chunking_service is mock_chunking_service
    assert processor.embedding_service is mock_embedding_service


def test_process_document_returns_correct_statistics(
    document_processor, sample_document_data
):
    """Test that processing returns correct statistics."""
    result = document_processor.process_document(**sample_document_data)

    # Verify all expected fields are present
    assert "document_id" in result
    assert "text_length" in result
    assert "num_chunks" in result
    assert "chunks_stored" in result
    assert "status" in result

    # Verify data types
    assert isinstance(result["document_id"], str)
    assert isinstance(result["text_length"], int)
    assert isinstance(result["num_chunks"], int)
    assert isinstance(result["chunks_stored"], int)
    assert result["status"] == "completed"
