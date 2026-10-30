"""Record and replay embedding and rerank calls so the retrieval gate runs offline.

Recording calls OpenRouter once and saves every embedding and every
(question, chunk) rerank score to a JSON file. Replay serves those values
back through the same seams the app uses (EmbeddingService's HTTP call and
RerankingService's provider call), so chunking, the search SQL, full-text
matching, RRF, and the rerank threshold all still run for real.

Rerank scores are stored per (query, document) pair, not per request. A
cross-encoder scores each pair independently, so a search change that
alters the candidate list still replays cleanly as long as the chunks and
questions are unchanged.
"""

import base64
import hashlib
import json
import struct
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def pair_key(query: str, document: str) -> str:
    return text_key(query + "\x00" + document)


def encode_vector(vector: Sequence[float]) -> str:
    """Pack a vector as base64 float16. Halves the file size of float32.

    The precision loss doesn't matter here: the recording is the reference,
    so every gate run sees the same rounded values.
    """
    return base64.b64encode(struct.pack(f"<{len(vector)}e", *vector)).decode()


def decode_vector(encoded: str) -> list[float]:
    raw = base64.b64decode(encoded)
    return list(struct.unpack(f"<{len(raw) // 2}e", raw))


def rank_by_score(scores: Sequence[float], top_n: int) -> list[tuple[int, float]]:
    """(index, score) pairs, best first, the shape a rerank provider returns."""
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    return [(i, scores[i]) for i in order[:top_n]]


class ReplayMiss(Exception):
    """A text or (query, document) pair that the recording doesn't have."""


@dataclass
class Recording:
    embedding_model: str
    rerank_model: str
    embeddings: dict[str, str] = field(default_factory=dict)
    rerank_scores: dict[str, float] = field(default_factory=dict)
    misses: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Recording":
        data = json.loads(path.read_text())
        return cls(
            embedding_model=data["embedding_model"],
            rerank_model=data["rerank_model"],
            embeddings=data["embeddings"],
            rerank_scores=data["rerank_scores"],
        )

    def save(self, path: Path) -> None:
        data = {
            "embedding_model": self.embedding_model,
            "rerank_model": self.rerank_model,
            "embeddings": dict(sorted(self.embeddings.items())),
            "rerank_scores": dict(sorted(self.rerank_scores.items())),
        }
        path.write_text(json.dumps(data, indent=0) + "\n")

    def embedding(self, text: str) -> list[float]:
        encoded = self.embeddings.get(text_key(text))
        if encoded is None:
            self.misses.append(f"embedding for {text[:60]!r}")
            raise ReplayMiss(text[:60])
        return decode_vector(encoded)

    def rerank_score(self, query: str, document: str) -> float:
        score = self.rerank_scores.get(pair_key(query, document))
        if score is None:
            self.misses.append(f"rerank score for {query[:40]!r} / {document[:40]!r}")
            raise ReplayMiss(query[:40])
        return score


def replay_services(recording: Recording) -> tuple[Any, Any]:
    """An EmbeddingService and RerankingService that answer from the recording.

    App modules are imported here because they read settings at import time,
    and the caller sets the environment first.
    """
    from app.services.embeddings import EmbeddingService
    from app.services.reranking import RerankingService

    class ReplayEmbeddingService(EmbeddingService):
        def _openrouter_embeddings(
            self, input_texts: str | list[str]
        ) -> list[list[float]]:
            texts = [input_texts] if isinstance(input_texts, str) else input_texts
            return [recording.embedding(t) for t in texts]

    class ReplayRerankingService(RerankingService):
        def _rerank_via_provider(
            self, query: str, documents: list[str], top_n: int, timeout: float = 0
        ) -> list[tuple[int, float]]:
            scores = [recording.rerank_score(query, d) for d in documents]
            return rank_by_score(scores, top_n)

    reranker = ReplayRerankingService()
    # A miss is recorded in recording.misses; retrying it only adds backoff sleeps.
    reranker.max_retries = 1
    return ReplayEmbeddingService(), reranker


def recording_embedding_service(recording: Recording) -> Any:
    """An EmbeddingService that calls OpenRouter and saves what it gets back."""
    from app.services.embeddings import EmbeddingService

    class RecordingEmbeddingService(EmbeddingService):
        def _openrouter_embeddings(
            self, input_texts: str | list[str]
        ) -> list[list[float]]:
            vectors: list[list[float]] = super()._openrouter_embeddings(input_texts)
            texts = [input_texts] if isinstance(input_texts, str) else input_texts
            for text, vector in zip(texts, vectors, strict=True):
                recording.embeddings[text_key(text)] = encode_vector(vector)
            return vectors

    return RecordingEmbeddingService()
