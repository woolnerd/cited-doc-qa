"""API tests for POST /api/query: search, rerank, answer, and citations."""

import asyncio

import pytest

from tests.integration.helpers import upload_and_process

pytestmark = pytest.mark.integration


async def test_query_answers_with_citations_from_session_document(
    client, session_id, fake_providers
):
    processed = await upload_and_process(client, session_id)

    response = await client.post(
        "/api/query",
        json={"session_id": session_id, "query": "What is Quokkalang used for?"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["answer"] == "Quokkalang is a programming language [1]."
    assert data["sources"], "expected at least one cited source"
    source = data["sources"][0]
    assert source["citation_num"] == 1
    assert source["document_id"] == processed["document_id"]
    assert source["document_name"] == "python.txt"
    assert source["rerank_score"] > 0
    # The LLM saw the retrieved chunk in its prompt.
    prompt = fake_providers.chat.completions.create.call_args.kwargs["messages"][-1]
    assert "data science" in prompt["content"]


async def test_query_does_not_see_other_sessions_documents(client, session_id):
    processed = await upload_and_process(client, session_id)

    response = await client.post(
        "/api/query",
        json={"session_id": "someone-else-entirely", "query": "What is Quokkalang?"},
    )

    assert response.status_code == 200
    cited = {s["document_id"] for s in response.json()["sources"]}
    assert processed["document_id"] not in cited


async def test_rerank_threshold_drops_irrelevant_chunks(client, session_id):
    """The chunk shares no words with the query, so its rerank score is 0."""
    processed = await upload_and_process(client, session_id)

    response = await client.post(
        "/api/query",
        json={"session_id": session_id, "query": "underwater basket weaving"},
    )

    assert response.status_code == 200
    cited = {s["document_id"] for s in response.json()["sources"]}
    assert processed["document_id"] not in cited


async def test_query_scoped_to_one_document(client, session_id):
    first = await upload_and_process(client, session_id)
    await upload_and_process(
        client,
        session_id,
        content=b"Quokkalang is also the name of a hiking trail in the Blue Mountains.",
        filename="snakes.txt",
    )

    response = await client.post(
        "/api/query",
        json={
            "session_id": session_id,
            "query": "What is Quokkalang?",
            "document_id": first["document_id"],
        },
    )

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert sources
    assert {s["document_id"] for s in sources} == {first["document_id"]}


async def test_concurrent_queries_all_succeed(client, session_id):
    await upload_and_process(client, session_id)

    responses = await asyncio.gather(
        *(
            client.post(
                "/api/query",
                json={"session_id": session_id, "query": f"Quokkalang question {i}"},
            )
            for i in range(5)
        )
    )

    assert [r.status_code for r in responses] == [200] * 5
