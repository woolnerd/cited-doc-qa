# VPS Testing Guide - Session Isolation

## Prerequisites
- VPS with PostgreSQL running in Docker
- Backend code on VPS
- VPS IP address

## Step 1: SSH into VPS

```bash
ssh root@YOUR_VPS_IP
cd /root/rag-demo  # or wherever your code is
```

## Step 2: Pull Latest Code

```bash
git fetch origin
git checkout session-isolation
git pull origin session-isolation
```

## Step 3: Apply Database Migrations

### Check Current State

```bash
docker exec -it n8n-test_postgres_1 psql -U rag_user -d rag_db -c "\d documents"
```

Look for `session_id` column. If it doesn't exist, continue:

### Apply Migration 004 (Add session_id column)

```bash
docker exec -i n8n-test_postgres_1 psql -U rag_user -d rag_db << 'EOF'
-- Migration 004: Add session isolation support
ALTER TABLE documents
ADD COLUMN session_id VARCHAR(255) NOT NULL DEFAULT 'global';

CREATE INDEX idx_documents_session_id ON documents(session_id);

UPDATE documents SET session_id = 'global' WHERE session_id IS NULL;

COMMENT ON COLUMN documents.session_id IS 'Session identifier for multi-user isolation. Use "global" for documents visible to all users.';

SELECT 'Migration 004 applied successfully!' as status;

-- Verify
SELECT session_id, COUNT(*) as doc_count FROM documents GROUP BY session_id;
EOF
```

### Apply Migration 005 (Session-aware search functions)

```bash
docker exec -i n8n-test_postgres_1 psql -U rag_user -d rag_db << 'EOF'
-- Migration 005: Add session-aware search functions

-- Vector search with session filtering
CREATE OR REPLACE FUNCTION search_chunks_by_session(
    query_embedding vector(768),
    user_session_id varchar(255),
    match_count int DEFAULT 10,
    similarity_threshold float DEFAULT 0.5
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    content text,
    contextual_content text,
    similarity float,
    metadata jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.contextual_content,
        1 - (c.embedding <=> query_embedding) as similarity,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE (d.session_id = user_session_id OR d.session_id = 'global')
        AND 1 - (c.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Vector search by document with session verification
CREATE OR REPLACE FUNCTION search_chunks_by_document_and_session(
    query_embedding vector(768),
    target_document_id uuid,
    user_session_id varchar(255),
    match_count int DEFAULT 10,
    similarity_threshold float DEFAULT 0.5
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    content text,
    contextual_content text,
    similarity float,
    metadata jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.contextual_content,
        1 - (c.embedding <=> query_embedding) as similarity,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.document_id = target_document_id
        AND (d.session_id = user_session_id OR d.session_id = 'global')
        AND 1 - (c.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Full-text search with session filtering
CREATE OR REPLACE FUNCTION search_chunks_fulltext_by_session(
    search_query text,
    user_session_id varchar(255),
    match_limit int DEFAULT 30
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    content text,
    contextual_content text,
    rank float,
    metadata jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.contextual_content,
        ts_rank(to_tsvector('english', c.content), websearch_to_tsquery('english', search_query)) as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE (d.session_id = user_session_id OR d.session_id = 'global')
        AND to_tsvector('english', c.content) @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;

-- Full-text search by document with session verification
CREATE OR REPLACE FUNCTION search_chunks_fulltext_by_document_and_session(
    search_query text,
    target_document_id uuid,
    user_session_id varchar(255),
    match_limit int DEFAULT 30
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    content text,
    contextual_content text,
    rank float,
    metadata jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.contextual_content,
        ts_rank(to_tsvector('english', c.content), websearch_to_tsquery('english', search_query)) as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.document_id = target_document_id
        AND (d.session_id = user_session_id OR d.session_id = 'global')
        AND to_tsvector('english', c.content) @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;

SELECT 'Migration 005 applied successfully!' as status;

-- List all functions
SELECT proname FROM pg_proc WHERE proname LIKE '%session%';
EOF
```

## Step 4: Restart Backend

```bash
cd /root/rag-demo
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --build
```

