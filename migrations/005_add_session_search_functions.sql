-- Migration 005: Add session-aware search functions
-- Description: Update search functions to filter by session_id for multi-user isolation

-- =============================================================================
-- VECTOR SEARCH FUNCTIONS (SESSION-AWARE)
-- =============================================================================

-- Function: Vector similarity search with session filtering
-- Searches chunks from documents that belong to the specified session OR global documents
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

-- Function: Vector similarity search scoped to specific document with session verification
-- Ensures the document belongs to the user's session before searching
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

-- =============================================================================
-- FULL-TEXT SEARCH FUNCTIONS (SESSION-AWARE)
-- =============================================================================

-- Function: Full-text search with session filtering
-- Searches chunks from documents that belong to the specified session OR global documents
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

-- Function: Full-text search scoped to specific document with session verification
-- Ensures the document belongs to the user's session before searching
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

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================

DO $$
BEGIN
  RAISE NOTICE 'Migration 005_add_session_search_functions.sql completed successfully!';
  RAISE NOTICE 'New session-aware functions created:';
  RAISE NOTICE '  - search_chunks_by_session (vector search with session filtering)';
  RAISE NOTICE '  - search_chunks_by_document_and_session (vector search by document + session)';
  RAISE NOTICE '  - search_chunks_fulltext_by_session (full-text search with session filtering)';
  RAISE NOTICE '  - search_chunks_fulltext_by_document_and_session (full-text search by document + session)';
  RAISE NOTICE '';
  RAISE NOTICE 'Session isolation:';
  RAISE NOTICE '  - Users can search their own documents (matching session_id)';
  RAISE NOTICE '  - Users can search global documents (session_id = ''global'')';
  RAISE NOTICE '  - Users cannot see other users'' documents';
  RAISE NOTICE '';
  RAISE NOTICE 'Note: Similarity threshold set to 0.5 for better recall';
END $$;
