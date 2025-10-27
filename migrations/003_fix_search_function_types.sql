-- Migration 003: Fix type mismatch in search functions
-- Fixes the rank column type from real to double precision

-- Function: Full-text search (fixed)
CREATE OR REPLACE FUNCTION search_chunks_fulltext(
    search_query text,
    match_limit int DEFAULT 30
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    content text,
    contextual_content text,
    rank double precision,
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
        ts_rank(to_tsvector('english', c.content), websearch_to_tsquery('english', search_query))::double precision as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE to_tsvector('english', c.content) @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;

-- Function: Full-text search scoped to a specific document (fixed)
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
    rank double precision,
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
        ts_rank(to_tsvector('english', c.content), websearch_to_tsquery('english', search_query))::double precision as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.document_id = target_document_id
        AND to_tsvector('english', c.content) @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;

DO $$
BEGIN
  RAISE NOTICE 'Migration 003_fix_search_function_types.sql completed successfully!';
  RAISE NOTICE 'Fixed type casting in full-text search functions';
END $$;
