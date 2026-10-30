"""Shared steps for the API integration tests."""

import httpx

# A made-up language name, so the fake reranker scores this document above
# anything else in the database (CI starts empty; `make test-db` also has the
# global demo documents).
SAMPLE_TEXT = (
    b"Quokkalang is a high-level programming language. It is widely used for "
    b"data science, web development, and automation."
)


async def upload_and_process(
    client: httpx.AsyncClient,
    session_id: str,
    content: bytes = SAMPLE_TEXT,
    filename: str = "python.txt",
) -> dict:
    """Upload a text file, process it, and return the processing response."""
    upload = await client.post(
        "/api/documents/upload",
        files={"file": (filename, content, "text/plain")},
        data={"session_id": session_id},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["document_id"]

    process = await client.post(
        f"/api/documents/{document_id}/process",
        files={"file": (filename, content, "text/plain")},
    )
    assert process.status_code == 200, process.text
    return process.json()
