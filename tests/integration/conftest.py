"""Fixtures for API tests that run against a real, migrated Postgres.

Skipped unless RUN_DB_TESTS=1. `make test-db` points them at the eval
database from evals/README.md; CI uses a pgvector service container.

Only the three provider calls are faked: embeddings, rerank, and the LLM.
Everything else (routes, chunking, the search SQL, RRF, the rerank
threshold, session filtering, citations) runs for real.
"""

import hashlib
import math
import os
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.core.config import settings
from app.core.dependencies import get_database
from app.main import app
from app.services.database import DatabaseService


def pytest_collection_modifyitems(items):
    if os.environ.get("RUN_DB_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_DB_TESTS=1 to run database tests")
    for item in items:
        if "tests/integration/" in str(item.fspath):
            item.add_marker(skip)


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def fake_embedding(text: str) -> list[float]:
    """Bag-of-words vector: texts that share words point the same way."""
    vector = [0.0] * settings.EMBEDDING_DIMENSIONS
    for word in words(text):
        digest = hashlib.sha256(word.encode()).digest()
        vector[int.from_bytes(digest[:4], "little") % len(vector)] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def fake_rerank(
    self, query: str, documents: list[str], top_n: int, timeout: float = 0
) -> list[tuple[int, float]]:
    """Score each document by the share of query words it contains."""
    query_words = words(query)
    scores = [len(query_words & words(d)) / max(len(query_words), 1) for d in documents]
    order = sorted(range(len(documents)), key=lambda i: -scores[i])
    return [(i, scores[i]) for i in order[:top_n]]


def fake_completion(**kwargs):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Quokkalang is a programming language [1]."
                ),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=100, completion_tokens=10, total_tokens=110
        ),
    )


@pytest.fixture(autouse=True)
def fake_providers():
    """Replace every outbound provider call with a deterministic fake."""
    llm_client = MagicMock()
    llm_client.chat.completions.create.side_effect = fake_completion
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embeddings_batch",
            lambda self, texts, batch_size=100: [fake_embedding(t) for t in texts],
        ),
        patch(
            "app.services.embeddings.EmbeddingService.generate_query_embedding",
            lambda self, query: fake_embedding(query),
        ),
        patch(
            "app.services.reranking.RerankingService._rerank_via_provider", fake_rerank
        ),
        patch("app.services.llm.OpenAI", return_value=llm_client),
    ):
        yield llm_client


@pytest.fixture
async def db_service():
    db = DatabaseService()
    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
async def client(db_service):
    """HTTP client for the app, sharing the test's event loop and database pool."""
    app.dependency_overrides[get_database] = lambda: db_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def session_id(db_service):
    """A fresh session whose documents are deleted after the test."""
    sid = f"integration-{os.urandom(6).hex()}"
    yield sid
    await db_service.execute("DELETE FROM documents WHERE session_id = $1", sid)
