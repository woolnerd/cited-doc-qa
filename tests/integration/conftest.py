"""Integration test configuration and fixtures."""

import asyncio
from uuid import uuid4

import pytest
from app.core.config import settings
from app.services.database import DatabaseService


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_service():
    """Create a real DatabaseService for integration tests.

    Uses actual PostgreSQL connection for end-to-end testing.
    """
    db = DatabaseService()
    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
def test_document_id():
    """Generate a unique test document ID."""
    return str(uuid4())


@pytest.fixture(autouse=True)
def cleanup_test_data(db_service):
    """Clean up test data before and after each test.

    This fixture runs automatically for every test to ensure clean state.
    """
    # Store document IDs created during test
    created_docs = []

    def track_document(doc_id: str):
        """Track a document ID for cleanup."""
        created_docs.append(doc_id)

    # Provide tracking function to test
    yield track_document

    # Cleanup after test
    async def cleanup():
        for doc_id in created_docs:
            try:
                # Delete document (chunks cascade automatically)
                await db_service.execute(
                    "DELETE FROM documents WHERE id = $1", doc_id
                )
            except Exception as e:
                # Log but don't fail test on cleanup errors
                print(f"Cleanup warning: Could not delete document {doc_id}: {e}")

    # Run cleanup in event loop
    asyncio.get_event_loop().run_until_complete(cleanup())


@pytest.fixture
def sample_text_content():
    """Provide sample text content for testing."""
    return b"This is a test document about Python programming. Python is a high-level language."


@pytest.fixture
def sample_pdf_content():
    """Provide minimal valid PDF content for testing."""
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF"
