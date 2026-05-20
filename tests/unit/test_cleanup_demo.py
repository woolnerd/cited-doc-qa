"""Tests for demo cleanup script."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from scripts import cleanup_demo


@pytest.fixture
def mock_cleanup_db():
    """Mock the cleanup script database dependency."""
    mock = MagicMock()
    mock.pool = object()
    mock.connect = AsyncMock()
    mock.fetch = AsyncMock()
    mock.fetchrow = AsyncMock()
    mock.fetchval = AsyncMock()
    mock.execute = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_cleanup_deletes_old_demo_documents_and_usage_records(
    mock_cleanup_db, monkeypatch
):
    """Cleanup should delete expired demo docs and old usage rows."""
    doc_id = uuid4()
    mock_cleanup_db.fetch.return_value = [
        {
            "id": doc_id,
            "filename": "demo.pdf",
            "upload_date": datetime.now(UTC) - timedelta(hours=25),
            "session_id": "demo-session",
        }
    ]
    mock_cleanup_db.fetchrow.return_value = {"count": 3}
    mock_cleanup_db.fetchval.return_value = 5
    mock_cleanup_db.execute.side_effect = ["DELETE 1", "DELETE 5"]
    monkeypatch.setattr(cleanup_demo, "db", mock_cleanup_db)

    stats = await cleanup_demo.cleanup_old_documents(
        hours=24,
        usage_retention_days=9,
    )

    assert stats == {
        "documents_found": 1,
        "documents_deleted": 1,
        "chunks_found": 3,
        "chunks_deleted": 3,
        "sessions_affected": 1,
        "usage_records_found": 5,
        "usage_records_deleted": 5,
    }

    fetch_args = mock_cleanup_db.fetch.await_args.args
    assert "session_id = ANY" in fetch_args[0]
    assert fetch_args[2] == ["global", "shared"]
    assert mock_cleanup_db.execute.await_count == 2


@pytest.mark.asyncio
async def test_cleanup_dry_run_counts_usage_records_without_deleting(
    mock_cleanup_db, monkeypatch
):
    """Dry run should report expired usage rows without deleting them."""
    mock_cleanup_db.fetch.return_value = []
    mock_cleanup_db.fetchval.return_value = 8
    monkeypatch.setattr(cleanup_demo, "db", mock_cleanup_db)

    stats = await cleanup_demo.cleanup_old_documents(
        dry_run=True,
        usage_retention_days=14,
    )

    assert stats["documents_found"] == 0
    assert stats["documents_deleted"] == 0
    assert stats["chunks_found"] == 0
    assert stats["chunks_deleted"] == 0
    assert stats["usage_records_found"] == 8
    assert stats["usage_records_deleted"] == 0
    mock_cleanup_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_dry_run_preserves_chunk_preview_total(
    mock_cleanup_db, monkeypatch
):
    """Dry run should report chunks that would be deleted."""
    doc_id = uuid4()
    mock_cleanup_db.fetch.return_value = [
        {
            "id": doc_id,
            "filename": "demo.pdf",
            "upload_date": datetime.now(UTC) - timedelta(hours=25),
            "session_id": "demo-session",
        }
    ]
    mock_cleanup_db.fetchrow.return_value = {"count": 4}
    mock_cleanup_db.fetchval.return_value = 0
    monkeypatch.setattr(cleanup_demo, "db", mock_cleanup_db)

    stats = await cleanup_demo.cleanup_old_documents(
        dry_run=True,
        cleanup_usage=False,
    )

    assert stats["documents_found"] == 1
    assert stats["documents_deleted"] == 0
    assert stats["chunks_found"] == 4
    assert stats["chunks_deleted"] == 0
    mock_cleanup_db.execute.assert_not_awaited()


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_positive_int_rejects_invalid_values(value):
    """Destructive cleanup CLI arguments must be positive integers."""
    with pytest.raises(cleanup_demo.argparse.ArgumentTypeError):
        cleanup_demo.positive_int(value)


def test_positive_int_accepts_positive_values():
    """Positive CLI values should parse normally."""
    assert cleanup_demo.positive_int("7") == 7
