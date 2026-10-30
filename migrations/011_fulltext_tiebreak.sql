-- Migration 011: Deterministic order for tied full-text ranks
-- Description: The full-text functions sorted by ts_rank alone. With the OR
-- query from migration 010, ties are common (two chunks that each contain one
-- query word once score the same), and Postgres returns tied rows in whatever
-- order they sit on disk. That order changes as rows are deleted and space is
-- reused, so the same question could get a different candidate list from one
-- day to the next. Ties are now broken by filename, then chunk index, then id.
-- The tiebreak is arbitrary but stable; it does not change which chunks score
-- higher.
--
-- Updates the two functions the app calls:
--   search_chunks_fulltext_by_session
--   search_chunks_fulltext_by_document_and_session
--
-- Requires migration 010 (fulltext_or_query).
--
-- Rollback: re-run migrations/010_fulltext_or_query.sql.

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
    rank double precision,
    metadata jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
    query tsquery := fulltext_or_query(search_query);
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.contextual_content,
        ts_rank(c.fts, query)::double precision as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE (d.session_id = user_session_id OR d.session_id = 'global')
        AND c.fts @@ query
    ORDER BY rank DESC, d.filename, c.chunk_index, c.id
    LIMIT match_limit;
END;
$$;

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
    rank double precision,
    metadata jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
    query tsquery := fulltext_or_query(search_query);
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.contextual_content,
        ts_rank(c.fts, query)::double precision as rank,
        (c.metadata || jsonb_build_object(
            'document_name', d.filename,
            'chunk_index', c.chunk_index
        )) as metadata
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.document_id = target_document_id
        AND (d.session_id = user_session_id OR d.session_id = 'global')
        AND c.fts @@ query
    ORDER BY rank DESC, d.filename, c.chunk_index, c.id
    LIMIT match_limit;
END;
$$;
