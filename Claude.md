# RAG Chatbot - AI Assistant Context

> This file provides context for AI assistants (Claude, Cursor, Cline, etc.) working on this project.

## Project Overview

Production-ready RAG (Retrieval-Augmented Generation) chatbot system that allows users to upload documents and ask questions about them using advanced search and AI generation.

**Live Demo:** <https://github.com/woolnerd/production-rag-system>

## Tech Stack

### Backend
- **Framework:** FastAPI (Python 3.13+)
- **Database:** PostgreSQL 15 (self-hosted on VPS) + pgvector extension
- **Vector Search:** pgvector with IVFFlat indexing
- **Full-Text Search:** PostgreSQL ts_vector with GIN indexing
- **Embeddings:** Google Gemini (text-embedding-004, 768 dimensions)
- **Reranking:** Cohere (rerank-english-v3.0) with 0.1 score threshold
- **LLM Generation:** Claude 3.5 Sonnet via OpenRouter
- **Session Isolation:** Multi-user demo support with session_id filtering
- **Testing:** pytest with >60% coverage (target: 80%)

### Frontend
- **Pure vanilla JavaScript** (no build step, no frameworks)
- **HTML + CSS** with modern responsive design
- **Server:** Simple Python HTTP server (`frontend/serve.py`)
- **Ports:** Frontend (3000), Backend (8000)

### Infrastructure
- **CI/CD:** GitHub Actions
- **Code Quality:** pre-commit hooks (black, ruff, mypy, bandit)
- **Version Control:** Git with conventional commits

## Important: GitHub Issue Numbering

⚠️ **Issue numbering discrepancy exists** - This was not intentional:

