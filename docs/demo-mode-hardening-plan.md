# Public Demo Mode Hardening Plan

## Goal

Add reusable safeguards to the base RAG application so public-facing demos are
protected from abuse, spam, excessive usage, and unexpected provider costs.

This work belongs in `production-rag-system` first. Branded downstream repos,
including ETA-specific deployments, should inherit these changes and only carry
their own copy, styling, sample documents, and deployment defaults.

## Principles

- Keep all behavior generic and reusable. Use `DEMO_*` naming, not customer- or
  vertical-specific naming.
- Make `DEMO_MODE=false` preserve current local/development behavior unless a
  limit is already enforced by existing code.
- Enforce limits before paid provider calls whenever possible.
- Keep backend enforcement as the source of truth; frontend messaging should
  display backend errors cleanly.
- Track usage without storing document contents or raw IP addresses.
- Treat provider-side budgets and dedicated API keys as deployment operations,
  while making quota errors friendly in application code.

## Proposed Demo Configuration

```env
DEMO_MODE=true
DEMO_MAX_UPLOADS_PER_SESSION=3
DEMO_MAX_QUERIES_PER_SESSION=20
DEMO_MAX_TOTAL_UPLOAD_MB_PER_SESSION=25
DEMO_MAX_FILE_SIZE_MB=10
DEMO_MAX_QUERY_LENGTH=1000
DEMO_RATE_LIMIT_WINDOW_MINUTES=60
DEMO_MAX_QUERIES_PER_IP=30
DEMO_GLOBAL_DAILY_QUERY_LIMIT=250
DEMO_MAX_COMPLETION_TOKENS=1000
DEMO_MAX_RETRIEVED_CHUNKS=10
DEMO_REQUEST_TIMEOUT_SECONDS=45
```

## Work Packages

### 1. Add Demo Mode Configuration

**Status:** Complete.

Implemented in `backend/app/core/config.py`, `.env.example`,
`.env.vps.example`, `docs/deployment.md`, and `tests/unit/test_config.py`.

**Scope**

Add typed settings for demo mode and limits.

**Likely files**

- `backend/app/core/config.py`
- `.env.example`
- `.env.vps.example`
- `docs/deployment.md`

**Acceptance checks**

- `DEMO_MODE` defaults to `false`.
- All demo limits are configurable via environment variables.
- Invalid values are handled by existing settings validation or clear failures.
- Documentation explains which values are intended for public demos.

**Suggested issue title**

Add configurable DEMO_MODE settings for public demo safeguards

### 2. Add Usage Tracking and Limit Service

**Status:** Complete.

Implemented in `backend/app/services/demo_limits.py`,
`backend/app/core/exceptions.py`, `backend/app/core/config.py`,
`migrations/008_add_demo_usage_events.sql`, and
`tests/unit/test_demo_limits.py`.

**Scope**

Create a backend service responsible for demo counters, hashed IP logging,
friendly limit errors, duplicate query checks, and cleanup support.

**Likely files**

- `backend/app/services/demo_limits.py`
- `backend/app/core/exceptions.py`
- `backend/app/services/database.py`
- `migrations/`
- `tests/unit/`

**Design notes**

- Prefer database-backed tracking over in-memory counters so limits survive
  restarts and work across multiple app instances.
- Store session ID, hashed IP, route, limit type, timestamp, and minimal request
  metadata such as byte counts.
- Do not store document contents, query text, or raw IP addresses.
- Add a short duplicate-query cooldown using a hash of the normalized query.

**Acceptance checks**

- Session, IP, and global query counters can be incremented and checked.
- Upload count and uploaded byte totals can be checked by session.
- Over-limit checks return consistent status codes and friendly messages.
- Limit events are logged without sensitive contents.
- Unit tests cover allowed, at-limit, and over-limit cases.

**Suggested issue title**

Add database-backed demo usage tracking and limit service

### 3. Enforce Upload Protections

**Status:** Complete.

Implemented in `backend/app/api/documents.py`,
`backend/app/services/demo_limits.py`, `tests/unit/test_demo_limits.py`, and
`tests/unit/test_documents.py`.

**Scope**

Reject invalid uploads before text extraction, chunking, embeddings, or storage.

**Likely files**

- `backend/app/api/documents.py`
- `backend/app/services/demo_limits.py`
- `tests/unit/test_documents.py`
- `tests/integration/test_document_workflow.py`

**Rules**

- Maximum file size: `DEMO_MAX_FILE_SIZE_MB`
- Maximum uploads per session: `DEMO_MAX_UPLOADS_PER_SESSION`
- Maximum total uploaded size per session:
  `DEMO_MAX_TOTAL_UPLOAD_MB_PER_SESSION`
