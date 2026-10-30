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

## CI/CD

- **CI** (`.github/workflows/ci.yml`): lint, type-check, and tests on every push and PR
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
