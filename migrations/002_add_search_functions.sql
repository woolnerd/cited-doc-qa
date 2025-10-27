-- Migration 002: Add search functions for RAG system
-- This adds the specific search functions needed by the application

-- =============================================================================
-- VECTOR SEARCH FUNCTIONS
-- =============================================================================

-- Function: Vector similarity search
CREATE OR REPLACE FUNCTION search_chunks(
    query_embedding vector(768),
    match_count int DEFAULT 10,
    similarity_threshold float DEFAULT 0.7
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
    WHERE 1 - (c.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function: Vector similarity search scoped to a specific document
CREATE OR REPLACE FUNCTION search_chunks_by_document(
    query_embedding vector(768),
    target_document_id uuid,
    match_count int DEFAULT 10,
    similarity_threshold float DEFAULT 0.7
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
        AND 1 - (c.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- =============================================================================
-- FULL-TEXT SEARCH FUNCTIONS
-- =============================================================================

-- Function: Full-text search
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
        ts_rank(to_tsvector('english', c.content), websearch_to_tsquery('english', search_query)) as rank,
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

-- Function: Full-text search scoped to a specific document
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
        ts_rank(to_tsvector('english', c.content), websearch_to_tsquery('english', search_query)) as rank,
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

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================

DO $$
BEGIN
  RAISE NOTICE 'Migration 002_add_search_functions.sql completed successfully!';
  RAISE NOTICE 'Functions created:';
  RAISE NOTICE '  - search_chunks (vector search)';
  RAISE NOTICE '  - search_chunks_by_document (vector search by document)';
  RAISE NOTICE '  - search_chunks_fulltext (full-text search)';
  RAISE NOTICE '  - search_chunks_fulltext_by_document (full-text search by document)';
END $$;
