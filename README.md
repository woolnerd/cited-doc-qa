# Cited Doc QA

[![CI](https://github.com/woolnerd/cited-doc-qa/actions/workflows/ci.yml/badge.svg)](https://github.com/woolnerd/cited-doc-qa/actions/workflows/ci.yml)
[![Deploy](https://github.com/woolnerd/cited-doc-qa/actions/workflows/deploy.yml/badge.svg)](https://github.com/woolnerd/cited-doc-qa/actions/workflows/deploy.yml)
[![codecov](https://codecov.io/gh/woolnerd/cited-doc-qa/branch/main/graph/badge.svg)](https://codecov.io/gh/woolnerd/cited-doc-qa)

A document Q&A app: upload documents, ask questions, and get answers with source citations. Built on hybrid search (vector + full-text), reranking, and Claude.

## Features

- **Document upload**: PDF, DOCX, and TXT with a drag-and-drop interface
- **Contextual chunking**: 400–600 token chunks with document context for better retrieval
- **Hybrid search**: pgvector similarity and Postgres full-text search, merged with Reciprocal Rank Fusion
- **Reranking**: Cohere rerank to keep only relevant chunks
- **Cited answers**: Claude answers with numbered `[n]` citations linked to source chunks
- **Session isolation**: each browser session sees its own uploads plus shared global documents
- **Demo mode**: per-session, per-IP, and daily limits for running as a public demo

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 15 + pgvector
- **Embeddings**: OpenAI `text-embedding-3-large` (3072 dimensions) via OpenRouter, or Gemini `gemini-embedding-001`
- **Reranking**: Cohere `rerank-v3.5` via OpenRouter, or Cohere directly
- **LLM**: Claude Haiku 4.5 via OpenRouter
- **Frontend**: vanilla HTML/CSS/JavaScript, no build step
- **Deployment**: Docker on a VPS behind Caddy, deployed by GitHub Actions

Providers and models are set in `.env`; see `.env.example` for local defaults and `.env.vps.example` for the production setup. Changing the embedding model requires re-embedding every document.

## Architecture

```
User → Upload → Text Extraction → Contextual Chunking → Embedding → Postgres
                                                                       ↓
User ← Cited Answer ← Claude ← Rerank ← Hybrid Search (RRF) ← Query Embedding ← Query Enhancement ← Question
```

### Document Processing Flow
1. Upload a document (PDF/DOCX/TXT)
2. Extract text
3. Split into contextual chunks (400–600 tokens)
4. Generate embeddings
5. Store chunks and vectors in Postgres

### Query Flow
1. User asks a question (with recent conversation history)
2. Rewrite the query for retrieval
3. Hybrid search, filtered to the user's session and global documents:
   - Vector similarity search (top 30)
   - Full-text search (top 30)
   - Merge with RRF
4. Rerank (top 5) and drop low-scoring chunks
5. Generate an answer with Claude
6. Return the answer with source citations

## Setup

### Prerequisites
- Python 3.11 or higher
- PostgreSQL 15 with the pgvector extension
- An OpenRouter API key (LLM, and embeddings/rerank in the production setup)
- Optionally Google AI (Gemini) and Cohere keys, if you use those providers directly

### Local Development

1. **Clone and set up**:
```bash
git clone https://github.com/woolnerd/cited-doc-qa.git
cd cited-doc-qa
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
```

2. **Configure environment variables**:
```bash
cp .env.example .env
# Edit .env with your database settings and API keys
```

3. **Set up the database**: create a database, then apply the files in `migrations/` in numeric order:
```bash
for f in migrations/*.sql; do psql -d rag_db -f "$f"; done
```

4. **Run the application**:
```bash
make run  # uvicorn on port 8000 with reload
```

5. **Open it**:
- App: http://localhost:8000
- API docs: http://localhost:8000/docs

See `docs/development.md` for more.

## Testing

```bash
make test-unit         # pytest tests/unit/
make test-integration  # pytest tests/integration/ (needs a database)
make test-cov          # with coverage report
make check-all         # format, lint, type-check, test
```

Performance tests live in `tests/performance/`; see the README there.

## What I measured and what I changed

I wrote 31 questions about the 9 documents on the live demo. Each answerable question has a reference answer and the exact passage that answers it; three questions test that the assistant says so when the documents can't answer. `evals/run.py` sends each question through the same search, rerank, and answer steps as the API, with production's models and settings, and scores retrieval (is the answer passage in what the LLM sees?) and the answer (correct, and supported by the retrieved text?, graded by a stronger Claude model). Details are in [`evals/README.md`](evals/README.md).

This is a small, hand-written set, so treat the numbers as evidence about one change, not as an accuracy figure.

### What the baseline showed

Vector search had a minimum cosine similarity of 0.45. With `text-embedding-3-large`, that cut too much: **6 of the 29 answerable questions got no search results at all**, so the app replied that it couldn't find anything. Examples include "How long should employees rub their hands together when handwashing?" and "How much tuition reimbursement can an employee get per year?", both answered verbatim in the documents.

Without the cutoff, the passage with the answer scored anywhere from 0.28 to 0.65 against its question, while the two questions the documents don't cover scored 0.38 and 0.44 against their closest chunks. A similarity cutoff can't separate those, so it was dropping good matches without reliably filtering bad ones.

### The change

I set `SEARCH_SIMILARITY_THRESHOLD` to 0, so vector search always returns its top candidates, and left relevance to the Cohere reranker's existing score threshold (0.1). I did not tune a new cutoff against these questions, since that would just fit the test set.

### Before and after

Retrieval counts are out of the 29 questions with an expected passage and were identical across two runs. Answer counts are out of all 31 questions; the two runs per setting are shown because generation and grading vary.

| | Threshold 0.45 (before) | Threshold 0 (after) |
|---|---|---|
| Answer passage anywhere in search results | 19 / 29 | 27 / 29 |
| Answer passage in the LLM's context (top 5 after rerank) | 19 / 29 | 27 / 29 |
| Answer passage ranked first | 17 / 29 | 24 / 29 |
| Answers judged correct (run 1, run 2) | 22, 22 / 31 | 28, 29 / 31 |
| Answers judged incorrect (run 1, run 2) | 8, 8 / 31 | 0, 0 / 31 |
| Uncovered questions correctly declined | 2 / 2 | 2 / 2 |
| Mean faithfulness (run 1, run 2) | 0.94, 0.95 | 0.93, 0.92 |
| Answers whose citations all point at real context | 31 / 31 | 31 / 31 |

### What didn't improve, and what I'd look at next

- **Faithfulness stayed flat.** About 7% of answer claims aren't supported by the retrieved text. Most are harmless padding ("the clearance is a safety measure to prevent fire hazards"), but a few are real errors.
- **More context brought a new failure: mixing documents.** The demo has three employee handbooks with different policies. With more candidates reaching the model, some answers combined them. For example, the NFIB handbook's "full-day or half-day vacation only" rule came back next to another handbook's one-hour increments. Two of the three remaining "partial" grades are this kind of problem; the third left out a detail. Grouping context by document, or asking which handbook the user means, would be the next thing to try. (Since tried; see [Naming the document in overlapping questions](#naming-the-document-in-overlapping-questions) and [Grouping context by document](#grouping-context-by-document).)
- **Full-text search almost never contributes.** It returned nothing for 81% of questions, because `websearch_to_tsquery` requires every word of a natural-language question to appear in one chunk. Switching to an OR-style query would make hybrid search actually hybrid. I left it unchanged so this comparison measures one change. (Since fixed; see [Full-text search](#full-text-search-match-any-word-not-every-word).)
- **Two passages are still missed.** One is in a chunk where the PDF's sidebar layout scrambled the text, and the other ranks 59th by vector similarity. In both cases the model still answered correctly from a similar passage elsewhere.

### Checking the grader

The correctness grades above come from a model, so I graded 40 of the answers myself without seeing its verdicts. The sample had every answer the judge didn't mark correct (17) plus 23 random ones it did, since a purely random sample would be almost all "correct".

| | All 40 | Without the app's canned "couldn't find" reply (33) |
|---|---|---|
| Agreement | 38 / 40 (95%) | 31 / 33 (94%) |
| Cohen's kappa | 0.91 | 0.87 |

Both disagreements are the same question in two runs, and they point at the dataset, not the judge. The question asks whether prescription drugs are covered by the drug-free workplace policy. The reference answer says "prescription and over-the-counter medications" are an exception, so the judge marked answers that only discussed prescription drugs as partial. I graded them against the question and called them correct. The reference answer asks for more than the question does.

I changed the reference answer to cover only prescription drugs and ran the eval twice more. The judge marked `nfib-03` correct in both runs (before: partial in one of two), and correct answers came to 30 and 29 of 31. Every remaining partial is an answer that puts two documents' conflicting rules side by side: `nfib-01` in both runs, and `rest-03` in one, where the restaurant SOP says to calibrate thermometers daily and the operations manual says weekly.

My grading notes also flagged the same weakness as above: four of the answers I graded struggled with two handbooks' conflicting policies.

Limits: one grader, who also wrote the reference answers, and a sample weighted toward the judge's non-correct verdicts. This shows the judge grades the way I would on this dataset; it doesn't show it would match other graders. Details are in [`evals/README.md`](evals/README.md#checking-the-judge).

### Full-text search: match any word, not every word

Migration `010_fulltext_or_query.sql` builds the full-text query from the question's stemmed words joined with OR instead of AND. Stop words are dropped, and `ts_rank` still ranks chunks that match more words higher. Before and after are two runs each with the same dataset (`results/nfib03-fix*.json` and `results/fulltext-or*.json`).

| | AND (before) | OR (after) |
|---|---|---|
| Full-text search returned nothing | 25 / 31 | 0 / 31 |
| Answer passage anywhere in search results | 27 / 29 | 28 / 29 |
| Answer passage in the LLM's context | 27 / 29 | 28 / 29 |
| Answer passage ranked first | 24 / 29 | 24 / 29 |
| MRR of answer passage | 0.87 | 0.89 |
| Answers judged correct (run 1, run 2) | 30, 29 / 31 | 29, 30 / 31 |
| Answers judged incorrect | 0, 0 / 31 | 0, 0 / 31 |

Retrieval numbers were identical across both runs on each side. The gain is one question: "Is there an open-door policy for raising workplace concerns?" (`nfib-02`). Its answer passage ranks 28th by vector similarity and didn't survive the merge into the candidate list; full-text search ranks it first, so it now reaches the reranker, which puts it second in the context. In 9 other questions the answer passage moved up in the candidate list, but it was already first or second after reranking, so the final context barely changed.

Answer grades didn't move beyond run-to-run noise. The remaining partials are still `nfib-01` (two handbooks' vacation rules side by side) in every run, plus one different question per run. Faithfulness went 0.93/0.95 before and 0.98/0.93 after, which is also within noise.

So this is a small retrieval improvement, not an answer-quality one. On this dataset vector search already finds most passages, so keyword matching mostly helps when a question uses the document's own wording and the embedding misses it.

### Tied full-text ranks

Building the CI check turned up a bug: the full-text SQL sorted by `ts_rank` alone. With the OR query, ties are common, and Postgres returns tied rows in whatever order they're stored on disk, which changes as rows are deleted and space is reused. The same question could get a different candidate list later. Migration `011_fulltext_tiebreak.sql` breaks ties by filename, then chunk index.

On the 31 demo questions (retrieval only, `results/tiebreak-*.json`), every retrieval metric stayed the same. The candidate lists didn't: 6 questions got a different set of chunks in the top 10, and 7 more got the same chunks in a different order. None of the 5 chunks the LLM sees changed for any question. So this fixes repeatability, not accuracy: the results no longer depend on storage order.

### Naming the document in overlapping questions

Three employee handbooks and three restaurant manuals cover overlapping topics, often with different rules. Some of my questions were ambiguous across them. "Can vacation be taken in partial days?" has one answer in one handbook and another in a different handbook, but its reference answer assumes one policy. Answers that were right for one handbook were graded against a reference written for another.

The decision: questions about overlapping documents now name the document, as a user would after seeing the filename in the app's document list. 17 questions changed, and only their `question` field. The ids, reference answers, and passages are the same. The new wording is in `evals/dataset.jsonl`. The human-graded sample in `evals/human_grades/sample.csv` was graded on the old wording, so its agreement numbers apply to the old questions.

Retrieval counts are out of the 29 questions with an expected passage. Answer counts are out of all 31. Each setting was run twice (`results/doc-grouping-before*.json` and `results/anchored*.json`).

| | Unanchored (before) | Anchored (after) |
|---|---|---|
| Answer passage in search candidates | 28 / 29, 28 / 29 | 29 / 29, 29 / 29 |
| Answer passage ranked first (hit@1) | 24 / 29, 24 / 29 | 28 / 29, 28 / 29 |
| MRR of answer passage in the LLM's context | 0.89, 0.89 | 0.98, 0.98 |
| Answers judged correct | 30, 29 / 31 | 30, 30 / 31 |
| Answers judged partial | 1, 2 / 31 | 1, 1 / 31 |
| Answers judged incorrect | 0, 0 / 31 | 0, 0 / 31 |
| Mean faithfulness | 0.95, 0.93 | 0.91, 0.94 |
| Answers with every claim supported | 77%, 74% | 68%, 71% |
| Answers whose citations all point at real context | 100%, 100% | 100%, 100% |

Retrieval improved. One passage (`rest-01`) was missing from the candidates before and is now ranked first. Four others (`nfib-02`, `nfib-03`, `pc-02`, `pc-03`) moved up in the final context.

Answers: `nfib-01` was partial in every earlier run and is correct in both anchored runs. `rest-03` was partial in one earlier run and correct in both anchored runs. `sfc-02` was correct in both earlier runs and partial in both anchored runs: the answer gave the disposal step but left out registering the wasted food in the cash register. Its passage was the first chunk in the context in every run, and the missing step is in that chunk. The other four chunks changed, and the anchored answers quoted only the disposal line. I read this as generation variance, not a retrieval loss.

Faithfulness did not improve. Mean faithfulness was 0.91 and 0.94 (before: 0.95 and 0.93), and the share of fully supported answers fell from 77% and 74% to 68% and 71%. This is one set of 31 questions, so treat the answer changes as small.

### Grouping context by document

The LLM's context used to be a flat list in rerank order. With three handbooks in the candidates, answers sometimes blended their rules. The change groups the context under one header per document, keeps each chunk's citation number and rerank order, and adds prompt rules: don't merge rules from different documents, and when documents disagree, give each answer separately and name its document. Retrieval is unchanged, so only the layout and the prompt differ.

I measured it twice: on the old wording, then on the anchored questions. On the old wording, grouping made the answers attribute each rule to its document, but judge-graded correctness fell from 30 and 29 to 28 and 28 of 31. In the grouped runs the judge marked `pc-02` partial because its answer hedged between two handbooks' policies, which conflicts with a single reference answer.

Retrieval was identical with and without grouping on both question sets. Counts are out of 31 answers, and each setting was run twice (`results/doc-grouping*.json`, `results/anchored*.json`).

| | Unanchored, no grouping | Unanchored, grouped | Anchored, no grouping | Anchored, grouped |
|---|---|---|---|---|
| Answers judged correct (run 1, run 2) | 30, 29 | 28, 28 | 30, 30 | 31, 31 |
| Answers judged partial | 1, 2 | 3, 3 | 1, 1 | 0, 0 |
| Mean faithfulness | 0.95, 0.93 | 0.96, 0.96 | 0.91, 0.94 | 0.97, 0.91 |
| Answers with every claim supported | 77%, 74% | 74%, 84% | 68%, 71% | 84%, 63% |
| Answer passage ranked first (hit@1, of 29) | 24 | 24 | 28 | 28 |
| MRR of answer passage | 0.89 | 0.89 | 0.98 | 0.98 |

The three questions I was watching:

- **`nfib-01`** (vacation in partial days) was partial in every unanchored run, with or without grouping. It was correct in all four anchored runs. In the unanchored grouped answers, each rule is attributed to its handbook; that is an observation from reading the answers, not a metric.
- **`rest-03`** (thermometer calibration) was correct in one unanchored run and partial in the other, and partial in both grouped unanchored runs. It was correct in all four anchored runs.
- **`pc-02`** (sick leave waiting period) was correct in every run without grouping, before and after anchoring, and partial in both unanchored grouped runs.

On the anchored questions, grouping makes little measurable difference. The one verdict that changed is `sfc-02`, which went from partial to correct in both pairs of runs. Faithfulness rose in one run and fell in the other. Each run has 31 questions, so none of these differences is strong evidence. What the eval does show is that anchoring removes most of the ambiguity that grouping was meant to address, and that on the unanchored wording grouping cost one or two correct answers per run, because the judge grades a per-document answer against a single reference.

### A retrieval check on every PR

The eval above needs the 9 demo PDFs, which aren't in the repo, and an API key, so it only runs on my machine. CI now runs a smaller retrieval-only version, `python -m evals.gate check`, against four fictional documents in `evals/fixtures/`: two employee handbooks for different companies with the same sections and different numbers, a cooler maintenance guide, and a linen service agreement. A fifth document is uploaded under a different session, and the check fails if any of it is ever retrieved. There are 21 questions.

Embeddings and rerank scores are recorded once and replayed, so the check needs no API key and gives the same numbers every run. Rerank scores are recorded for every question against every chunk, so a change to search that changes the candidate list still replays cleanly. Everything else runs for real against Postgres: chunking, the vector and full-text SQL, RRF, and the rerank threshold. The check fails if any retrieval metric drops below the committed baseline, or if either search starts returning nothing.

To see whether it catches anything, I broke the code five ways. Every one failed the check:

| Break | What failed |
|---|---|
| Vector search queries the wrong session | 5 chunks from another session retrieved |
| Full-text search returns nothing | candidate MRR 0.82 → 0.70, full-text empty 0% → 100% |
| Vector search returns nothing | candidate MRR 0.82 → 0.80, vector empty 0% → 100% |
| RRF ranks the worst match first | every metric → 0 |
| Migration 010 reverted (full-text back to AND) | candidate MRR 0.82 → 0.72, full-text empty 0% → 95% |

The first version only gated on hit rates and MRR after reranking, and it missed both "search returns nothing" breaks: with 28 chunks, either search alone finds every answer in the top 10, and the reranker fixes the order. Gating on candidate MRR and on each search's empty rate fixed that.

Limits: the fixtures are small and written by me, and the check uses 100-180 token chunks instead of production's 400-600 so that 3,000 words make 28 chunks rather than 9. It catches retrieval code that breaks, not small tuning effects. Because calls are replayed, it won't notice the embedding or rerank provider changing behavior; the full eval does that.

## CI/CD

- **CI** (`.github/workflows/ci.yml`): lint, type-check, and tests on every push and PR
- **Retrieval gate** (same workflow): replays the fixture eval against a pgvector service container and fails on a retrieval regression; see [A retrieval check on every PR](#a-retrieval-check-on-every-pr)
- **Deploy** (`.github/workflows/deploy.yml`): builds `ghcr.io/woolnerd/cited-doc-qa` and deploys to the VPS on every push to `main`

See `docs/deployment.md` for setup and `deployment/vps/ROLLBACK.md` for rolling back.

## API

All document and query endpoints take a `session_id`. Users can see, search, and delete only their own documents, plus read-only global documents.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/documents/upload` | Upload a file (multipart: `file`, `session_id`) |
| `POST` | `/api/documents/{id}/process` | Extract, chunk, and embed an uploaded document |
| `GET` | `/api/documents?session_id=...` | List session and global documents |
| `GET` | `/api/documents/{id}` | Document metadata |
| `GET` | `/api/documents/{id}/source-url` | Signed URL for the original file, if an operator mapped one |
| `DELETE` | `/api/documents/{id}?session_id=...` | Delete a document and its chunks |
| `POST` | `/api/query` | Ask a question |

### `POST /api/query`

**Request**:
```json
{
  "session_id": "abc123",
  "query": "What is the notice period for terminating the lease?",
  "document_id": null,
  "conversation_history": []
}
```

**Response** (abridged):
```json
{
  "success": true,
  "answer": "The tenant must give 60 days' written notice [1].",
  "sources": [
    {
      "citation_num": 1,
      "document_name": "lease.pdf",
      "chunk_index": 12,
      "content": "relevant chunk...",
      "rerank_score": 0.91
    }
  ],
  "metadata": {
    "model": "anthropic/claude-haiku-4.5",
    "results_count": 5,
    "timing": {"total_ms": 3120.5}
  }
}
```

Full schemas are at `/docs` when the app is running.

## Limitations

- Scanned PDFs (images only) are not supported; there is no OCR
- Max file size is 10 MB by default
- Demo mode caps uploads, queries, and total upload size per session

## Support

For issues and questions, please open a GitHub issue.

---

**Built with Claude Code** 🤖
