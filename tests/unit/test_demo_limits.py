"""Tests for demo usage tracking and limits."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import Settings
from app.core.exceptions import DemoLimitError
from app.services.demo_limits import DemoLimitService


@pytest.fixture
def demo_settings() -> Settings:
    """Create demo settings with small limits for unit tests."""
    return Settings(
        _env_file=None,
        DEMO_MODE=True,
        DEMO_MAX_UPLOADS_PER_SESSION=2,
        DEMO_MAX_QUERIES_PER_SESSION=3,
        DEMO_MAX_TOTAL_UPLOAD_MB_PER_SESSION=1,
        DEMO_MAX_FILE_SIZE_MB=1,
        DEMO_RATE_LIMIT_WINDOW_MINUTES=15,
        DEMO_MAX_QUERIES_PER_IP=4,
        DEMO_GLOBAL_DAILY_QUERY_LIMIT=5,
        DEMO_USAGE_HASH_SALT="test-salt",
    )


@pytest.fixture
def mock_db():
    """Mock database dependency."""
    mock = MagicMock()
    mock.fetchval = AsyncMock(return_value=0)
    mock.execute = AsyncMock(return_value="INSERT 0 1")
    return mock


@pytest.fixture
def service(mock_db, demo_settings):
    """Create a demo limit service."""
    return DemoLimitService(db=mock_db, config=demo_settings)


def test_hash_ip_is_stable_and_does_not_return_raw_ip(service):
    """IP hashes should be stable and should not expose raw IP addresses."""
    first = service.hash_ip(" 203.0.113.10 ")
    second = service.hash_ip("203.0.113.10")

    assert first == second
    assert first != "203.0.113.10"
    assert len(first) == 64


def test_normalize_query_collapses_case_and_whitespace(service):
    """Duplicate detection should use normalized query text."""
    assert service.normalize_query("  What   IS\nPython? ") == "what is python?"


@pytest.mark.asyncio
async def test_record_query_writes_hashed_metadata_only(service, mock_db):
    """Accepted query events should not store raw query text or raw IPs."""
    await service.record_query(
        session_id="session-1",
        ip_address="203.0.113.10",
        query="What is Python?",
        metadata={"result_count": 2},
    )

    mock_db.execute.assert_awaited_once()
    args = mock_db.execute.await_args.args

    assert "INSERT INTO demo_usage_events" in args[0]
    assert args[1] == "session-1"
    assert args[2] != "203.0.113.10"
    assert args[4] == "query"
    assert args[7] != "What is Python?"
    assert json.loads(args[8]) == {"result_count": 2}


@pytest.mark.asyncio
async def test_check_query_allowed_when_counts_under_limits(service, mock_db):
    """Allowed query checks should inspect duplicate, session, IP, and global counts."""
    mock_db.fetchval.side_effect = [0, 2, 3, 4]

    await service.check_query_allowed(
        session_id="session-1",
        ip_address="203.0.113.10",
        query="What is Python?",
    )

    assert mock_db.fetchval.await_count == 4
    mock_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_query_rejects_whitespace_query(service, mock_db):
    """Whitespace-only queries should be rejected before rate checks."""
    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_query_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            query="   ",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.limit_type == "query_content_limit"
    mock_db.fetchval.assert_not_awaited()
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_query_rejects_duplicate_query(service, mock_db):
    """Rapid duplicate queries should produce a friendly 429."""
    mock_db.fetchval.return_value = 1

    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_query_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            query="What is Python?",
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.limit_type == "duplicate_query"
    assert "30 seconds" in exc_info.value.message
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_query_rejects_length_limit(service, mock_db):
    """Overly long demo queries should be rejected before search."""
    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_query_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            query="x" * 1001,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.limit_type == "query_length_limit"
    mock_db.fetchval.assert_not_awaited()
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_query_rejects_session_limit(service, mock_db):
    """At-limit session query counts should be rejected."""
    mock_db.fetchval.side_effect = [0, 3]

    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_query_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            query="What is Python?",
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.limit_type == "session_query_limit"
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_query_rejects_ip_limit(service, mock_db):
    """At-limit IP query counts should be rejected."""
    mock_db.fetchval.side_effect = [0, 2, 4]

    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_query_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            query="What is Python?",
        )

    assert exc_info.value.limit_type == "ip_query_limit"
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_query_rejects_global_daily_limit(service, mock_db):
    """At-limit global daily query counts should be rejected."""
    mock_db.fetchval.side_effect = [0, 2, 3, 5]

    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_query_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            query="What is Python?",
        )

    assert exc_info.value.limit_type == "global_daily_query_limit"
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_upload_allowed_when_under_limits(service, mock_db):
    """Allowed upload checks should inspect count and byte totals."""
    mock_db.fetchval.side_effect = [1, 512]

    await service.check_upload_allowed(
        session_id="session-1",
        ip_address="203.0.113.10",
        file_size_bytes=256,
    )

    assert mock_db.fetchval.await_count == 2
    mock_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_upload_rejects_file_size_limit(service, mock_db):
    """Per-file upload size limits should return 413."""
    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_upload_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            file_size_bytes=2 * 1024 * 1024,
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.limit_type == "file_size_limit"
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_upload_rejects_tiny_file(service, mock_db):
    """Tiny uploads should be rejected before storage or processing."""
    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_upload_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            file_size_bytes=3,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.limit_type == "upload_content_limit"
    mock_db.execute.assert_awaited_once()
    mock_db.fetchval.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_upload_rejects_upload_count_limit(service, mock_db):
    """At-limit session upload counts should be rejected."""
    mock_db.fetchval.return_value = 2

    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_upload_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            file_size_bytes=512,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.limit_type == "session_upload_limit"
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_upload_rejects_total_upload_bytes(service, mock_db):
    """Per-session uploaded byte totals should be enforced."""
    mock_db.fetchval.side_effect = [1, 1024 * 1024 - 100]

    with pytest.raises(DemoLimitError) as exc_info:
        await service.check_upload_allowed(
            session_id="session-1",
            ip_address="203.0.113.10",
            file_size_bytes=512,
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.limit_type == "session_upload_bytes_limit"
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_service_skips_database_calls(mock_db):
    """Demo limit service should be inert when DEMO_MODE is false."""
    disabled_settings = Settings(_env_file=None, DEMO_MODE=False)
    service = DemoLimitService(db=mock_db, config=disabled_settings)

    await service.check_query_allowed(
        session_id="session-1",
        ip_address="203.0.113.10",
        query="What is Python?",
    )
    await service.record_query(
        session_id="session-1",
        ip_address="203.0.113.10",
        query="What is Python?",
    )

    mock_db.fetchval.assert_not_awaited()
    mock_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_usage_records_returns_deleted_count(service, mock_db):
    """Cleanup should parse asyncpg DELETE status rows."""
    mock_db.execute.return_value = "DELETE 12"

    deleted = await service.cleanup_usage_records(older_than_days=14)

    assert deleted == 12
    mock_db.execute.assert_awaited_once()
