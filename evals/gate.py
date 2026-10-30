"""Retrieval regression gate over synthetic documents, run in CI.

    python -m evals.gate check                    # replay recorded calls; exit 1 on a regression
    python -m evals.gate check --update-baseline  # accept the current numbers
    python -m evals.gate record                   # call OpenRouter and rewrite the recording

The documents and questions live in evals/fixtures/. `check` needs a migrated
pgvector database but no API key: embeddings and rerank scores come from
evals/fixtures/recording.json (see evals/replay.py). See evals/README.md.
"""

import argparse
import asyncio
import json
import os
import sys
from argparse import Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from evals.replay import (
    Recording,
    pair_key,
    recording_embedding_service,
    replay_services,
)
from evals.run import (
    INGEST_SESSION,
    PROD_CANDIDATES,
    PROD_RERANK_TOP_K,
    REPO_ROOT,
    answer_question,
    configure_environment,
    ingest_file,
    summarize,
)

FIXTURES = REPO_ROOT / "evals" / "fixtures"
DOCS_DIR = FIXTURES / "docs"
# Uploaded under another session. Retrieving any of it means session filtering broke.
OTHER_SESSION_DIR = FIXTURES / "other_session"
OTHER_SESSION = "someone-else"
DATASET = FIXTURES / "dataset.jsonl"
RECORDING = FIXTURES / "recording.json"
BASELINE = FIXTURES / "baseline.json"

# The fixtures are about 3,000 words. Production's 400-600 token chunks would
# give 9 chunks, fewer than the 10 candidates, so every chunk would be a
# candidate and search could not fail. Smaller chunks give 26.
CHUNK_MIN, CHUNK_MAX = 100, 180

# Higher is better for these.
GATED_METRICS = (
    "candidate_hit_rate",
    "candidate_mrr",
    "context_hit_at_1",
    "context_hit_at_5",
    "context_mrr",
    "context_recall",
)
# Lower is better. Either search alone finds most answers in a set this small,
# so these catch a search leg that silently stops returning anything.
GATED_ZERO_RATES = ("fulltext_zero_result_rate", "vector_zero_result_rate")
# Replay is deterministic, so this only absorbs float rounding.
TOLERANCE = 1e-9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", choices=["check", "record"])
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the current numbers to the baseline instead of comparing",
    )
    return parser.parse_args()


def regressions(
    baseline: dict[str, Any],
    current: dict[str, Any],
    metrics: Sequence[str] = GATED_METRICS,
    zero_rates: Sequence[str] = GATED_ZERO_RATES,
) -> list[str]:
    """Metrics that got worse than the baseline, plus any other-session leak."""
    problems = [
        f"{m}: {baseline[m]:.3f} -> {current[m]:.3f}"
        for m in metrics
        if current[m] < baseline[m] - TOLERANCE
    ]
    problems += [
        f"{m}: {baseline[m]:.3f} -> {current[m]:.3f}"
        for m in zero_rates
        if current[m] > baseline[m] + TOLERANCE
    ]
    if current["other_session_chunks"]:
        problems.append(
            f"other_session_chunks: {current['other_session_chunks']} chunks from "
            "another session were retrieved (session filtering is broken)"
        )
    return problems


def rank_changes(
    baseline: dict[str, dict[str, int | None]],
    current: dict[str, dict[str, int | None]],
) -> list[str]:
    """Per-question rank changes, so a failing gate says which questions moved."""
    lines = []
    for qid in sorted(baseline.keys() | current.keys()):
        before, after = baseline.get(qid, {}), current.get(qid, {})
        for stage in ("candidate_hit_rank", "context_hit_rank"):
            if before.get(stage) != after.get(stage):
                lines.append(
                    f"{qid} {stage}: {before.get(stage)} -> {after.get(stage)}"
                )
    return lines


def question_ranks(records: list[dict[str, Any]]) -> dict[str, dict[str, int | None]]:
    return {
        r["id"]: {
            "candidate_hit_rank": r["candidate_hit_rank"],
            "context_hit_rank": r["context_hit_rank"],
        }
        for r in records
        if "candidate_hit_rank" in r
    }


def count_other_session_chunks(records: list[dict[str, Any]]) -> int:
    names = {p.name for p in OTHER_SESSION_DIR.glob("*.txt")}
    return sum(
        1
        for r in records
        for stage in ("candidates", "context")
        for chunk in r[stage]
        if chunk["document_name"] in names
    )


def load_dataset() -> list[dict[str, Any]]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line]


async def ingest_fixtures(db: Any, embedding_service: Any) -> dict[str, int]:
    """Replace everything in the gate database with the fixture documents."""
    from app.services.document_processor import DocumentProcessor

    # TRUNCATE, not DELETE: fresh table files keep rows in insertion order.
    # Full-text ranks often tie, and Postgres breaks ties by physical row
    # order, so reused space after DELETE would reorder results between runs.
    await db.execute("TRUNCATE documents, chunks")
    processor = DocumentProcessor(db_service=db, embedding_service=embedding_service)
    counts = {}
    for folder, session in (
        (DOCS_DIR, INGEST_SESSION),
        (OTHER_SESSION_DIR, OTHER_SESSION),
    ):
        for path in sorted(folder.glob("*.txt")):
            counts[path.name] = await ingest_file(db, processor, path, session, {})
    return counts


