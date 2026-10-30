"""Integration tests for the full-text search SQL functions.

These run the real Postgres functions, so they need a migrated database
(`make test-db` uses the eval database from evals/README.md).
"""

from uuid import uuid4

import pytest
from app.services.full_text_search import FullTextSearchService

pytestmark = pytest.mark.integration

CHUNK_TEXT = (
    "Employees may receive tuition reimbursement of up to $5,250 per "
    "calendar year for approved courses."
)


@pytest.fixture
async def session_with_chunk(db_service, track_document):
    """Insert one document with one chunk in a fresh session."""
    session_id = f"fts-test-{uuid4()}"
    doc_id = str(uuid4())
    await db_service.execute(
        "INSERT INTO documents (id, filename, file_type, session_id) "
        "VALUES ($1, 'handbook.txt', 'txt', $2)",
        doc_id,
        session_id,
    )
    track_document(doc_id)
    await db_service.execute(
        "INSERT INTO chunks (document_id, content, contextual_content, chunk_index) "
        "VALUES ($1, $2, $2, 0)",
        doc_id,
        CHUNK_TEXT,
    )
    return session_id, doc_id


async def test_question_matches_chunk_without_every_word(
    db_service, session_with_chunk
):
    """A natural-language question matches a chunk that has only some of its words."""
    session_id, doc_id = session_with_chunk
    service = FullTextSearchService(db=db_service)

    results = await service.search(
        "How much tuition reimbursement can an employee get per year?", session_id
    )

    assert any(r["document_id"] == doc_id for r in results)


async def test_by_document_search_also_matches_partial_terms(
    db_service, session_with_chunk
):
    session_id, doc_id = session_with_chunk
    service = FullTextSearchService(db=db_service)

    results = await service.search_by_document(
        "How much tuition reimbursement can an employee get?", doc_id, session_id
    )

    assert len(results) == 1


async def test_stopword_only_query_returns_nothing(db_service, session_with_chunk):
    session_id, _ = session_with_chunk
    service = FullTextSearchService(db=db_service)

    assert await service.search("what is the", session_id) == []


async def test_query_with_tsquery_syntax_characters_does_not_error(
    db_service, session_with_chunk
):
    """Characters that mean something in tsquery syntax are treated as text."""
    session_id, doc_id = session_with_chunk
    service = FullTextSearchService(db=db_service)

    results = await service.search(
        "tuition & (reimbursement | !year) 'calendar' <-> o'brien:*", session_id
    )

    assert any(r["document_id"] == doc_id for r in results)


async def test_chunk_matching_more_terms_ranks_higher(db_service, session_with_chunk):
    session_id, doc_id = session_with_chunk
    await db_service.execute(
        "INSERT INTO chunks (document_id, content, contextual_content, chunk_index) "
        "VALUES ($1, $2, $2, 1)",
        doc_id,
        "Approved courses are listed on the intranet.",
    )
    service = FullTextSearchService(db=db_service)

    results = await service.search(
        "tuition reimbursement for approved courses", session_id, limit=1000
    )

    # Session search also returns global documents, so keep only this test's.
    assert [r["content"] for r in results if r["document_id"] == doc_id] == [
        CHUNK_TEXT,
        "Approved courses are listed on the intranet.",
    ]
