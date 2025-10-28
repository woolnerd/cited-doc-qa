"""Load tests for concurrent operations."""

import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from app.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.benchmark


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.mark.slow
def test_concurrent_document_uploads(client, sample_text_medium):
    """Load test: 10 concurrent document uploads."""
    with (
        patch(
            "app.services.text_extraction.TextExtractor.extract_from_txt"
        ) as mock_extract,
        patch.object(app.dependency_overrides, "get", return_value=lambda: MagicMock()),
    ):
        mock_extract.return_value = "Sample extracted text"

        def upload_document(i):
            sample_text_medium.seek(0)
            files = {
                "file": (
                    f"doc_{i}.txt",
                    BytesIO(sample_text_medium.read()),
                    "text/plain",
                )
            }
            start = time.time()
            response = client.post("/api/documents/upload", files=files)
            duration = time.time() - start
            return {
                "index": i,
                "status_code": response.status_code,
                "duration": duration,
                "success": response.status_code == 201,
            }

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(upload_document, range(10)))
        total_time = time.time() - start_time

        # Verify results
        successes = sum(1 for r in results if r["success"])
        avg_duration = sum(r["duration"] for r in results) / len(results)
        p95_duration = sorted([r["duration"] for r in results])[
            int(len(results) * 0.95)
        ]

        print("\n=== Concurrent Upload Results ===")
        print("Total documents: 10")
        print(f"Successful uploads: {successes}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Average duration: {avg_duration:.2f}s")
        print(f"P95 duration: {p95_duration:.2f}s")

        # At least 70% should succeed
        assert successes >= 7, f"Only {successes}/10 uploads succeeded"


@pytest.mark.slow
def test_concurrent_queries(client):
    """Load test: 50 concurrent queries."""
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch("app.services.retrieval.RetrievalService.hybrid_search") as mock_search,
        patch("cohere.Client") as mock_cohere,
        patch("requests.post") as mock_llm,
        patch.object(app.dependency_overrides, "get", return_value=lambda: MagicMock()),
    ):
        # Setup mocks
        mock_embed.return_value = [0.1] * 768
        mock_search.return_value = [
            {
                "chunk_id": "1",
                "content": "Test content",
                "document_name": "test.txt",
                "similarity": 0.9,
            }
        ]

        cohere_instance = mock_cohere.return_value
        cohere_instance.rerank.return_value = MagicMock(
            results=[MagicMock(index=0, relevance_score=0.95)]
        )

        mock_llm.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": "Answer [1]."}}],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 20,
                    "total_tokens": 70,
                },
            },
        )

        def make_query(i):
            start = time.time()
            response = client.post(
                "/api/query", json={"query": f"What is query {i}?", "top_k": 3}
            )
            duration = time.time() - start
            return {
                "index": i,
                "status_code": response.status_code,
                "duration": duration,
                "success": response.status_code == 200,
            }

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(make_query, range(50)))
        total_time = time.time() - start_time

        # Calculate statistics
        successes = sum(1 for r in results if r["success"])
        durations = [r["duration"] for r in results]
        avg_duration = sum(durations) / len(durations)
        p50_duration = sorted(durations)[int(len(durations) * 0.50)]
        p95_duration = sorted(durations)[int(len(durations) * 0.95)]
        p99_duration = sorted(durations)[int(len(durations) * 0.99)]

        print("\n=== Concurrent Query Results ===")
        print("Total queries: 50")
        print(f"Successful queries: {successes}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Throughput: {50/total_time:.2f} queries/sec")
        print(f"Average duration: {avg_duration:.3f}s")
        print(f"P50 duration: {p50_duration:.3f}s")
        print(f"P95 duration: {p95_duration:.3f}s")
        print(f"P99 duration: {p99_duration:.3f}s")

        # SLO: P95 should be under 3 seconds
        assert p95_duration < 3.0, f"P95 duration {p95_duration:.2f}s exceeds 3s SLO"
        # At least 90% should succeed
        assert successes >= 45, f"Only {successes}/50 queries succeeded"


@pytest.mark.slow
def test_mixed_load(client, sample_text_small):
    """Load test: Mixed uploads and queries simultaneously."""
    with (
        patch(
            "app.services.text_extraction.TextExtractor.extract_from_txt"
        ) as mock_extract,
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch("app.services.retrieval.RetrievalService.hybrid_search") as mock_search,
        patch("cohere.Client") as mock_cohere,
        patch("requests.post") as mock_llm,
        patch.object(app.dependency_overrides, "get", return_value=lambda: MagicMock()),
    ):
        mock_extract.return_value = "Extracted text"
        mock_embed.return_value = [0.1] * 768
        mock_search.return_value = [
            {
                "chunk_id": "1",
                "content": "Content",
                "document_name": "test.txt",
                "similarity": 0.9,
            }
        ]

        cohere_instance = mock_cohere.return_value
        cohere_instance.rerank.return_value = MagicMock(
            results=[MagicMock(index=0, relevance_score=0.95)]
        )

        mock_llm.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": "Answer."}}],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 20,
                    "total_tokens": 70,
                },
            },
        )

        def upload_or_query(i):
            start = time.time()
            if i % 2 == 0:
                # Upload
                sample_text_small.seek(0)
                files = {
                    "file": (
                        f"doc_{i}.txt",
                        BytesIO(sample_text_small.read()),
                        "text/plain",
                    )
                }
                response = client.post("/api/documents/upload", files=files)
                op_type = "upload"
            else:
                # Query
                response = client.post(
                    "/api/query", json={"query": f"Query {i}?", "top_k": 3}
                )
                op_type = "query"

            duration = time.time() - start
            return {
                "index": i,
                "type": op_type,
                "status_code": response.status_code,
                "duration": duration,
                "success": response.status_code in [200, 201],
            }

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(upload_or_query, range(20)))
        total_time = time.time() - start_time

        uploads = [r for r in results if r["type"] == "upload"]
        queries = [r for r in results if r["type"] == "query"]

        print("\n=== Mixed Load Results ===")
        print("Total operations: 20 (10 uploads, 10 queries)")
        print(f"Total time: {total_time:.2f}s")
        print(f"Successful uploads: {sum(1 for r in uploads if r['success'])}/10")
        print(f"Successful queries: {sum(1 for r in queries if r['success'])}/10")

        # At least 80% should succeed
        successes = sum(1 for r in results if r["success"])
        assert successes >= 16, f"Only {successes}/20 operations succeeded"
