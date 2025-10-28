"""Integration tests for document upload and processing workflow."""

from io import BytesIO
from unittest.mock import patch

import pytest
from app.core.dependencies import get_supabase_client
from app.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def client(supabase_client):
    """Create test client with real database."""
    app.dependency_overrides[get_supabase_client] = lambda: supabase_client
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.slow
def test_document_upload_processing_storage_flow(
    client, cleanup_test_data, sample_text_content
):
    """Test complete flow: upload → process → verify storage in database.

    This integration test verifies:
    1. Document upload creates database record
    2. Document processing extracts text, chunks, and embeds
    3. Chunks and embeddings are stored in database
    4. Data can be queried back from database
    """
    # Mock external APIs
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch(
            "app.services.text_extraction.TextExtractor.extract_from_txt"
        ) as mock_extract,
    ):
        # Setup mocks
        mock_extract.return_value = "Sample extracted text for testing"
        mock_embed.return_value = [0.1] * 768  # Mock 768-dim embedding

        # Step 1: Upload document
        files = {"file": ("test.txt", BytesIO(sample_text_content), "text/plain")}
        upload_response = client.post("/api/documents/upload", files=files)

        assert upload_response.status_code == 201
        upload_data = upload_response.json()
        assert upload_data["success"] is True
        document_id = upload_data["document_id"]

        # Track for cleanup
        cleanup_test_data(document_id)

        # Step 2: Process document
        files = {"file": ("test.txt", BytesIO(sample_text_content), "text/plain")}
        process_response = client.post(
            f"/api/documents/{document_id}/process", files=files
        )

        assert process_response.status_code == 200
        process_data = process_response.json()
        assert process_data["success"] is True
        assert process_data["num_chunks"] > 0
        assert process_data["chunks_stored"] == process_data["num_chunks"]

        # Step 3: Verify document in database
        doc_response = client.get(f"/api/documents/{document_id}")
        assert doc_response.status_code == 200
        doc_data = doc_response.json()
        assert doc_data["id"] == document_id
        assert doc_data["filename"] == "test.txt"

        # Step 4: Verify chunks in database
        list_response = client.get("/api/documents")
        assert list_response.status_code == 200
        list_data = list_response.json()

        uploaded_doc = next(d for d in list_data["documents"] if d["id"] == document_id)
        assert uploaded_doc["chunk_count"] > 0
        assert uploaded_doc["status"] == "ready"


@pytest.mark.slow
def test_document_deletion_cascade(client, cleanup_test_data, sample_text_content):
    """Test that deleting a document removes all associated chunks.

    Verifies database CASCADE DELETE works correctly.
    """
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch(
            "app.services.text_extraction.TextExtractor.extract_from_txt"
        ) as mock_extract,
    ):
        mock_extract.return_value = "Sample text for deletion test"
        mock_embed.return_value = [0.1] * 768

        # Upload and process document
        files = {
            "file": ("delete_test.txt", BytesIO(sample_text_content), "text/plain")
        }
        upload_response = client.post("/api/documents/upload", files=files)
        document_id = upload_response.json()["document_id"]

        files = {
            "file": ("delete_test.txt", BytesIO(sample_text_content), "text/plain")
        }
        process_response = client.post(
            f"/api/documents/{document_id}/process", files=files
        )
        chunks_stored = process_response.json()["chunks_stored"]
        assert chunks_stored > 0

        # Delete document
        delete_response = client.delete(f"/api/documents/{document_id}")
        assert delete_response.status_code == 200
        delete_data = delete_response.json()
        assert delete_data["success"] is True
        assert delete_data["chunks_deleted"] == chunks_stored

        # Verify document is gone
        doc_response = client.get(f"/api/documents/{document_id}")
        assert doc_response.status_code == 404

        # No need to track for cleanup since we deleted it


@pytest.mark.slow
def test_error_handling_invalid_document(client, cleanup_test_data):
    """Test error handling when processing invalid document."""
    # Upload valid document metadata
    files = {"file": ("test.txt", BytesIO(b"valid content"), "text/plain")}
    upload_response = client.post("/api/documents/upload", files=files)
    document_id = upload_response.json()["document_id"]
    cleanup_test_data(document_id)

    # Try to process with corrupted content
    with patch(
        "app.services.text_extraction.TextExtractor.extract_from_txt"
    ) as mock_extract:
        mock_extract.side_effect = Exception("Extraction failed")

        files = {"file": ("test.txt", BytesIO(b"corrupted"), "text/plain")}
        process_response = client.post(
            f"/api/documents/{document_id}/process", files=files
        )

        # Should return error
        assert process_response.status_code in [422, 500]
