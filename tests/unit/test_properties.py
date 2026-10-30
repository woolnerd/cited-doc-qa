"""Property-based tests for the deterministic parts of the pipeline.

Covers chunking, RRF fusion, citation-to-source mapping, and the eval scoring
functions. Model outputs and retrieval quality are measured by the evals in
evals/, not here.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.services.chunking import ChunkingService
from app.services.hybrid_search import HybridSearchService
from app.services.llm import LLMService
from hypothesis import assume, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.metrics import normalize, passage_coverage  # noqa: E402

METADATA = {"filename": "test.pdf", "file_type": "pdf"}
CHUNKER = ChunkingService()

# --- Chunking -----------------------------------------------------------------

words = st.text(
    alphabet=st.characters(categories=["L", "N", "P", "S"]), min_size=1, max_size=40
)
sentences = st.lists(words, min_size=1, max_size=30).map(
    lambda ws: " ".join(ws).capitalize() + "."
)
separators = st.sampled_from([" ", "  ", "\n", "\n\n", "\t"])


@st.composite
def documents(draw):
    """Sentence-like text, the shape the chunker is built for."""
    parts = draw(st.lists(sentences, min_size=1, max_size=40))
    out = parts[0]
    for part in parts[1:]:
        out += draw(separators) + part
    return out


any_text = st.text(min_size=1).filter(lambda t: t.strip())
chunk_sizes = st.integers(min_value=40, max_value=200).map(lambda mx: (mx // 2, mx))


def chunk(text: str, sizes: tuple[int, int]) -> list[dict]:
    min_size, max_size = sizes
    return CHUNKER.chunk_text(
        text, METADATA, min_chunk_size=min_size, max_chunk_size=max_size
    )


@hypothesis_settings(deadline=None)
@given(text=st.one_of(documents(), any_text), sizes=chunk_sizes)
def test_chunking_loses_no_text(text, sizes):
    """Joining the chunks gives back every word of the input, in order."""
    chunks = chunk(text, sizes)
    rebuilt = " ".join(c["content"] for c in chunks)
    assert rebuilt.split() == text.split()


@hypothesis_settings(deadline=None)
@given(text=st.one_of(documents(), any_text), sizes=chunk_sizes)
def test_chunks_are_non_empty_and_indexed_in_order(text, sizes):
    chunks = chunk(text, sizes)
    assert chunks
    assert all(c["content"].strip() for c in chunks)
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


@hypothesis_settings(deadline=None)
@given(text=st.one_of(documents(), any_text), sizes=chunk_sizes)
def test_contextual_content_and_token_count_match_content(text, sizes):
    for c in chunk(text, sizes):
        assert c["contextual_content"] == CHUNKER.create_contextual_chunk(
            c["content"], METADATA
        )
        assert c["token_count"] == CHUNKER.count_tokens(c["contextual_content"])


@hypothesis_settings(deadline=None)
@given(text=documents(), sizes=chunk_sizes)
def test_chunks_stay_within_max_tokens(text, sizes):
    """Only a single word too long to fit on its own may exceed the maximum."""
    _, max_size = sizes
    for c in chunk(text, sizes):
        if len(c["content"].split()) > 1:
            assert c["token_count"] <= max_size


@hypothesis_settings(deadline=None)
@given(
    word=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=300, max_size=2000),
    sizes=chunk_sizes,
)
def test_oversized_single_word_becomes_its_own_chunk(word, sizes):
    # Repetitive strings compress into few tokens, so check the word really is
    # too big to share a chunk.
    assume(CHUNKER.count_tokens(word) > sizes[1])
    text = f"Before this. {word} After this."
    chunks = chunk(text, sizes)
    assert word in [c["content"] for c in chunks]
    assert " ".join(c["content"] for c in chunks).split() == text.split()


@given(text=st.text(alphabet=" \t\n\r"))
def test_blank_text_is_rejected(text):
    with pytest.raises(DocumentProcessingError):
        CHUNKER.chunk_text(text, METADATA)


# --- RRF fusion ---------------------------------------------------------------

chunk_ids = st.sampled_from([f"c{i}" for i in range(25)])
ranked_ids = st.lists(chunk_ids, unique=True, max_size=20)


def as_results(ids: list[str]) -> list[dict]:
    """Search results in the shape vector and full-text search return."""
    return [
        {
            "chunk_id": cid,
            "document_id": "doc",
            "content": cid,
            "contextual_content": cid,
            "metadata": {},
            "rank": rank,
        }
        for rank, cid in enumerate(ids, start=1)
    ]


HYBRID = HybridSearchService(
    db=MagicMock(),
    embedding_service=MagicMock(),
    vector_search_service=MagicMock(),
    full_text_search_service=MagicMock(),
)


def fuse(vector_ids: list[str], fulltext_ids: list[str], k: int) -> list[dict]:
    """Merge with RRF and keep the top k, as HybridSearchService.search does."""
    merged = HYBRID._merge_results(as_results(vector_ids), as_results(fulltext_ids))
    return merged[:k]


@given(vector_ids=ranked_ids, fulltext_ids=ranked_ids, k=st.integers(1, 40))
def test_fusion_has_no_duplicates_and_respects_k(vector_ids, fulltext_ids, k):
    fused = [r["chunk_id"] for r in fuse(vector_ids, fulltext_ids, k)]
    assert len(fused) == len(set(fused))
    assert len(fused) <= k


@given(vector_ids=ranked_ids, fulltext_ids=ranked_ids)
def test_fusion_returns_exactly_the_input_items(vector_ids, fulltext_ids):
    fused = {r["chunk_id"] for r in fuse(vector_ids, fulltext_ids, k=100)}
    assert fused == set(vector_ids) | set(fulltext_ids)


@given(vector_ids=ranked_ids, fulltext_ids=ranked_ids)
def test_fusion_is_sorted_by_score_with_sequential_ranks(vector_ids, fulltext_ids):
    fused = fuse(vector_ids, fulltext_ids, k=100)
    scores = [r["rrf_score"] for r in fused]
    assert scores == sorted(scores, reverse=True)
    assert [r["final_rank"] for r in fused] == list(range(1, len(fused) + 1))


@given(vector_ids=ranked_ids, fulltext_ids=ranked_ids)
def test_fusion_score_is_sum_of_reciprocal_ranks(vector_ids, fulltext_ids):
    k = settings.RRF_K
    for r in fuse(vector_ids, fulltext_ids, k=100):
        expected = 0.0
        if r["chunk_id"] in vector_ids:
            expected += 1 / (k + vector_ids.index(r["chunk_id"]) + 1)
        if r["chunk_id"] in fulltext_ids:
            expected += 1 / (k + fulltext_ids.index(r["chunk_id"]) + 1)
        assert r["rrf_score"] == pytest.approx(expected)


@given(
    top=chunk_ids,
    vector_rest=ranked_ids,
    fulltext_rest=ranked_ids,
    k=st.integers(1, 40),
)
def test_item_first_in_both_lists_is_first_after_fusion(
    top, vector_rest, fulltext_rest, k
):
    vector_ids = [top] + [c for c in vector_rest if c != top]
    fulltext_ids = [top] + [c for c in fulltext_rest if c != top]
    assert fuse(vector_ids, fulltext_ids, k)[0]["chunk_id"] == top


# --- Citations ----------------------------------------------------------------


def make_llm(answer: str) -> LLMService:
    with patch("app.services.llm.OpenAI") as client_class:
        client = MagicMock()
        client_class.return_value = client
        service = LLMService(api_key="test", base_url="https://test")
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = answer
    response.choices[0].finish_reason = "stop"
    client.chat.completions.create.return_value = response
    return service


def as_reranked(ids: list[str]) -> list[dict]:
    return [
        {
            "chunk_id": cid,
            "document_id": f"doc-{cid}",
            "content": f"content of {cid}",
            "contextual_content": f"Document: d.pdf\n\ncontent of {cid}",
            "metadata": {"document_name": "d.pdf", "chunk_index": i},
            "rerank_score": 0.5,
        }
        for i, cid in enumerate(ids)
    ]


@given(
    ids=st.lists(chunk_ids, unique=True, max_size=15),
    cited=st.lists(st.integers(1, 15), max_size=10),
    demo_mode=st.booleans(),
)
def test_every_source_is_a_retrieved_chunk_numbered_as_in_the_context(
    ids, cited, demo_mode
):
    """Source n is the chunk the model saw as [n], whatever the answer cites."""
    results = as_reranked(ids)
    answer = " ".join(f"Claim [{n}]." for n in cited)
    service = make_llm(answer)

    with patch.object(settings, "DEMO_MODE", demo_mode):
        response = service.generate_answer("question", results)
        shown = service._limit_search_results(results)

    sources = response["sources"]
    context = service._format_context(shown)
    assert len(sources) == len(shown)
    for n, source in enumerate(sources, start=1):
        assert source["citation_num"] == n
        assert source["chunk_id"] in ids
        assert source["chunk_id"] == shown[n - 1]["chunk_id"]
        assert f"[{n}] {shown[n - 1]['contextual_content']}" in context


# --- Eval scoring -------------------------------------------------------------

plain_words = st.lists(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=8),
    min_size=1,
    max_size=20,
)
noise = st.text(alphabet=" \n\t.,;:!?()\"'-", min_size=1, max_size=3)


@given(passage=st.text(), chunk_text=st.text())
def test_coverage_is_between_zero_and_one(passage, chunk_text):
    assert 0.0 <= passage_coverage(passage, chunk_text) <= 1.0


@given(passage_words=plain_words, before=st.text(), after=st.text(), gaps=noise)
def test_passage_found_whatever_the_surrounding_text_and_punctuation(
    passage_words, before, after, gaps
):
    passage = " ".join(passage_words)
    chunk_text = f"{before} {gaps.join(passage_words)} {after}"
    assert passage_coverage(passage, chunk_text) == 1.0


@given(text=st.text())
def test_normalize_is_idempotent(text):
    words_once = normalize(text)
    assert normalize(" ".join(words_once)) == words_once
