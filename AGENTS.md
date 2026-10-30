# Agent Instructions

Cited Doc QA: upload documents, ask questions, get answers with source citations. FastAPI backend, Postgres + pgvector, vanilla JS frontend (no build step). Production runs at rag.getfreetime.ai and eta.getfreetime.ai.

For setup, architecture, and deployment details, read `docs/` and `deployment/vps/`. This file only covers what isn't obvious from them.

## Layout

- `backend/app/`: FastAPI app (`api/`, `services/`, `models/`, `core/config.py`)
- `frontend/`: static HTML/CSS/JS, served by the backend in production
- `tests/unit/`, `tests/integration/`: pytest suites (run from the repo root, not `backend/`)
- `migrations/`: numbered SQL files, applied by hand to the VPS database
- `deployment/vps/`: VPS setup, rollback, global-documents guides

## Commands

```bash
source venv/bin/activate
make test-unit        # pytest tests/unit/
make lint type-check  # ruff + mypy
make run              # backend on :8000
```

Pre-commit runs black, ruff, mypy, and bandit. Fix failures rather than skipping hooks.

## Retrieval pipeline

Query enhancement → hybrid search (pgvector + Postgres full-text, merged with RRF) → rerank → LLM answer with `[n]` citations. Everything is filtered by `session_id`: users see their own documents plus `session_id = 'global'`.

## Production config differs from code defaults

`core/config.py` and `.env.example` default to Gemini embeddings and direct Cohere rerank. Production (see `.env.vps.example`) uses:

- Embeddings: OpenRouter `openai/text-embedding-3-large`, 3072 dims
- Rerank: OpenRouter `cohere/rerank-v3.5`
- LLM: `anthropic/claude-haiku-4.5` via OpenRouter
- `SEARCH_SIMILARITY_THRESHOLD=0.0` (relevance is gated by the reranker's threshold; see `evals/README.md`)

**Do not change the embedding provider, model, or dimensions without re-embedding every document.** The stored vectors (including the global demo documents) were made with that model; a mismatch silently breaks vector search.

## Rules

- **Retrieval changes:** run `python -m evals.run` before and after changing search, rerank, chunking, or prompt settings, and compare with `python -m evals.compare`. See `evals/README.md`.

- **Config constants:** when changing a hardcoded value (model names, dimensions, thresholds), grep `tests/` for the old value. Unit tests assert exact strings in mock calls.
- **Image name:** `docker-compose.prod.yml` and `deploy.yml` must use `cited-doc-qa`, the repo name CI publishes to GHCR. `tests/unit/test_deployment_config.py` guards this.
- **Deploys:** pushing to `main` deploys to the VPS via GitHub Actions. Never push to `main` directly; open a PR.
- **Rollback:** see `deployment/vps/ROLLBACK.md`. Update it when you change Caddy, compose, env, or container setup.
- **Public repo:** keep secrets, server IPs, and personal documents out of commits. `sample_documents/real_docs/` is gitignored for that reason.
- **Commits:** conventional commits, `type(scope): description`.
