"""Fixtures for tests that run SQL against a real, migrated Postgres.

Skipped unless RUN_DB_TESTS=1. `make test-db` points them at the eval
database from evals/README.md.
"""

import os

import pytest
from app.services.database import DatabaseService


def pytest_collection_modifyitems(items):
    if os.environ.get("RUN_DB_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_DB_TESTS=1 to run database tests")
    for item in items:
        if "tests/db/" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture
async def db_service():
    db = DatabaseService()
    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
async def track_document(db_service):
    """Collect document IDs and delete them (chunks cascade) after the test."""
    doc_ids: list[str] = []
    yield doc_ids.append
    for doc_id in doc_ids:
        await db_service.execute("DELETE FROM documents WHERE id = $1", doc_id)
