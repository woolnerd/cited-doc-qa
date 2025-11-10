-- Migration 004: Add session isolation support
-- Description: Add session_id column to documents table to support multi-user session isolation

-- Add session_id column to documents table
ALTER TABLE documents
ADD COLUMN session_id VARCHAR(255) NOT NULL DEFAULT 'global';

-- Create index on session_id for faster filtering
CREATE INDEX idx_documents_session_id ON documents(session_id);

-- Update existing documents to use 'global' session_id (default documents visible to all)
UPDATE documents SET session_id = 'global' WHERE session_id IS NULL;

-- Comments for documentation
COMMENT ON COLUMN documents.session_id IS 'Session identifier for multi-user isolation. Use "global" for documents visible to all users.';
COMMENT ON INDEX idx_documents_session_id IS 'Index for efficient session-based document filtering';

-- Verification query (optional, for testing)
-- SELECT session_id, COUNT(*) as doc_count
-- FROM documents
-- GROUP BY session_id;

-- ==============================================================================
-- MAKING DOCUMENTS GLOBAL (visible to all users)
-- ==============================================================================
-- To make a document visible to all users, set its session_id to 'global'
-- This is useful for demo/sample documents that should be accessible to everyone

-- Make a specific document global:
-- UPDATE documents SET session_id = 'global' WHERE id = '<document-uuid>';

-- Make a document global by filename:
-- UPDATE documents SET session_id = 'global' WHERE filename = 'sample-document.pdf';

-- Make all documents from a session global:
-- UPDATE documents SET session_id = 'global' WHERE session_id = 'session_xxx';

-- List all global documents:
-- SELECT id, filename, upload_date FROM documents WHERE session_id = 'global';