async def run_questions(
    db: Any, embedding_service: Any, reranker: Any, dataset: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    from app.services.hybrid_search import HybridSearchService

    chunk_counts = await ingest_fixtures(db, embedding_service)
    services = {
        "hybrid": HybridSearchService(db=db, embedding_service=embedding_service),
        "reranker": reranker,
    }
    args = Namespace(
        candidates=PROD_CANDIDATES, rerank_top_k=PROD_RERANK_TOP_K, retrieval_only=True
    )
    records = [await answer_question(row, services, args) for row in dataset]
    summary = summarize(dataset, records)
    summary["other_session_chunks"] = count_other_session_chunks(records)
    return summary, records, chunk_counts


async def record(db: Any, dataset: list[dict[str, Any]]) -> Recording:
    """Embed every chunk and question, and rerank every question against every chunk."""
    from app.core.config import settings
    from app.services.reranking import RerankingService

    recording = Recording(settings.EMBEDDING_MODEL, settings.RERANK_MODEL)
    embedder = recording_embedding_service(recording)
    counts = await ingest_fixtures(db, embedder)
    print(f"Embedded {sum(counts.values())} chunks: {counts}")

    chunks = [
        r["contextual_content"]
        for r in await db.fetch("SELECT contextual_content FROM chunks")
    ]
    reranker = RerankingService()
    for row in dataset:
        question = row["question"]
        embedder.generate_query_embedding(question)
        scored = reranker._rerank_via_provider(question, chunks, top_n=len(chunks))
        if len(scored) != len(chunks):
            raise SystemExit(f"Rerank returned {len(scored)} of {len(chunks)} scores")
        for index, score in scored:
            recording.rerank_scores[pair_key(question, chunks[index])] = score
        print(f"  {row['id']}: reranked {len(chunks)} chunks")
    recording.save(RECORDING)
    print(f"Wrote {RECORDING.relative_to(REPO_ROOT)}")
    return recording


def write_baseline(
    summary: dict[str, Any], records: list[dict[str, Any]], chunk_counts: dict[str, int]
) -> None:
    from app.core.config import settings

    baseline = {
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": {
            "candidates": PROD_CANDIDATES,
            "rerank_top_k": PROD_RERANK_TOP_K,
            "chunking_tokens": f"{CHUNK_MIN}-{CHUNK_MAX}",
            "rerank_score_threshold": settings.RERANK_SCORE_THRESHOLD,
            "similarity_threshold": settings.SEARCH_SIMILARITY_THRESHOLD,
            "chunks_per_document": chunk_counts,
        },
        "summary": summary,
        "questions": question_ranks(records),
    }
    BASELINE.write_text(json.dumps(baseline, indent=2) + "\n")
    print(f"Wrote {BASELINE.relative_to(REPO_ROOT)}")


def report(summary: dict[str, Any], records: list[dict[str, Any]]) -> int:
    """Compare with the baseline, print the outcome, and return an exit code."""
    baseline = json.loads(BASELINE.read_text())
    for line in rank_changes(baseline["questions"], question_ranks(records)):
        print(f"  {line}")
    problems = regressions(baseline["summary"], summary)
    for metric in GATED_METRICS + GATED_ZERO_RATES:
        print(
            f"  {metric:26} {baseline['summary'][metric]:.3f} -> {summary[metric]:.3f}"
        )
    if problems:
        print("\nRetrieval regressed:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    improved = any(
        summary[m] > baseline["summary"][m] + TOLERANCE for m in GATED_METRICS
    ) or any(summary[m] < baseline["summary"][m] - TOLERANCE for m in GATED_ZERO_RATES)
    if improved:
        print(
            "\nRetrieval improved. Run with --update-baseline and commit the baseline."
        )
    else:
        print("\nNo regression.")
    return 0


async def main() -> int:
    args = parse_args()
    os.environ.setdefault("POSTGRES_DB", "rag_gate")
    configure_environment(
        Namespace(similarity_threshold=None, chunk_min=CHUNK_MIN, chunk_max=CHUNK_MAX)
    )

    from app.core.config import settings
    from app.services.database import DatabaseService

    dataset = load_dataset()
    db = DatabaseService()
    await db.connect()
    try:
        if args.mode == "record":
            await record(db, dataset)

        recording = Recording.load(RECORDING)
        recorded = (recording.embedding_model, recording.rerank_model)
        if recorded != (settings.EMBEDDING_MODEL, settings.RERANK_MODEL):
            print(
                f"The recording was made with {recorded}; settings use "
                f"{(settings.EMBEDDING_MODEL, settings.RERANK_MODEL)}. Re-record."
            )
            return 1
        embedder, reranker = replay_services(recording)
        try:
            summary, records, chunk_counts = await run_questions(
                db, embedder, reranker, dataset
            )
        except Exception:
            if not recording.misses:
                raise
            summary, records, chunk_counts = {}, [], {}
    finally:
        await db.disconnect()

    if recording.misses:
        print(f"{len(recording.misses)} calls are missing from the recording, e.g.:")
        for miss in recording.misses[:5]:
            print(f"  {miss}")
        print(
            "Chunking, the fixtures, or the questions changed. "
            "Run `python -m evals.gate record` and commit evals/fixtures/."
        )
        return 1
    if args.mode == "record" or args.update_baseline:
        write_baseline(summary, records, chunk_counts)
        return 0
    return report(summary, records)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
