"""Database-backed public demo usage limits."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.core.config import Settings, settings
from app.core.exceptions import DemoLimitError
from app.core.logging import get_logger
from app.services.database import DatabaseService

logger = get_logger(__name__)

DUPLICATE_QUERY_COOLDOWN_SECONDS = 30

EVENT_QUERY = "query"
EVENT_UPLOAD = "upload"
EVENT_LIMIT_EXCEEDED = "limit_exceeded"

LIMIT_DUPLICATE_QUERY = "duplicate_query"
LIMIT_QUERY_CONTENT = "query_content_limit"
LIMIT_QUERY_LENGTH = "query_length_limit"
LIMIT_SESSION_QUERY = "session_query_limit"
LIMIT_IP_QUERY = "ip_query_limit"
LIMIT_GLOBAL_DAILY_QUERY = "global_daily_query_limit"
LIMIT_FILE_SIZE = "file_size_limit"
LIMIT_UPLOAD_CONTENT = "upload_content_limit"
LIMIT_SESSION_UPLOAD = "session_upload_limit"
LIMIT_SESSION_UPLOAD_BYTES = "session_upload_bytes_limit"

MIN_DEMO_UPLOAD_BYTES = 32


class DemoLimitService:
    """Track and enforce public demo usage without storing sensitive contents."""

    def __init__(self, db: DatabaseService, config: Settings = settings):
        self.db = db
        self.settings = config

    @property
    def enabled(self) -> bool:
        """Return whether public demo limits should be enforced."""
        return self.settings.DEMO_MODE

    def hash_ip(self, ip_address: str | None) -> str | None:
        """Hash an IP address with the configured application salt."""
        if not ip_address:
            return None
        return self._hash_value(ip_address.strip().lower())

    def hash_query(self, query: str) -> str:
        """Hash a normalized query without storing query text."""
        return self._hash_value(self.normalize_query(query))

    def normalize_query(self, query: str) -> str:
        """Normalize query text before duplicate detection."""
        return re.sub(r"\s+", " ", query.strip().lower())

    async def check_query_content_allowed(
        self,
        *,
        session_id: str,
        ip_address: str | None,
        query: str,
        route: str = "/api/query",
    ) -> None:
        """Reject empty, whitespace-only, or overly short demo queries."""
        if not self.enabled:
            return

        normalized_query = self.normalize_query(query)
        compact_query = re.sub(r"[^a-z0-9]+", "", normalized_query)

        if len(normalized_query) > self.settings.DEMO_MAX_QUERY_LENGTH:
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_QUERY_LENGTH,
                message=f"This public demo limits questions to {self.settings.DEMO_MAX_QUERY_LENGTH} characters.",
                status_code=400,
            )

        if len(compact_query) < 3:
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_QUERY_CONTENT,
                message="Please ask a more specific question.",
                status_code=400,
            )

    async def check_query_allowed(
        self,
        *,
        session_id: str,
        ip_address: str | None,
        query: str,
        route: str = "/api/query",
    ) -> None:
        """Raise DemoLimitError if a query would exceed demo limits."""
        if not self.enabled:
            return

        await self.check_query_content_allowed(
            session_id=session_id,
            ip_address=ip_address,
            query=query,
            route=route,
        )

        hashed_ip = self.hash_ip(ip_address)
        query_hash = self.hash_query(query)

        duplicate_count = await self._count_events(
            event_type=EVENT_QUERY,
            session_id=session_id,
            query_hash=query_hash,
            window_interval="second",
            window_amount=DUPLICATE_QUERY_COOLDOWN_SECONDS,
        )
        if duplicate_count > 0:
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_DUPLICATE_QUERY,
                message=f"You just asked that question. Please wait {DUPLICATE_QUERY_COOLDOWN_SECONDS} seconds before trying it again.",
                metadata={"cooldown_seconds": DUPLICATE_QUERY_COOLDOWN_SECONDS},
            )

        session_count = await self.get_session_query_count(session_id)
        if session_count >= self.settings.DEMO_MAX_QUERIES_PER_SESSION:
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_SESSION_QUERY,
                message="This demo session has reached its question limit. Please start a new session later.",
            )

        if hashed_ip:
            ip_count = await self.get_ip_query_count(hashed_ip)
            if ip_count >= self.settings.DEMO_MAX_QUERIES_PER_IP:
                await self._reject(
                    session_id=session_id,
                    ip_address=ip_address,
                    route=route,
                    limit_type=LIMIT_IP_QUERY,
                    message="This public demo is receiving too many questions from your network. Please try again later.",
                )

        global_count = await self.get_global_daily_query_count()
        if global_count >= self.settings.DEMO_GLOBAL_DAILY_QUERY_LIMIT:
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_GLOBAL_DAILY_QUERY,
                message="This public demo has reached today's question limit. Please try again tomorrow.",
            )

    async def record_query(
        self,
        *,
        session_id: str,
        ip_address: str | None,
        query: str,
        route: str = "/api/query",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an accepted query event."""
        if not self.enabled:
            return

        await self._record_event(
            session_id=session_id,
            hashed_ip=self.hash_ip(ip_address),
            route=route,
            event_type=EVENT_QUERY,
            query_hash=self.hash_query(query),
            metadata=metadata,
        )

    async def check_upload_allowed(
        self,
        *,
        session_id: str,
        ip_address: str | None,
        file_size_bytes: int,
        route: str = "/api/documents/upload",
    ) -> None:
        """Raise DemoLimitError if an upload would exceed demo limits."""
        if not self.enabled:
            return

        await self.check_file_content_allowed(
            session_id=session_id,
            ip_address=ip_address,
            file_size_bytes=file_size_bytes,
            route=route,
        )

        upload_count = await self.get_session_upload_count(session_id)
        if upload_count >= self.settings.DEMO_MAX_UPLOADS_PER_SESSION:
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_SESSION_UPLOAD,
                message="This demo session has reached its upload limit.",
                request_bytes=file_size_bytes,
            )

        uploaded_bytes = await self.get_session_uploaded_bytes(session_id)
        if (
            uploaded_bytes + file_size_bytes
            > self.settings.DEMO_MAX_TOTAL_UPLOAD_BYTES_PER_SESSION
        ):
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_SESSION_UPLOAD_BYTES,
                message=f"This demo session can upload up to {self.settings.DEMO_MAX_TOTAL_UPLOAD_MB_PER_SESSION}MB total.",
                status_code=413,
                request_bytes=file_size_bytes,
                metadata={"current_uploaded_bytes": uploaded_bytes},
            )

    async def check_file_content_allowed(
        self,
        *,
        session_id: str,
        ip_address: str | None,
        file_size_bytes: int,
        route: str,
    ) -> None:
        """Raise DemoLimitError if raw file content is unsuitable for demo mode."""
        if not self.enabled:
            return

        if file_size_bytes < MIN_DEMO_UPLOAD_BYTES:
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_UPLOAD_CONTENT,
                message="Please upload a document with enough content to search.",
                status_code=400,
                request_bytes=file_size_bytes,
            )

        if file_size_bytes > self.settings.DEMO_MAX_FILE_SIZE_BYTES:
            await self._reject(
                session_id=session_id,
                ip_address=ip_address,
                route=route,
                limit_type=LIMIT_FILE_SIZE,
                message=f"Files in this public demo must be {self.settings.DEMO_MAX_FILE_SIZE_MB}MB or smaller.",
                status_code=413,
                request_bytes=file_size_bytes,
            )

    async def record_upload(
        self,
        *,
        session_id: str,
        ip_address: str | None,
        file_size_bytes: int,
        route: str = "/api/documents/upload",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an accepted upload event."""
        if not self.enabled:
            return

        await self._record_event(
            session_id=session_id,
            hashed_ip=self.hash_ip(ip_address),
            route=route,
            event_type=EVENT_UPLOAD,
            request_bytes=file_size_bytes,
            metadata=metadata,
        )

    async def record_limit_event(
        self,
        *,
        session_id: str | None,
        ip_address: str | None,
        route: str,
        limit_type: str,
        request_bytes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an over-limit event without sensitive request contents."""
        if not self.enabled:
            return

        logger.info(
            "Demo limit reached: route=%s limit_type=%s session_id=%s",
            route,
            limit_type,
            session_id,
        )
        await self._record_event(
            session_id=session_id,
            hashed_ip=self.hash_ip(ip_address),
            route=route,
            event_type=EVENT_LIMIT_EXCEEDED,
            limit_type=limit_type,
            request_bytes=request_bytes,
            metadata=metadata,
        )

    async def get_session_query_count(self, session_id: str) -> int:
        """Count accepted session queries in the configured rate window."""
        return await self._count_events(
            event_type=EVENT_QUERY,
            session_id=session_id,
            window_interval="minute",
            window_amount=self.settings.DEMO_RATE_LIMIT_WINDOW_MINUTES,
        )

    async def get_ip_query_count(self, hashed_ip: str) -> int:
        """Count accepted IP queries in the configured rate window."""
        return await self._count_events(
            event_type=EVENT_QUERY,
            hashed_ip=hashed_ip,
            window_interval="minute",
            window_amount=self.settings.DEMO_RATE_LIMIT_WINDOW_MINUTES,
        )

    async def get_global_daily_query_count(self) -> int:
        """Count accepted queries since the current database day started."""
        value = await self.db.fetchval(
            """
            SELECT COUNT(*)
            FROM demo_usage_events
            WHERE event_type = $1
              AND created_at >= date_trunc('day', now())
            """,
            EVENT_QUERY,
        )
        return int(value or 0)

    async def get_session_upload_count(self, session_id: str) -> int:
        """Count accepted uploads for a session."""
        return await self._count_events(
            event_type=EVENT_UPLOAD,
            session_id=session_id,
        )

    async def get_session_uploaded_bytes(self, session_id: str) -> int:
        """Sum accepted upload bytes for a session."""
        value = await self.db.fetchval(
            """
            SELECT COALESCE(SUM(request_bytes), 0)
            FROM demo_usage_events
            WHERE event_type = $1
              AND session_id = $2
            """,
            EVENT_UPLOAD,
            session_id,
        )
        return int(value or 0)

    async def cleanup_usage_records(self, *, older_than_days: int = 7) -> int:
        """Delete demo usage records older than the requested retention window."""
        status = await self.db.execute(
            """
            DELETE FROM demo_usage_events
            WHERE created_at < now() - ($1::int * interval '1 day')
            """,
            older_than_days,
        )
        return self._rows_affected(status)

    async def _reject(
        self,
        *,
        session_id: str | None,
        ip_address: str | None,
        route: str,
        limit_type: str,
        message: str,
        status_code: int = 429,
        request_bytes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.record_limit_event(
            session_id=session_id,
            ip_address=ip_address,
            route=route,
            limit_type=limit_type,
            request_bytes=request_bytes,
            metadata=metadata,
        )
        raise DemoLimitError(message, status_code=status_code, limit_type=limit_type)

    async def _count_events(
        self,
        *,
        event_type: str,
        session_id: str | None = None,
        hashed_ip: str | None = None,
        query_hash: str | None = None,
        window_interval: str | None = None,
        window_amount: int | None = None,
    ) -> int:
        if window_interval not in {None, "minute", "second"}:
            raise ValueError(
                f"Unsupported demo usage window interval: {window_interval}"
            )

        value = await self.db.fetchval(
            """
            SELECT COUNT(*)
            FROM demo_usage_events
            WHERE event_type = $1
              AND ($2::varchar IS NULL OR session_id = $2)
              AND ($3::char(64) IS NULL OR hashed_ip = $3)
              AND ($4::char(64) IS NULL OR query_hash = $4)
              AND (
                $5::int IS NULL
                OR ($6::varchar = 'minute' AND created_at >= now() - ($5::int * interval '1 minute'))
                OR ($6::varchar = 'second' AND created_at >= now() - ($5::int * interval '1 second'))
              )
            """,
            event_type,
            session_id,
            hashed_ip,
            query_hash,
            window_amount,
            window_interval,
        )
        return int(value or 0)

    async def _record_event(
        self,
        *,
        session_id: str | None,
        hashed_ip: str | None,
        route: str,
        event_type: str,
        limit_type: str | None = None,
        request_bytes: int | None = None,
        query_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO demo_usage_events (
                session_id,
                hashed_ip,
                route,
                event_type,
                limit_type,
                request_bytes,
                query_hash,
                metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            """,
            session_id,
            hashed_ip,
            route,
            event_type,
            limit_type,
            request_bytes,
            query_hash,
            json.dumps(metadata or {}),
        )

    def _hash_value(self, value: str) -> str:
        salt = self.settings.DEMO_USAGE_HASH_SALT.strip()
        return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()

    def _rows_affected(self, status: str) -> int:
        try:
            return int(status.rsplit(" ", 1)[-1])
        except (AttributeError, ValueError):
            return 0