- Early issues (created mid-project) have "Issue #1-8" in titles but different actual GitHub numbers
- Later issues (#6, #7, #9-17) use their actual GitHub issue numbers
- Always check the actual GitHub issue URL, not just the title number

Example:

- Title: "Issue #1: Project Setup" → Actual: #29
- Title: "Issue #6: Document Upload" → Actual: #22
- Title: "Document Management Interface" → Actual: #6 ✓

When referencing issues, verify the actual number with `gh issue list`.

## Project Structure

```
rag-demo/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/               # API endpoints
│   │   ├── services/          # Business logic (embeddings, search, LLM)
│   │   ├── models/            # Pydantic models
│   │   ├── core/              # Config, dependencies, logging
│   │   └── main.py            # FastAPI app entry point
│   ├── tests/                 # Pytest tests
│   └── .env                   # Environment variables (not in git)
├── frontend/                   # Vanilla JS frontend
│   ├── index.html             # Main HTML
│   ├── styles.css             # All styling
│   ├── app.js                 # Application logic
│   └── serve.py               # Development server
├── migrations/                 # SQL database migrations
│   ├── 001_initial_schema.sql
│   ├── 002_add_search_functions.sql
│   ├── 003_fix_search_function_types.sql  # CRITICAL!
│   ├── 004_add_session_isolation.sql
│   ├── 005_add_session_search_functions.sql
│   └── 006_optimize_fulltext_search.sql  # PERFORMANCE!
├── deployment/                 # VPS deployment documentation
│   └── vps/                   # VPS-specific guides and scripts
├── database/                   # Database documentation
└── venv/                      # Python virtual environment
```

## Development Workflow

### 1. Making Changes

**Always use this pattern:**

1. Work on a GitHub issue (never commit to main directly)
2. Create a feature branch: `git checkout -b issue-N-description`
3. Make changes and commit with descriptive messages
4. Use TodoWrite tool for multi-step tasks
5. Run tests: `cd backend && pytest`
6. Create PR linked to issue
7. Merge via GitHub (squash preferred)

### 2. Commit Format

```
Add feature description

Detailed explanation of changes made.

Tested:
- Test case 1
- Test case 2

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### 3. Pre-commit Hooks

Automatically run on commit:
- `black` - Code formatting
- `ruff` - Linting
- `mypy` - Type checking
- `bandit` - Security scanning

If hooks fail, fix issues before committing.

### 4. PR Creation

```bash
gh pr create --title "Add feature (Issue #N)" --body "..."
```

Always include:
- Summary of changes
- Testing performed
- Link to issue (auto-closes with "Fixes #N")

## Database & Migrations

### Running Migrations

⚠️ **For VPS PostgreSQL:**

```bash
# Connect to PostgreSQL
docker exec -it n8n-test_postgres_1 psql -U rag_user -d rag_db

# Paste SQL from migrations/ files
# Or run directly:
docker exec -i n8n-test_postgres_1 psql -U rag_user -d rag_db -c "SQL COMMANDS HERE"

# Verify
\d documents  # Check schema
\df *session* # Check functions
\q
```

See `deployment/vps/VPS_TESTING.md` for detailed migration instructions.

### Migration 003 is Critical

**Must be applied** for search to work:

```sql
-- migrations/003_fix_search_function_types.sql
-- Fixes "type real does not match double precision" error
```

Without this migration:

- Vector search may work
- Full-text search will fail with type errors
- Queries return 500 errors

### Migration 006 - Full-Text Search Optimization

**Performance improvement** - should be applied for faster searches:

```sql
-- migrations/006_optimize_fulltext_search.sql
-- Fixes full-text search to use GIN index instead of runtime tsvector computation
```

**What it fixes:**

The initial schema created a GIN index on a pre-computed `fts` column:
```sql
ALTER TABLE chunks ADD COLUMN fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(contextual_content, content))) STORED;
CREATE INDEX idx_chunks_fts ON chunks USING GIN(fts);
```

But the search functions were computing `to_tsvector('english', c.content)` at query time, bypassing the index!

**Benefits after migration:**
- ✅ Uses pre-computed GIN index (much faster)
- ✅ No runtime tsvector computation
- ✅ Searches both `contextual_content` and `content` (as originally designed)
- ✅ Significantly improves full-text search performance

**Affected functions:**
- `search_chunks_fulltext`
- `search_chunks_fulltext_by_document`
- `search_chunks_fulltext_by_session`
- `search_chunks_fulltext_by_document_and_session`

### Common Database Issues

**Issue:** "Could not find the function search_chunks"

- **Cause:** Migration 002 not applied
- **Fix:** Run migration 002 in Supabase SQL Editor

**Issue:** "type real does not match expected type double precision"

- **Cause:** Migration 003 not applied
- **Fix:** Run migration 003 in Supabase SQL Editor

**Issue:** Search returns 0 results but no errors

- **Cause:** Supabase schema cache not refreshed
- **Fix:** Wait a few minutes or restart backend
- **Note:** This can happen mysteriously and resolve itself

## Search & Retrieval

### How It Works

1. **Hybrid Search** (runs in parallel):
   - Vector search using cosine similarity
   - Full-text search using PostgreSQL ts_vector

2. **Reciprocal Rank Fusion (RRF):**
   - Combines vector + full-text results
   - Weighted scoring algorithm

3. **Reranking:**
   - Uses Cohere rerank-english-v3.0
   - Improves result relevance

4. **Context Assembly:**
   - Top 5 chunks (configurable)
   - Includes document names and chunk indices

5. **LLM Generation:**
   - Claude 3.5 Sonnet generates answer
   - Cites sources with [1], [2], etc.

### Query Requirements

⚠️ **Queries must match document content**

If documents are about electricity bills, queries like "What is Python?" will correctly return 0 results. Always ask relevant questions:

✅ Good: "What was my electricity usage?"
✅ Good: "How much do I owe?"
❌ Bad: "What is Python?" (if docs are about bills)

## Common Tasks

### Running the Application

```bash
# Terminal 1 - Backend
cd backend
source ../venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - Frontend
cd frontend
python3 serve.py

# Access at http://localhost:3000
```

### Running Tests

```bash
cd backend
source ../venv/bin/activate
pytest                    # Run all tests
pytest -v                 # Verbose
pytest --cov              # With coverage
pytest tests/test_foo.py  # Specific file
```

### Environment Variables

Required in `backend/.env`:
```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJxxx...
GEMINI_API_KEY=AIzaSyxxx...
COHERE_API_KEY=xxx...
OPENROUTER_API_KEY=sk-or-xxx...
```

### Checking GitHub Issues

```bash
gh issue list                    # Open issues
gh issue list --state all       # All issues
gh issue view 6                 # View specific issue
gh pr list                      # Open PRs
```

## Code Patterns & Conventions

### Backend

**FastAPI Endpoints:**
```python
@router.post("/endpoint", response_model=ResponseModel)
async def endpoint_name(
    request: RequestModel,
    supabase: SupabaseClient = None,  # Injected dependency
) -> ResponseModel:
    """Clear docstring."""
    try:
        # Implementation
        return ResponseModel(success=True, data=result)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error message")
```

**Services:**
```python
class ServiceName:
    """Service docstring."""

    def __init__(self, client: Client):
        self.client = client

    def method(self, param: str) -> Result:
        """Method docstring."""
        # Implementation
