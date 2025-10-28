"""Tests for document upload and management endpoints."""

from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.core.dependencies import get_supabase_client
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def client_with_mock_db(mock_supabase):
    """Create test client with mocked Supabase dependency."""
    app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
    yield TestClient(app), mock_supabase
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
    client, mock_supabase = client_with_mock_db

    # Mock Supabase response
    mock_document_id = str(uuid4())
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        MagicMock(
            data=[
                {
                    "id": mock_document_id,
                    "filename": "test.pdf",
                    "file_type": "pdf",
                    "upload_date": "2025-01-27T00:00:00",
                    "metadata": {"file_size": 100},
                }
            ]
        )
    )

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
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        MagicMock(
            data=[
                {
                    "id": mock_document_id,
                    "filename": "test.docx",
                    "file_type": "docx",
                    "upload_date": "2025-01-27T00:00:00",
                    "metadata": {"file_size": 150},
                }
            ]
        )
    )

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
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        MagicMock(
            data=[
                {
                    "id": mock_document_id,
                    "filename": "test.txt",
                    "file_type": "txt",
                    "upload_date": "2025-01-27T00:00:00",
                    "metadata": {"file_size": 50},
                }
            ]
        )
    )

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
    client, mock_supabase = client_with_mock_db

    # Mock Supabase to return no data (failure)
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        MagicMock(data=None)
    )

    test_content = b"%PDF-1.4 test content"
    files = {"file": create_test_file("test.pdf", test_content, "application/pdf")}

    response = client.post("/api/documents/upload", files=files)

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data


def test_get_document_success(client_with_mock_db):
    """Test successful document retrieval."""
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": mock_document_id,
                "filename": "test.pdf",
                "file_type": "pdf",
                "upload_date": "2025-01-27T00:00:00",
                "metadata": {"file_size": 100},
            }
        ]
    )

    response = client.get(f"/api/documents/{mock_document_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == mock_document_id
    assert data["filename"] == "test.pdf"
    assert data["file_type"] == "pdf"


def test_get_document_not_found(client_with_mock_db):
    """Test document retrieval when document doesn't exist."""
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

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
    client, mock_supabase = client_with_mock_db

    doc_id_1 = str(uuid4())
    doc_id_2 = str(uuid4())

    # Track call count for chunk queries
    call_count = [0]

    def mock_table(table_name):
        """Mock table calls for documents and chunks."""
        mock_chain = MagicMock()

        if table_name == "documents":
            # Return documents list
            mock_chain.select.return_value.order.return_value.execute.return_value = (
                MagicMock(
                    data=[
                        {
                            "id": doc_id_1,
                            "filename": "test1.pdf",
                            "file_type": "pdf",
                            "upload_date": "2025-01-27T00:00:00",
                            "metadata": {"file_size": 100},
                        },
                        {
                            "id": doc_id_2,
                            "filename": "test2.txt",
                            "file_type": "txt",
                            "upload_date": "2025-01-26T00:00:00",
                            "metadata": {"file_size": 50},
                        },
                    ]
                )
            )
        elif table_name == "chunks":
            # Return chunk counts (alternating for each document)
            count = call_count[0]
            call_count[0] += 1
            chunk_count = 5 if count == 0 else 3
            mock_chain.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(count=chunk_count)
            )

        return mock_chain

    mock_supabase.table.side_effect = mock_table

    response = client.get("/api/documents")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_count"] == 2
    assert len(data["documents"]) == 2

    # Check first document
    doc1 = data["documents"][0]
    assert doc1["id"] == doc_id_1
    assert doc1["filename"] == "test1.pdf"
    assert doc1["file_type"] == "pdf"
    assert doc1["chunk_count"] == 5
    assert doc1["status"] == "ready"

    # Check second document
    doc2 = data["documents"][1]
    assert doc2["id"] == doc_id_2
    assert doc2["filename"] == "test2.txt"
    assert doc2["chunk_count"] == 3


