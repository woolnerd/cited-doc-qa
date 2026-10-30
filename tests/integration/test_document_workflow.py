"""API tests for uploading, processing, listing, and deleting documents."""

from unittest.mock import patch

import pytest

from tests.integration.helpers import upload_and_process

pytestmark = pytest.mark.integration


async def test_upload_and_process_stores_chunks(client, session_id):
    processed = await upload_and_process(client, session_id)
    document_id = processed["document_id"]

    assert processed["success"] is True
    assert processed["num_chunks"] > 0
    assert processed["chunks_stored"] == processed["num_chunks"]

    listing = await client.get("/api/documents", params={"session_id": session_id})
    assert listing.status_code == 200
    doc = next(d for d in listing.json()["documents"] if d["id"] == document_id)
    assert doc["filename"] == "python.txt"
    assert doc["chunk_count"] == processed["num_chunks"]


async def test_listing_hides_other_sessions_documents(client, session_id):
    processed = await upload_and_process(client, session_id)

    listing = await client.get(
        "/api/documents", params={"session_id": "someone-else-entirely"}
    )

    assert listing.status_code == 200
    ids = {d["id"] for d in listing.json()["documents"]}
    assert processed["document_id"] not in ids


async def test_delete_removes_document_and_chunks(client, db_service, session_id):
    processed = await upload_and_process(client, session_id)
    document_id = processed["document_id"]

    deleted = await client.delete(
        f"/api/documents/{document_id}", params={"session_id": session_id}
    )

    assert deleted.status_code == 200
    assert deleted.json()["chunks_deleted"] == processed["chunks_stored"]
    chunks_left = await db_service.fetchval(
        "SELECT count(*) FROM chunks WHERE document_id = $1", document_id
    )
    assert chunks_left == 0
    assert (await client.get(f"/api/documents/{document_id}")).status_code == 404


async def test_delete_from_another_session_is_forbidden(client, session_id):
    processed = await upload_and_process(client, session_id)

    deleted = await client.delete(
        f"/api/documents/{processed['document_id']}",
        params={"session_id": "someone-else-entirely"},
    )

    assert deleted.status_code == 403


async def test_failed_processing_returns_422_and_removes_document(
    client, db_service, session_id
):
    upload = await client.post(
        "/api/documents/upload",
        files={"file": ("broken.txt", b"some text", "text/plain")},
        data={"session_id": session_id},
    )
    document_id = upload.json()["document_id"]

    with patch(
        "app.services.text_extraction.TextExtractor.extract_text",
        side_effect=Exception("extraction failed"),
    ):
        process = await client.post(
            f"/api/documents/{document_id}/process",
            files={"file": ("broken.txt", b"some text", "text/plain")},
        )

    assert process.status_code == 422
    remaining = await db_service.fetchval(
        "SELECT count(*) FROM documents WHERE id = $1", document_id
    )
    assert remaining == 0