```

**Testing:**
```python
def test_feature():
    """Test that feature works correctly."""
    # Arrange
    input_data = create_test_data()

    # Act
    result = function(input_data)

    # Assert
    assert result.success is True
    assert result.data == expected
```

### Frontend

**Pure vanilla JS patterns:**
```javascript
// State management
const state = {
    documents: [],
    messages: [],
};

// API calls
async function fetchData() {
    try {
        const response = await fetch(`${API_BASE_URL}/endpoint`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data),
        });

        if (!response.ok) {
            throw new Error('Request failed');
        }

        return await response.json();
    } catch (error) {
        console.error('Error:', error);
        showError(error.message);
    }
}

// DOM updates
function updateUI(data) {
    elements.container.innerHTML = data.map(item => `
        <div class="item">
            ${escapeHtml(item.name)}
        </div>
    `).join('');
}
```

## Known Gotchas

### 1. TypeScript Warnings in app.js

The IDE shows TypeScript diagnostics for `app.js` even though it's vanilla JS. Common warnings:
- Unused variables (often needed for clarity)
- Parameter types (no TypeScript in vanilla JS)

**Fix unused variables:** Remove them if truly unused.

### 2. Supabase Schema Cache

Supabase caches schema/function definitions. After running migrations:
- Changes may not be immediately visible
- Backend may need restart
- Wait 1-2 minutes for cache refresh

### 3. File Upload Size Limits

- Max file size: 10MB (configurable in `documents.py`)
- Allowed types: PDF, DOCX, TXT
- Frontend validates before upload
- Backend validates again for security

### 4. Embedding Dimensions

⚠️ **Must match across system:**

- Gemini embeddings: 768 dimensions
- Database vector column: vector(768)
- Search functions: Use 768-dim vectors

Changing embedding model requires:

1. Update `EMBEDDING_DIMENSIONS` in config
2. Migrate database column type
3. Regenerate all embeddings

### 5. Import Naming Collisions

**Watch for shadowing in Python:**
```python
# Bad - shadows fastapi.status module
status = "ready"
raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Good - use different variable name
doc_status = "ready"
raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

## Debugging

### Backend Logs

```bash
# Follow uvicorn logs
tail -f logs/app.log  # If logging to file

# Or watch console output
# Logs show:
# - Request details
# - Search timing
# - API call results
# - Errors with tracebacks
```

### Common Error Messages

**"No results found for query"**

- Not an error - query doesn't match document content
- Check what documents contain
- Try more specific queries

**"Vector search failed"**

- Migration 002 missing
- Supabase function not found
- Run migration 002

**"Full-text search failed: type mismatch"**

- Migration 003 missing
- Type error in search function
- Run migration 003

**"Could not find 'token_count' column"**

- Schema mismatch
- Run migration 001
- Verify all columns exist

### Database Inspection

```python
# Quick script to check database
from app.core.config import settings
from supabase import create_client

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# Check chunks
result = supabase.table('chunks').select('id, content').limit(5).execute()
print(f"Chunks: {len(result.data)}")

# Check documents
result = supabase.table('documents').select('id, filename').execute()
print(f"Documents: {len(result.data)}")
```

## Testing Strategy

### Test Coverage

Current: >85%

- Unit tests for all services
- Integration tests for API endpoints
- Mock external APIs (Gemini, Cohere, OpenRouter)

### Test Organization

```
tests/
├── test_api/              # API endpoint tests
├── test_services/         # Service layer tests
├── conftest.py           # Shared fixtures
└── __init__.py
```

### Running Specific Tests

```bash
pytest tests/test_api/test_documents.py::test_upload_document
pytest -k "document"       # All tests matching "document"
pytest -m "slow"          # Tests marked as slow
```

## Performance Considerations

### Search Timing (typical)

- Vector search: ~600ms
- Full-text search: ~100ms
- RRF merge: ~10ms
- Reranking: ~500ms
- LLM generation: ~3-5s
- **Total:** ~4-6s for end-to-end query

### Optimization Opportunities

1. **Caching:**
   - Embed common queries
   - Cache search results
   - Cache LLM responses

2. **Batch Processing:**
   - Process multiple chunks in parallel
   - Batch embedding generation

3. **Database:**
   - Optimize IVFFlat index `lists` parameter
   - Adjust search thresholds
   - Add more indexes for common queries

## Security Notes

⚠️ **Development setup - not production-ready:**

- No authentication/authorization
- No rate limiting
- No input sanitization beyond basic validation
- CORS wide open for development
- API keys in `.env` file (not secure for production)

