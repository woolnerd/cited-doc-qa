-- Migration 010: Match any query term in full-text search
-- Description: websearch_to_tsquery ANDs every word of the query, so a
-- natural-language question only matched chunks containing all of its words.
-- In the evals that returned nothing for 81% of questions, leaving hybrid
-- search as vector-only. This ORs the query's lexemes instead; ts_rank still
-- puts chunks that match more terms first.
--
-- plainto_tsquery ignores tsquery syntax in user input, drops stop words, and
-- stems, and its output is valid tsquery text, so swapping ' & ' for ' | '
-- is safe. Lexemes never contain spaces. Phrase operators (<->) from
-- hyphenated words are kept and bind tighter than |.
--
-- Updates the two functions the app calls:
--   search_chunks_fulltext_by_session
--   search_chunks_fulltext_by_document_and_session
--
-- Rollback: re-run migrations/006_optimize_fulltext_search.sql, then
--   DROP FUNCTION IF EXISTS fulltext_or_query(text);

CREATE OR REPLACE FUNCTION fulltext_or_query(search_query text)
RETURNS tsquery
LANGUAGE sql
STABLE
AS $$
    SELECT replace(plainto_tsquery('english', search_query)::text, ' & ', ' | ')::tsquery;
$$;

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
    ORDER BY rank DESC
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
    ORDER BY rank DESC
    LIMIT match_limit;
END;
$$;