Check logs:
```bash
docker-compose -f docker-compose.prod.yml logs -f backend
```

(Ctrl+C to exit logs)

## Step 5: Test Session Isolation

### Test 1: Upload Document in Session 1

**Browser 1 (Normal window):**
1. Open: `http://YOUR_VPS_IP:3000`
2. Upload a document (e.g., `test-doc-session1.pdf`)
3. Note the session ID in browser console: `Ctrl+Shift+J` → Check `SESSION_ID` variable
4. Wait for processing to complete

### Test 2: Verify Isolation in Session 2

**Browser 2 (Incognito/Private window):**
1. Open: `http://YOUR_VPS_IP:3000`
2. Check document list
3. **Expected:** Document from Session 1 should NOT appear
4. Note the different session ID in console

### Test 3: Upload Document in Session 2

**Browser 2 (still in incognito):**
1. Upload a different document (e.g., `test-doc-session2.pdf`)
2. **Expected:** Only Session 2's document appears

### Test 4: Verify Both Sessions Are Isolated

**Browser 1:**
- Refresh page
- **Expected:** Only Session 1's document appears

**Browser 2:**
- Refresh page
- **Expected:** Only Session 2's document appears

### Test 5: Make Document Global

**SSH into VPS:**

```bash
docker exec -it n8n-test_postgres_1 psql -U rag_user -d rag_db

-- List all documents
SELECT id, filename, session_id FROM documents ORDER BY upload_date DESC;

-- Make Session 1's document global
UPDATE documents SET session_id = 'global' WHERE filename = 'test-doc-session1.pdf';

-- Verify
SELECT filename, session_id FROM documents;

\q
```

### Test 6: Verify Global Document Visible in Both Sessions

**Browser 1:**
- Refresh
- **Expected:** Session 1's document (now global) + Session 1's other docs

**Browser 2:**
- Refresh
- **Expected:** Session 1's document (now global) + Session 2's docs

### Test 7: Test Query Isolation

**Browser 1:**
1. Ask a query about Session 1's document
2. **Expected:** Gets answer with sources from Session 1's docs

**Browser 2:**
1. Ask the SAME query
2. **Expected:** If doc is session-specific, gets "no results"
3. If doc is global, gets answer

### Test 8: Test Delete Protection

**Browser 2:**
1. Try to delete the global document
2. **Expected:** Should get 403 Forbidden error

**Browser 1 (if it uploaded the global doc):**
1. Try to delete the global document
2. **Expected:** Should get 403 Forbidden error (global docs can't be deleted)

## Verification Queries

**Check session distribution:**
```sql
SELECT session_id, COUNT(*) as doc_count,
       array_agg(filename) as files
FROM documents
GROUP BY session_id;
```

**Check chunks per session:**
```sql
SELECT d.session_id, COUNT(c.id) as chunk_count
FROM documents d
LEFT JOIN chunks c ON d.id = c.document_id
GROUP BY d.session_id;
```

## Cleanup After Testing

**Remove test documents:**

```bash
docker exec -it n8n-test_postgres_1 psql -U rag_user -d rag_db << 'EOF'
DELETE FROM documents WHERE filename LIKE 'test-doc-%';
EOF
```

## Expected Results Summary

✅ Documents are isolated by session_id
✅ Users can only see their own + global documents
✅ Queries only search within user's session + global
✅ Global documents visible to all sessions
✅ Global documents cannot be deleted
✅ Session documents can only be deleted by owning session

## Troubleshooting

**If backend won't start:**
```bash
docker-compose -f docker-compose.prod.yml logs backend
```

**If migrations fail:**

```bash
# Check if column already exists
docker exec -it n8n-test_postgres_1 psql -U rag_user -d rag_db -c "\d documents"

# Check if functions exist
docker exec -it n8n-test_postgres_1 psql -U rag_user -d rag_db -c "\df *session*"
```

**If search returns no results:**
- Check backend logs for errors
- Verify migrations applied: `\df search_chunks_by_session`
- Check document has chunks: `SELECT COUNT(*) FROM chunks;`