**Before production:**

1. Add user authentication (OAuth, JWT)
2. Implement rate limiting
3. Add input validation/sanitization
4. Restrict CORS origins
5. Use proper secret management
6. Add virus scanning for uploads
7. Implement access control for documents

## Deployment

Not yet configured. Planned:

- Docker containers (Issue #14)
- GitHub Actions CI/CD (Issue #15)
- VPS deployment (Issue #16)

## Maintenance & Cleanup

### Automated Cleanup Script

**Purpose**: Prevents database bloat by deleting old demo documents (Issue #70)

**Location**: `backend/scripts/cleanup_demo.py`

**Usage (Docker - RECOMMENDED FOR VPS)**:

```bash
# Run cleanup in Docker container (deletes docs older than 24h)
docker exec rag-chatbot-prod python /app/scripts/cleanup_demo.py

# Dry run (see what would be deleted)
docker exec rag-chatbot-prod python /app/scripts/cleanup_demo.py --dry-run

# Custom time threshold
docker exec rag-chatbot-prod python /app/scripts/cleanup_demo.py --hours 48
```

**Usage (Non-Docker/venv)**:

```bash
cd /root/rag-demo
/root/rag-demo/venv/bin/python backend/scripts/cleanup_demo.py --dry-run
```

**Automated Scheduling (Docker with Cron)**:

```bash
# Cron job - runs daily at 2 AM
crontab -e
0 2 * * * docker exec rag-chatbot-prod python /app/scripts/cleanup_demo.py >> /var/log/rag-cleanup.log 2>&1

# Or every 6 hours
0 */6 * * * docker exec rag-chatbot-prod python /app/scripts/cleanup_demo.py >> /var/log/rag-cleanup.log 2>&1
```

**Features**:
- Deletes documents older than 24 hours by default
- Protects global documents (excludes `session_id='global'`)
- Cascades deletion to chunks and embeddings
- Comprehensive logging and statistics
- Dry-run mode for testing

**See**: `backend/scripts/README.md` for full documentation

## Useful Commands

```bash
# Git workflow
git checkout -b issue-N-feature
git add .
git commit -m "Add feature"
git push -u origin issue-N-feature
gh pr create --title "Title" --body "Body"

# Python environment
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt

# Code quality
black backend/              # Format code
ruff check backend/        # Lint
mypy backend/              # Type check
bandit -r backend/         # Security scan

# Database
cat migrations/003_fix_search_function_types.sql
# Copy and run in Supabase SQL Editor

# Testing
pytest                     # All tests
pytest --cov              # With coverage
pytest -v                 # Verbose
```

## Resources

- **Repository:** <https://github.com/woolnerd/production-rag-system>
- **Supabase Docs:** <https://supabase.com/docs>
- **FastAPI Docs:** <https://fastapi.tiangolo.com>
- **pgvector Docs:** <https://github.com/pgvector/pgvector>

## Contributing

This project follows trunk-based development:

1. All changes via GitHub issues
2. Feature branches from main
3. PRs reviewed and squashed to main
4. Never commit directly to main

## Notes for AI Assistants

### Best Practices

1. **Always use TodoWrite tool** for multi-step tasks
2. **Mark todos complete** immediately after finishing
3. **Run tests** before creating PRs
4. **Check pre-commit hooks** pass before committing
5. **Link PRs to issues** with "Fixes #N"
6. **Use descriptive commit messages** (not "fix bug")

### When Things Break

1. Check backend logs first
2. Verify database migrations applied
3. Test search functions directly
4. Check environment variables set
5. Verify API keys valid
6. Try restarting backend server

### Common User Questions

**"Search isn't working"**

- Check migrations applied (especially 003)
- Verify documents uploaded and processed
- Check if query matches document content

**"Upload fails"**

- Check file size < 10MB
- Verify file type (PDF, DOCX, TXT)
- Check Supabase connection

**"No results found"**

- Usually correct - query doesn't match docs
- Ask user what documents they uploaded
- Suggest relevant queries

---

## Current Status - Session Isolation (2025-11-10)

### What We Just Completed

**Branch:** `session-isolation`
**Issue:** #69 - Session isolation for multi-user demo
**Status:** ✅ Fully implemented and tested on VPS

### Feature Summary

Multi-user session isolation allowing concurrent demo users without data mixing:

1. ✅ **Database Schema (Migration 004)**
   - Added `session_id` column to documents table
   - Created index on session_id for fast filtering
   - Default existing documents to 'global' session

2. ✅ **Session-Aware Search Functions (Migration 005)**
   - `search_chunks_by_session()` - Vector search with session filtering
   - `search_chunks_by_document_and_session()` - Document-specific vector search
   - `search_chunks_fulltext_by_session()` - Full-text search with session filtering
   - `search_chunks_fulltext_by_document_and_session()` - Document-specific full-text
   - All functions filter by: `session_id = user OR session_id = 'global'`

3. ✅ **Backend Services Updated**
   - `vector_search.py` - Added session_id parameter to all methods
   - `full_text_search.py` - Added session_id parameter to all methods
   - `hybrid_search.py` - Passes session_id to both search services
   - `query.py` - Extracts session_id from request and passes to search

4. ✅ **Frontend Session Management**
   - Auto-generates unique session_id on page load
   - Persists session_id in localStorage across page refreshes
   - Sends session_id with all document uploads
   - Sends session_id with all queries

5. ✅ **Security & Isolation**
   - Users can only see their own documents + global documents
   - Users can only search within their session + global documents
   - Users cannot delete global documents (403 Forbidden)
   - Users cannot delete other users' documents

6. ✅ **Search Quality Improvements**
   - Added `RERANK_SCORE_THRESHOLD = 0.1` to filter irrelevant results
   - Prevents low-scoring documents from appearing in answers
   - Fixed regression where unrelated docs appeared with score < 0.01

### VPS Testing Results (2025-11-10)

**Status:** ✅ **SUCCESSFUL** - Session isolation working perfectly on VPS!

**Testing Performed:**
1. ✅ Uploaded documents in Browser 1 (normal window)
2. ✅ Opened Browser 2 (incognito) - documents from Browser 1 NOT visible
3. ✅ Uploaded documents in Browser 2 - isolated from Browser 1
4. ✅ Made document global via SQL - visible in both sessions
5. ✅ Queries filtered by session - only returns session + global docs
6. ✅ Delete protection - cannot delete global documents (403 error)
7. ✅ Search quality - rerank threshold filtering irrelevant results

**Database Container:**
- Container: `n8n-test_postgres_1`
- Database: `rag_db`
- User: `rag_user`

### Managing Global Documents

To make uploaded documents visible to all users:

```bash
# SSH into VPS
ssh root@YOUR_VPS_IP

# Connect to PostgreSQL
docker exec -it n8n-test_postgres_1 psql -U rag_user -d rag_db

# List recent documents
SELECT id, filename, session_id FROM documents ORDER BY upload_date DESC;

# Make document global by filename
UPDATE documents SET session_id = 'global' WHERE filename = 'Employee_Handbook.txt';

# Verify
SELECT filename, session_id FROM documents WHERE session_id = 'global';

\q
```

See `deployment/vps/GLOBAL_DOCUMENTS.md` for complete guide.

### Next Steps

1. **Create PR** for session-isolation branch
2. **Update documentation** with session isolation notes
3. **Close Issue #69**
4. **TODO - Restore Test Coverage:**
   - Add tests for session isolation features
   - Target: Bring coverage back to 80%+
   - Add tests for session-aware search functions

### Important Files Changed

**Migrations:**
- `migrations/004_add_session_isolation.sql` - NEW (session_id column)
- `migrations/005_add_session_search_functions.sql` - NEW (session-aware search)

**Backend:**
- `backend/app/models/base.py` - UPDATED (session_id in QueryRequest & DocumentListItem)
- `backend/app/api/documents.py` - UPDATED (session isolation for upload/list/delete)
- `backend/app/api/query.py` - UPDATED (pass session_id to search)
- `backend/app/services/vector_search.py` - UPDATED (session_id parameter)
- `backend/app/services/full_text_search.py` - UPDATED (session_id parameter)
- `backend/app/services/hybrid_search.py` - UPDATED (pass session_id to searches)
- `backend/app/services/reranking.py` - UPDATED (filter by rerank threshold)
- `backend/app/core/config.py` - UPDATED (RERANK_SCORE_THRESHOLD = 0.1)

**Frontend:**
- `frontend/app.js` - UPDATED (session generation, localStorage persistence)

**Tests:**
- `backend/tests/test_conversation_history.py` - UPDATED (add session_id to tests)

**Documentation:**
- `deployment/vps/VPS_TESTING.md` - NEW (testing guide)
- `deployment/vps/GLOBAL_DOCUMENTS.md` - NEW (global docs guide)

---

**Last Updated:** 2025-11-10
**Project Status:** Session Isolation - COMPLETE ✅ | Ready for PR