def test_list_documents_empty(client_with_mock_db):
    """Test document list when no documents exist."""
    client, mock_supabase = client_with_mock_db

    # Mock empty documents response
    mock_supabase.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(
        data=[]
    )

    response = client.get("/api/documents")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_count"] == 0
    assert len(data["documents"]) == 0


def test_list_documents_database_error(client_with_mock_db):
    """Test document list when database error occurs."""
    client, mock_supabase = client_with_mock_db

    # Mock database error
    mock_supabase.table.return_value.select.return_value.order.return_value.execute.side_effect = Exception(
        "Database error"
    )

    response = client.get("/api/documents")

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data


def test_delete_document_success(client_with_mock_db):
    """Test successful document deletion."""
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())

    # Mock document exists check
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": mock_document_id}]
    )

    # Mock chunks count
    mock_chunks = MagicMock(count=5)

    # Mock delete success
    mock_delete = MagicMock(data=[{"id": mock_document_id}])

    # Setup table() to return different mocks for different operations
    call_sequence = [0]

    def mock_table_chain(table_name):
        """Handle different table operations in sequence."""
        mock_chain = MagicMock()

        if call_sequence[0] == 0:  # First call: check if doc exists
            mock_chain.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[{"id": mock_document_id}])
            )
            call_sequence[0] += 1
        elif call_sequence[0] == 1:  # Second call: get chunk count
            mock_chain.select.return_value.eq.return_value.execute.return_value = (
                mock_chunks
            )
            call_sequence[0] += 1
        else:  # Third call: delete document
            mock_chain.delete.return_value.eq.return_value.execute.return_value = (
                mock_delete
            )

        return mock_chain

    mock_supabase.table.side_effect = mock_table_chain

    response = client.delete(f"/api/documents/{mock_document_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["document_id"] == mock_document_id
    assert data["chunks_deleted"] == 5
    assert "deleted successfully" in data["message"].lower()


def test_delete_document_not_found(client_with_mock_db):
    """Test document deletion when document doesn't exist."""
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())

    # Mock document doesn't exist
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

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
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())

    # Mock document exists
    call_sequence = [0]

    def mock_table_chain(table_name):
        """Handle different table operations."""
        mock_chain = MagicMock()

        if call_sequence[0] == 0:  # Check doc exists
            mock_chain.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[{"id": mock_document_id}])
            )
            call_sequence[0] += 1
        elif call_sequence[0] == 1:  # Get chunk count
            mock_chain.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(count=5)
            )
            call_sequence[0] += 1
        else:  # Delete fails - return no data
            mock_chain.delete.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=None)
            )

        return mock_chain

    mock_supabase.table.side_effect = mock_table_chain

    response = client.delete(f"/api/documents/{mock_document_id}")

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data


def test_process_document_success(client_with_mock_db):
    """Test successful document processing."""
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())

    # Mock document exists
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": mock_document_id,
                "filename": "test.pdf",
                "file_type": "pdf",
                "upload_date": "2025-01-27T00:00:00",
            }
        ]
    )

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
        assert data["document_id"] == mock_document_id
        assert data["text_length"] == 1000
        assert data["num_chunks"] == 5
        assert data["chunks_stored"] == 5
        assert data["processing_status"] == "completed"


def test_process_document_not_found(client_with_mock_db):
    """Test processing when document doesn't exist."""
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())

    # Mock document doesn't exist
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

    test_content = b"%PDF-1.4 test content"
    files = {"file": create_test_file("test.pdf", test_content, "application/pdf")}

    response = client.post(f"/api/documents/{mock_document_id}/process", files=files)

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


def test_process_document_processing_error(client_with_mock_db):
    """Test processing when document processor fails."""
    client, mock_supabase = client_with_mock_db

    mock_document_id = str(uuid4())

    # Mock document exists
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": mock_document_id,
                "filename": "test.pdf",
                "file_type": "pdf",
                "upload_date": "2025-01-27T00:00:00",
            }
        ]
    )

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