- Allowed MIME types only
- Reject empty or extremely small documents

**Acceptance checks**

- Over-limit uploads return `429` or `413` as appropriate.
- Rejected uploads do not call embedding, chunking, or storage services.
- Friendly messages are returned for file size, upload count, and empty content.
- Existing non-demo behavior remains compatible.

**Suggested issue title**

Enforce public demo upload limits before document processing

### 4. Enforce Query Protections

**Scope**

Reject abusive or expensive queries before retrieval, reranking, or LLM calls.

**Likely files**

- `backend/app/api/query.py`
- `backend/app/services/demo_limits.py`
- `tests/unit/test_query_api.py`
- `tests/integration/test_query_workflow.py`

**Rules**

- Maximum query length: `DEMO_MAX_QUERY_LENGTH`
- Reject empty or low-value queries
- Prevent rapid duplicate queries
- Session query limit per rate window
- IP query limit per rate window
- Global daily query limit
- Request timeout: `DEMO_REQUEST_TIMEOUT_SECONDS`

**Acceptance checks**

- Over-limit queries return `429`.
- Empty or low-value queries return `400`.
- Duplicate rapid queries return a friendly retry message.
- Rejected queries do not call embeddings, retrieval, reranking, or LLM services.
- Tests cover session, IP, global, and duplicate-query limits.

**Suggested issue title**

Enforce public demo query limits before paid provider calls

### 5. Add Retrieval and LLM Cost Controls

**Scope**

Cap downstream retrieval and generation work while demo mode is enabled.

**Likely files**

- `backend/app/api/query.py`
- `backend/app/services/reranking.py`
- `backend/app/services/llm.py`
- `backend/app/core/config.py`
- `tests/unit/test_query_api.py`
- `tests/unit/test_llm.py`

**Rules**

- Maximum retrieved chunks: `DEMO_MAX_RETRIEVED_CHUNKS`
- Maximum completion tokens: `DEMO_MAX_COMPLETION_TOKENS`
- Provider quota/rate-limit failures become friendly application messages.

**Acceptance checks**

- Demo mode caps the number of chunks sent to generation.
- Demo mode caps provider completion tokens.
- Provider quota errors do not leak raw provider error payloads to users.
- Tests cover cap propagation and friendly quota handling.

**Suggested issue title**

Cap retrieval and LLM generation costs in DEMO_MODE

### 6. Integrate Cleanup

**Scope**

Ensure demo documents and usage records expire while protected shared/global
documents remain available.

**Likely files**

- `backend/scripts/cleanup_demo.py`
- `backend/app/services/demo_limits.py`
- `backend/app/services/database.py`
- `migrations/`
- `tests/unit/`

**Acceptance checks**

- Demo documents continue to be deleted after 24 hours.
- Demo usage records are cleaned up after the configured retention period.
- Shared/global documents are excluded from cleanup.
- Cleanup behavior is documented for deployments.

**Suggested issue title**

Extend demo cleanup to remove usage records and preserve shared documents

### 7. Update Frontend Messaging and Footer Copy

**Scope**

Display backend-provided friendly errors and make public demo limits visible.

**Likely files**

- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/README.md`

**Footer copy**

Demo limits: 3 documents per session, 10 MB per file, 20 questions per hour.
Documents are automatically deleted after 24 hours.

**Acceptance checks**

- Upload and query limit responses render as readable user-facing messages.
- Raw provider errors are not displayed.
- Footer includes current demo usage information.
- Copy stays generic for downstream branded deployments.

**Suggested issue title**

Show friendly demo limit errors and visible usage copy in the frontend

## Provider Operations Checklist

Application code cannot enforce provider budgets directly. Public demo
deployments should complete these steps during deployment:

- Use dedicated provider API keys for public demos.
- Configure provider-side budgets, quotas, and alerting.
- Keep local/development keys separate from demo/production keys.
- Confirm quota and rate-limit provider errors are mapped to friendly app
  responses.
- Rotate demo keys independently from development keys.

## Context Reset Handoff

Before starting any work package, read:

1. This plan.
2. The suggested files for the chosen package.
3. Existing tests that cover the route or service being changed.

At the end of each package, leave a short note in the PR or issue with:

- Files changed.
- New environment variables or migrations.
- Tests run.
- Any follow-up work intentionally deferred to the next package.

## Recommended Order

1. Add demo mode configuration.
2. Add usage tracking and limit service.
3. Enforce upload protections.
4. Enforce query protections.
5. Add retrieval and LLM cost controls.
6. Integrate cleanup.
7. Update frontend messaging and footer copy.
