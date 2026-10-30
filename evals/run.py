"""Run the retrieval and answer evals against a local pgvector database.

    python -m evals.run --label current
    python -m evals.run --label baseline --similarity-threshold 0.45

Each run ingests the live demo documents (if the chunking settings changed),
answers every question in evals/dataset.jsonl with the same search, rerank,
and generation steps as POST /api/query, and writes evals/results/<label>.json.
See evals/README.md for setup.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPO_ROOT / "evals" / "dataset.jsonl"
RESULTS_DIR = REPO_ROOT / "evals" / "results"
DOCS_DIR = REPO_ROOT / "sample_documents" / "real_docs"

# Production settings (see .env.vps.example). The eval database is local and
# throwaway; everything else matches what the live demo runs.
EVAL_ENV = {
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5433",
    "POSTGRES_DB": "rag_eval",
    "POSTGRES_USER": "rag_user",
    "POSTGRES_PASSWORD": "evalpass",
    "EMBEDDING_PROVIDER": "openrouter",
    "EMBEDDING_MODEL": "openai/text-embedding-3-large",
    "EMBEDDING_DIMENSIONS": "3072",
    "RERANK_PROVIDER": "openrouter",
    "RERANK_MODEL": "cohere/rerank-v3.5",
    "LLM_MODEL": "anthropic/claude-haiku-4.5",
    "DEMO_MODE": "false",
    "LOG_LEVEL": "WARNING",
}

# Production runs in demo mode: hybrid search returns DEMO_MAX_RETRIEVED_CHUNKS
# candidates, the reranker keeps the request's top_k (default 5), and
# completions are capped at DEMO_MAX_COMPLETION_TOKENS.
PROD_CANDIDATES = 10
PROD_RERANK_TOP_K = 5
PROD_MAX_COMPLETION_TOKENS = 1000

INGEST_SESSION = "global"
QUERY_SESSION = "eval"
NO_RESULTS_ANSWER = (
    "I couldn't find any relevant information in the documents to answer your question."
)
DEFAULT_JUDGE_MODEL = "anthropic/claude-sonnet-5.5"
# Results keep a short preview of each chunk; scoring runs on the full text first.
PREVIEW_CHARS = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--label", required=True, help="Name for this run's results")
    parser.add_argument("--candidates", type=int, default=PROD_CANDIDATES)
    parser.add_argument("--rerank-top-k", type=int, default=PROD_RERANK_TOP_K)
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        help="Override SEARCH_SIMILARITY_THRESHOLD (app default: 0.0)",
    )
    parser.add_argument("--chunk-min", type=int, default=400)
    parser.add_argument("--chunk-max", type=int, default=600)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument(
        "--retrieval-only", action="store_true", help="Skip answers and judging"
    )
    parser.add_argument("--limit", type=int, help="Only run the first N questions")
    return parser.parse_args()


def configure_environment(args: argparse.Namespace) -> None:
    """Set app settings before any app module is imported (they load at import)."""
    for key, value in EVAL_ENV.items():
        os.environ.setdefault(key, value)
    if args.similarity_threshold is not None:
        os.environ["SEARCH_SIMILARITY_THRESHOLD"] = str(args.similarity_threshold)
    os.environ["CHUNK_SIZE_MIN"] = str(args.chunk_min)
    os.environ["CHUNK_SIZE_MAX"] = str(args.chunk_max)
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    # Settings read backend/.env or .env relative to the working directory.
    os.chdir(REPO_ROOT)


def load_dataset(limit: int | None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in DATASET.read_text().splitlines() if line]
    return rows[:limit] if limit else rows


async def ensure_ingested(db: Any, chunking: str) -> dict[str, int]:
    """Ingest the demo documents unless they are already in with this chunking."""
    from app.services.document_processor import DocumentProcessor

    files = sorted(DOCS_DIR.glob("*.pdf"))
    if not files:
        raise SystemExit(f"No PDFs in {DOCS_DIR}. See evals/README.md.")

    existing = await db.fetch(
        "SELECT filename, metadata->>'eval_chunking' AS chunking FROM documents"
    )
    if {r["filename"] for r in existing} == {f.name for f in files} and all(
        r["chunking"] == chunking for r in existing
    ):
        rows = await db.fetch(
            "SELECT d.filename, count(c.id) AS n FROM documents d "
            "JOIN chunks c ON c.document_id = d.id GROUP BY d.filename"
        )
        return {r["filename"]: r["n"] for r in rows}

    print(f"Ingesting {len(files)} documents with chunking {chunking}...")
    await db.execute("DELETE FROM documents")  # chunks cascade
    processor = DocumentProcessor(db_service=db)
    counts: dict[str, int] = {}
    for path in files:
        counts[path.name] = await ingest_file(
            db, processor, path, INGEST_SESSION, {"eval_chunking": chunking}
        )
        print(f"  {path.name}: {counts[path.name]} chunks")
    return counts


async def ingest_file(
    db: Any, processor: Any, path: Path, session_id: str, metadata: dict[str, Any]
) -> int:
    """Insert one document row, chunk and embed the file, and return its chunk count."""
    file_type = path.suffix.lstrip(".")
    doc_id = await db.fetchval(
        "INSERT INTO documents (filename, file_type, upload_date, session_id, metadata) "
        "VALUES ($1, $2, now(), $3, $4::jsonb) RETURNING id",
        path.name,
        file_type,
        session_id,
        json.dumps(metadata),
    )
    result = await processor.process_document(
        doc_id, path.read_bytes(), path.name, file_type
    )
    return int(result["num_chunks"])


def chunk_summary(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata") or {}
    return {
        "document_name": metadata.get("document_name"),
        "chunk_index": metadata.get("chunk_index"),
        "content": result.get("content", ""),
        "vector_rank": result.get("vector_rank"),
        "fulltext_rank": result.get("fulltext_rank"),
        "rerank_score": result.get("rerank_score"),
    }


async def answer_question(
    row: dict[str, Any], services: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    """Mirror POST /api/query for one question and record every stage."""
    question = row["question"]
    search = await services["hybrid"].search(
        query=question, session_id=QUERY_SESSION, top_k=args.candidates
    )
    candidates = search["results"]

    final: list[dict[str, Any]] = []
    if candidates:
        reranked = await asyncio.to_thread(
            services["reranker"].rerank_with_metadata,
            question,
            candidates,
            args.rerank_top_k,
        )
        final = reranked["results"]

    record: dict[str, Any] = {
        "id": row["id"],
        "fulltext_results": search["metadata"]["fulltext_results_count"],
        "vector_results": search["metadata"]["vector_results_count"],
        "candidates": [chunk_summary(c) for c in candidates],
        "context": [chunk_summary(c) for c in final],
    }
    if args.retrieval_only:
        return record

    if final:
        llm = await asyncio.to_thread(
            services["llm"].generate_answer_with_retry,
            query=question,
            search_results=final,
            max_tokens=PROD_MAX_COMPLETION_TOKENS,
        )
        record["answer"] = llm["answer"]
    else:
        record["answer"] = NO_RESULTS_ANSWER

    judge = services["judge"]
    record["correctness"] = await asyncio.to_thread(
        judge.correctness, question, row["expected_answer"], record["answer"]
    )
    record["faithfulness"] = (
        await asyncio.to_thread(judge.faithfulness, record["answer"], record["context"])
        if final
        else {"score": None, "claims": []}
    )
    return record


def summarize(
    dataset: list[dict[str, Any]], records: list[dict[str, Any]]
) -> dict[str, Any]:
    from evals.metrics import (
        RetrievedChunk,
        citations_valid,
        first_hit_rank,
        hit_rate,
        mean,
        mean_reciprocal_rank,
        passage_recall,
    )

    by_id = {r["id"]: r for r in records}
    retrieval_rows = [d for d in dataset if d["expected_passages"]]

    def chunks(record: dict[str, Any], stage: str) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(c["document_name"] or "", c["content"])
            for c in record[stage]
        ]

    candidate_ranks, context_ranks, recalls = [], [], []
    for d in retrieval_rows:
        rec = by_id[d["id"]]
        args = (d["source_document"], d["expected_passages"])
        rec["candidate_hit_rank"] = first_hit_rank(chunks(rec, "candidates"), *args)
        rec["context_hit_rank"] = first_hit_rank(chunks(rec, "context"), *args)
        candidate_ranks.append(rec["candidate_hit_rank"])
        context_ranks.append(rec["context_hit_rank"])
        recalls.append(passage_recall(chunks(rec, "context"), *args))

    summary: dict[str, Any] = {
        "questions": len(dataset),
        "retrieval_questions": len(retrieval_rows),
        "candidate_hit_rate": hit_rate(candidate_ranks, 10**6),
        "candidate_mrr": mean_reciprocal_rank(candidate_ranks),
        "context_hit_at_1": hit_rate(context_ranks, 1),
        "context_hit_at_3": hit_rate(context_ranks, 3),
        "context_hit_at_5": hit_rate(context_ranks, 5),
        "context_mrr": mean_reciprocal_rank(context_ranks),
        "context_recall": mean(recalls),
        "fulltext_zero_result_rate": mean(
            [1.0 if r["fulltext_results"] == 0 else 0.0 for r in records]
        ),
        "vector_zero_result_rate": mean(
            [1.0 if r["vector_results"] == 0 else 0.0 for r in records]
        ),
    }

    answered = [r for r in records if "answer" in r]
    if answered:
        verdicts = [r["correctness"]["verdict"] for r in answered]
        faith = [
            r["faithfulness"]["score"]
            for r in answered
            if r["faithfulness"]["score"] is not None
        ]
        summary.update(
            {
                "answer_correct": verdicts.count("correct") / len(verdicts),
                "answer_partial": verdicts.count("partial") / len(verdicts),
                "answer_incorrect": verdicts.count("incorrect") / len(verdicts),
                "faithfulness_mean": mean(faith),
                "fully_faithful_rate": mean([1.0 if f == 1.0 else 0.0 for f in faith]),
                "citations_valid_rate": mean(
                    [
                        1.0 if citations_valid(r["answer"], len(r["context"])) else 0.0
                        for r in answered
                    ]
                ),
            }
        )
    return summary


def print_summary(label: str, summary: dict[str, Any]) -> None:
    print(f"\n{label}")
    for key, value in summary.items():
        shown = f"{value:.3f}" if isinstance(value, float) else value
        print(f"  {key:28} {shown}")


async def main() -> None:
    args = parse_args()
    configure_environment(args)

    from app.core.config import settings
    from app.services.database import DatabaseService
    from app.services.hybrid_search import HybridSearchService
    from app.services.llm import LLMService
    from app.services.reranking import RerankingService
    from openai import OpenAI

    from evals.judge import Judge

    dataset = load_dataset(args.limit)
    db = DatabaseService()
    await db.connect()
    try:
        chunking = f"{args.chunk_min}-{args.chunk_max}"
        chunk_counts = await ensure_ingested(db, chunking)
        services = {
            "hybrid": HybridSearchService(db=db),
            "reranker": RerankingService(),
            "llm": LLMService(),
            "judge": Judge(
                OpenAI(
                    base_url=settings.OPENROUTER_BASE_URL,
                    api_key=settings.OPENROUTER_API_KEY,
                ),
                args.judge_model,
            ),
        }

        records = []
        started = time.time()
        for i, row in enumerate(dataset, start=1):
            print(f"[{i}/{len(dataset)}] {row['id']}", flush=True)
            records.append(await answer_question(row, services, args))
    finally:
        await db.disconnect()

    summary = summarize(dataset, records)
    for record in records:
        for stage in ("candidates", "context"):
            for chunk in record[stage]:
                chunk["preview"] = chunk.pop("content")[:PREVIEW_CHARS]
    output = {
        "label": args.label,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_seconds": round(time.time() - started),
        "config": {
            "candidates": args.candidates,
            "rerank_top_k": args.rerank_top_k,
            "chunking_tokens": chunking,
            "embedding_model": settings.EMBEDDING_MODEL,
            "rerank_model": settings.RERANK_MODEL,
            "rerank_score_threshold": settings.RERANK_SCORE_THRESHOLD,
            "similarity_threshold": settings.SEARCH_SIMILARITY_THRESHOLD,
            "llm_model": settings.LLM_MODEL,
            "judge_model": None if args.retrieval_only else args.judge_model,
            "chunks_per_document": chunk_counts,
        },
        "summary": summary,
        "records": records,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{args.label}.json"
    path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    print_summary(args.label, summary)
    print(f"\nWrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
