"""Tests for document upload and management endpoints."""

from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.core.dependencies import get_database
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db():
    """Create a mock DatabaseService."""
    mock = MagicMock()
    # Make database methods async
    mock.fetchrow = AsyncMock()
    mock.fetch = AsyncMock()
    mock.execute = AsyncMock()
    return mock


@pytest.fixture
def client_with_mock_db(mock_db):
    """Create test client with mocked Database dependency."""
    app.dependency_overrides[get_database] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


def create_test_file(filename: str, content: bytes, content_type: str):
    """Create a test file for upload.

    Args:
        filename: The filename
        content: File content as bytes
        content_type: MIME type

    Returns:
        Tuple of (filename, file_object, content_type)
    """
    return (filename, BytesIO(content), content_type)


def test_upload_pdf_success(client_with_mock_db):
    """Test successful PDF upload."""
    client, mock_db = client_with_mock_db

    # Mock database INSERT ... RETURNING response
    mock_document_id = uuid4()
    mock_db.fetchrow.return_value = {
        "id": mock_document_id,
        "filename": "test.pdf",
        "file_type": "pdf",
        "upload_date": datetime.now(UTC),
        "metadata": {"file_size": 100},
    }

    # Create test PDF file
    test_content = b"%PDF-1.4 test content"
    files = {"file": create_test_file("test.pdf", test_content, "application/pdf")}

    response = client.post("/api/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "test.pdf"
    assert data["file_type"] == "pdf"
    assert "document_id" in data
    assert data["file_size"] == len(test_content)


def test_upload_docx_success(client_with_mock_db):
    """Test successful DOCX upload."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()
    mock_db.fetchrow.return_value = {
        "id": mock_document_id,
        "filename": "test.docx",
        "file_type": "docx",
        "upload_date": datetime.now(UTC),
        "metadata": {"file_size": 150},
    }

    test_content = b"PK\x03\x04 test docx content"  # DOCX files are ZIP archives
    files = {
        "file": create_test_file(
            "test.docx",
            test_content,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    response = client.post("/api/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "test.docx"
    assert data["file_type"] == "docx"


def test_upload_txt_success(client_with_mock_db):
    """Test successful TXT upload."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()
    mock_db.fetchrow.return_value = {
        "id": mock_document_id,
        "filename": "test.txt",
        "file_type": "txt",
        "upload_date": datetime.now(UTC),
        "metadata": {"file_size": 50},
    }

    test_content = b"This is a test text file content."
    files = {"file": create_test_file("test.txt", test_content, "text/plain")}

    response = client.post("/api/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "test.txt"
    assert data["file_type"] == "txt"


def test_upload_invalid_file_type(client_with_mock_db):
    """Test upload with invalid file type."""
    client, _ = client_with_mock_db

    test_content = b"Invalid file content"
    files = {
        "file": create_test_file("test.exe", test_content, "application/x-msdownload")
    }

    response = client.post("/api/documents/upload", files=files)

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "not allowed" in data["detail"].lower()


def test_upload_file_too_large(client_with_mock_db):
    """Test upload with file exceeding size limit."""
    client, _ = client_with_mock_db

    # Create 11MB file (exceeds 10MB limit)
    large_content = b"x" * (11 * 1024 * 1024)
    files = {"file": create_test_file("large.pdf", large_content, "application/pdf")}

    response = client.post("/api/documents/upload", files=files)

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "exceeds" in data["detail"].lower()


def test_upload_no_file(client_with_mock_db):
    """Test upload without providing a file."""
    client, _ = client_with_mock_db

    response = client.post("/api/documents/upload")

    assert response.status_code == 422  # Unprocessable Entity


def test_upload_database_error(client_with_mock_db):
    """Test upload when database operation fails."""
    client, mock_db = client_with_mock_db

    # Mock database to return None (failure)
    mock_db.fetchrow.return_value = None

    test_content = b"%PDF-1.4 test content"
    files = {"file": create_test_file("test.pdf", test_content, "application/pdf")}

    response = client.post("/api/documents/upload", files=files)

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data


def test_get_document_success(client_with_mock_db):
    """Test successful document retrieval."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()
    mock_db.fetchrow.return_value = {
        "id": mock_document_id,
        "filename": "test.pdf",
        "file_type": "pdf",
        "upload_date": datetime.now(UTC),
        "metadata": {"file_size": 100},
    }

    response = client.get(f"/api/documents/{mock_document_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(mock_document_id)
    assert data["filename"] == "test.pdf"
    assert data["file_type"] == "pdf"


def test_get_document_not_found(client_with_mock_db):
    """Test document retrieval when document doesn't exist."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()
    mock_db.fetchrow.return_value = None

    response = client.get(f"/api/documents/{mock_document_id}")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


def test_get_document_invalid_uuid(client_with_mock_db):
    """Test document retrieval with invalid UUID."""
    client, _ = client_with_mock_db

    response = client.get("/api/documents/invalid-uuid")

    assert response.status_code == 422  # Unprocessable Entity


def test_list_documents_success(client_with_mock_db):
    """Test successful document list retrieval."""
    client, mock_db = client_with_mock_db

    doc_id_1 = uuid4()
    doc_id_2 = uuid4()

    # Mock database fetch with JOIN result
    mock_db.fetch.return_value = [
        {
            "id": doc_id_1,
            "filename": "test1.pdf",
            "file_type": "pdf",
            "upload_date": datetime.now(UTC),
            "metadata": {"file_size": 100},
            "chunk_count": 5,
        },
        {
            "id": doc_id_2,
            "filename": "test2.txt",
            "file_type": "txt",
            "upload_date": datetime.now(UTC),
            "metadata": {"file_size": 50},
            "chunk_count": 3,
        },
    ]

    response = client.get("/api/documents")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_count"] == 2
    assert len(data["documents"]) == 2

    # Check first document
    doc1 = data["documents"][0]
    assert doc1["id"] == str(doc_id_1)
    assert doc1["filename"] == "test1.pdf"
    assert doc1["file_type"] == "pdf"
    assert doc1["chunk_count"] == 5
    assert doc1["status"] == "ready"

    # Check second document
    doc2 = data["documents"][1]
    assert doc2["id"] == str(doc_id_2)
    assert doc2["filename"] == "test2.txt"
    assert doc2["chunk_count"] == 3


def test_list_documents_empty(client_with_mock_db):
    """Test document list when no documents exist."""
    client, mock_db = client_with_mock_db

    # Mock empty documents response
    mock_db.fetch.return_value = []

    response = client.get("/api/documents")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_count"] == 0
    assert len(data["documents"]) == 0


def test_list_documents_database_error(client_with_mock_db):
    """Test document list when database error occurs."""
    client, mock_db = client_with_mock_db

    # Mock database error
    mock_db.fetch.side_effect = Exception("Database error")

    response = client.get("/api/documents")

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data


def test_delete_document_success(client_with_mock_db):
    """Test successful document deletion."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()

    # Mock document exists with chunk count
    mock_db.fetchrow.return_value = {
        "id": mock_document_id,
        "chunk_count": 5,
    }

    # Mock successful delete
    mock_db.execute.return_value = None

    response = client.delete(f"/api/documents/{mock_document_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["document_id"] == str(mock_document_id)
    assert data["chunks_deleted"] == 5
    assert "deleted successfully" in data["message"].lower()


def test_delete_document_not_found(client_with_mock_db):
    """Test document deletion when document doesn't exist."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()

    # Mock document doesn't exist
    mock_db.fetchrow.return_value = None

    response = client.delete(f"/api/documents/{mock_document_id}")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


def test_delete_document_invalid_uuid(client_with_mock_db):
    """Test document deletion with invalid UUID."""
    client, _ = client_with_mock_db

    response = client.delete("/api/documents/invalid-uuid")

    assert response.status_code == 422  # Unprocessable Entity


def test_delete_document_database_error(client_with_mock_db):
    """Test document deletion when delete operation fails."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()

    # Mock document exists
    mock_db.fetchrow.return_value = {
        "id": mock_document_id,
        "chunk_count": 5,
    }

    # Mock delete fails
    mock_db.execute.side_effect = Exception("Delete failed")

    response = client.delete(f"/api/documents/{mock_document_id}")

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data


def test_process_document_success(client_with_mock_db):
    """Test successful document processing."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()

    # Mock document exists
    mock_db.fetchrow.return_value = {
        "filename": "test.pdf",
        "file_type": "pdf",
    }

    # Mock DocumentProcessor
    with patch("app.api.documents.DocumentProcessor") as MockProcessor:
        mock_processor = MockProcessor.return_value
        mock_processor.process_document.return_value = {
            "text_length": 1000,
            "num_chunks": 5,
            "chunks_stored": 5,
            "status": "completed",
        }

        # Create test file
        test_content = b"%PDF-1.4 test content"
        files = {"file": create_test_file("test.pdf", test_content, "application/pdf")}

        response = client.post(
            f"/api/documents/{mock_document_id}/process", files=files
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["document_id"] == str(mock_document_id)
        assert data["text_length"] == 1000
        assert data["num_chunks"] == 5
        assert data["chunks_stored"] == 5
        assert data["processing_status"] == "completed"


def test_process_document_not_found(client_with_mock_db):
    """Test processing when document doesn't exist."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()

    # Mock document doesn't exist
    mock_db.fetchrow.return_value = None

    test_content = b"%PDF-1.4 test content"
    files = {"file": create_test_file("test.pdf", test_content, "application/pdf")}

    response = client.post(f"/api/documents/{mock_document_id}/process", files=files)

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


def test_process_document_processing_error(client_with_mock_db):
    """Test processing when document processor fails."""
    client, mock_db = client_with_mock_db

    mock_document_id = uuid4()

    # Mock document exists
    mock_db.fetchrow.return_value = {
        "filename": "test.pdf",
        "file_type": "pdf",
    }

    # Mock DocumentProcessor to raise error
    with patch("app.api.documents.DocumentProcessor") as MockProcessor:
        from app.core.exceptions import DocumentProcessingError

        mock_processor = MockProcessor.return_value
        mock_processor.process_document.side_effect = DocumentProcessingError(
            "Failed to extract text"
        )

        test_content = b"%PDF-1.4 test content"
        files = {"file": create_test_file("test.pdf", test_content, "application/pdf")}

        response = client.post(
            f"/api/documents/{mock_document_id}/process", files=files
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "processing failed" in data["detail"].lower()


def test_process_document_invalid_uuid(client_with_mock_db):
    """Test processing with invalid document UUID."""
    client, _ = client_with_mock_db

    test_content = b"%PDF-1.4 test content"
    files = {"file": create_test_file("test.pdf", test_content, "application/pdf")}

    response = client.post("/api/documents/invalid-uuid/process", files=files)

    assert response.status_code == 422  # Unprocessable Entity
