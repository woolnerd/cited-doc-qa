-- RAG Chatbot Database Schema
-- Run this in your Supabase SQL Editor to set up the database

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    upload_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create chunks table with vector embeddings
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    contextual_content TEXT,  -- Content with document context for better retrieval
    chunk_index INTEGER NOT NULL,
    embedding vector(768),  -- Gemini text-embedding-004 produces 768-dimensional vectors
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT fk_document FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Create full-text search index
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(contextual_content, content))) STORED;
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON chunks USING GIN(fts);

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

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chunks_updated_at BEFORE UPDATE ON chunks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
