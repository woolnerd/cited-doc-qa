-- Migration 006: Optimize full-text search to use GIN index
-- Description: Fix search functions to use pre-computed fts column instead of computing tsvector at runtime
--
-- PROBLEM:
--   The GIN index is built on the `fts` column: to_tsvector('english', coalesce(contextual_content, content))
--   But search functions were computing: to_tsvector('english', c.content) at query time
--   This bypasses the index and causes slow queries with unnecessary runtime computation
--
-- SOLUTION:
--   Update all full-text search functions to use c.fts instead of to_tsvector('english', c.content)
--   This will:
--     - Use the GIN index for fast lookups
--     - Avoid runtime tsvector computation
--     - Search both contextual_content and content (as designed)
--
-- FUNCTIONS UPDATED:
--   1. search_chunks_fulltext
--   2. search_chunks_fulltext_by_document
--   3. search_chunks_fulltext_by_session
--   4. search_chunks_fulltext_by_document_and_session

-- =============================================================================
-- FULL-TEXT SEARCH FUNCTIONS (NON-SESSION)
-- =============================================================================

-- Function: Full-text search (OPTIMIZED)
CREATE OR REPLACE FUNCTION search_chunks_fulltext(
    search_query text,
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
        ts_rank(c.fts, websearch_to_tsquery('english', search_query)) as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.fts @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;

-- Function: Full-text search scoped to a specific document (OPTIMIZED)
CREATE OR REPLACE FUNCTION search_chunks_fulltext_by_document(
    search_query text,
    target_document_id uuid,
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
        ts_rank(c.fts, websearch_to_tsquery('english', search_query)) as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.document_id = target_document_id
        AND c.fts @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;

-- =============================================================================
-- FULL-TEXT SEARCH FUNCTIONS (SESSION-AWARE) (OPTIMIZED)
-- =============================================================================

-- Function: Full-text search with session filtering (OPTIMIZED)
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
        ts_rank(c.fts, websearch_to_tsquery('english', search_query)) as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE (d.session_id = user_session_id OR d.session_id = 'global')
        AND c.fts @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;

-- Function: Full-text search scoped to specific document with session verification (OPTIMIZED)
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
        ts_rank(c.fts, websearch_to_tsquery('english', search_query)) as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.document_id = target_document_id
        AND (d.session_id = user_session_id OR d.session_id = 'global')
        AND c.fts @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================

DO $$
BEGIN
  RAISE NOTICE '========================================';
  RAISE NOTICE 'Migration 006: Full-text search optimization';
  RAISE NOTICE '========================================';
  RAISE NOTICE '';
  RAISE NOTICE 'Updated functions to use GIN index:';
  RAISE NOTICE '  - search_chunks_fulltext';
  RAISE NOTICE '  - search_chunks_fulltext_by_document';
  RAISE NOTICE '  - search_chunks_fulltext_by_session';
  RAISE NOTICE '  - search_chunks_fulltext_by_document_and_session';
  RAISE NOTICE '';
  RAISE NOTICE 'Performance improvements:';
  RAISE NOTICE '  ✓ Using pre-computed fts column (GIN indexed)';
  RAISE NOTICE '  ✓ No runtime tsvector computation';
  RAISE NOTICE '  ✓ Searches contextual_content + content (as designed)';
  RAISE NOTICE '';
  RAISE NOTICE 'Expected impact:';
  RAISE NOTICE '  - Faster full-text search queries';
  RAISE NOTICE '  - Better index utilization';
  RAISE NOTICE '  - More comprehensive search (includes contextual_content)';
  RAISE NOTICE '';
  RAISE NOTICE 'Migration completed successfully!';
END $$;
