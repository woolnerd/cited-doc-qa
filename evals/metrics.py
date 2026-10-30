"""Pure scoring functions for the retrieval and answer evals.

Nothing here calls a database or a model, so it is all unit-tested in
tests/unit/test_eval_metrics.py.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

# A passage split across two chunks still counts as found if one chunk holds
# at least this share of its words in a contiguous run.
MIN_PASSAGE_COVERAGE = 0.5


@dataclass(frozen=True)
class RetrievedChunk:
    """The parts of a retrieved chunk that scoring needs."""

    document_name: str
    content: str


def normalize(text: str) -> list[str]:
    """Lowercase words with punctuation, ligatures, and spacing differences removed.

    PDF extraction produces ligatures (U+FB01 for "fi"), curly quotes, and
    line breaks mid-sentence. Comparing word lists sidesteps all of them.
    """
    folded = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^a-z0-9]+", " ", folded).split()


def passage_coverage(passage: str, chunk_text: str) -> float:
    """Share of the passage's words found in one contiguous run inside the chunk."""
    passage_words = normalize(passage)
    if not passage_words:
        return 0.0
    chunk_joined = " " + " ".join(normalize(chunk_text)) + " "

    n = len(passage_words)
    for length in range(n, 0, -1):
        for start in range(0, n - length + 1):
            window = " " + " ".join(passage_words[start : start + length]) + " "
            if window in chunk_joined:
                return length / n
    return 0.0


def chunk_matches(
    chunk: RetrievedChunk,
    source_document: str | None,
    passage: str,
    min_coverage: float = MIN_PASSAGE_COVERAGE,
) -> bool:
    """True if the chunk is from the expected document and contains the passage."""
    if source_document is not None and chunk.document_name != source_document:
        return False
    return passage_coverage(passage, chunk.content) >= min_coverage


def first_hit_rank(
    chunks: Sequence[RetrievedChunk],
    source_document: str | None,
    passages: Sequence[str],
) -> int | None:
    """1-based rank of the first chunk containing any expected passage."""
    for rank, chunk in enumerate(chunks, start=1):
        if any(chunk_matches(chunk, source_document, p) for p in passages):
            return rank
    return None


def passage_recall(
    chunks: Sequence[RetrievedChunk],
    source_document: str | None,
    passages: Sequence[str],
) -> float:
    """Share of expected passages found anywhere in the chunks."""
    if not passages:
        return 0.0
    found = sum(
        1 for p in passages if any(chunk_matches(c, source_document, p) for c in chunks)
    )
    return found / len(passages)


def cited_numbers(answer: str) -> list[int]:
    """Citation numbers like [1] or [2, 3] in an answer, in order of appearance."""
    numbers: list[int] = []
    for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", answer):
        numbers.extend(int(n) for n in group.split(","))
    return numbers


def citations_valid(answer: str, context_size: int) -> bool:
    """True if every citation in the answer points at a chunk the model was given."""
    return all(1 <= n <= context_size for n in cited_numbers(answer))


def mean(values: Sequence[float]) -> float | None:
    """Arithmetic mean, or None for an empty sequence."""
    return sum(values) / len(values) if values else None


def hit_rate(ranks: Sequence[int | None], k: int) -> float | None:
    """Share of questions whose first hit is at rank k or better."""
    return mean([1.0 if r is not None and r <= k else 0.0 for r in ranks])


def mean_reciprocal_rank(ranks: Sequence[int | None]) -> float | None:
    """Mean of 1/rank, counting misses as 0."""
    return mean([1.0 / r if r is not None else 0.0 for r in ranks])
