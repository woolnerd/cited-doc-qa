-- Migration 006a: Add fts column for full-text search optimization
-- Description: Creates the missing fts tsvector column that should have been in migration 001
--
-- PROBLEM:
--   Migration 001 created an index on to_tsvector('english', content) but didn't create
--   a stored fts column. Migration 006 expects this column to exist.
--
-- SOLUTION:
--   Add the fts column as a generated column and create a GIN index on it
--   This enables the optimized search functions from migration 006 to work

-- =============================================================================
-- ADD FTS COLUMN
-- =============================================================================

-- Add the fts column as a generated/computed column
-- This will be automatically updated whenever content or contextual_content changes
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(contextual_content, content))) STORED;

-- Drop the old index on to_tsvector('english', content) if it exists
DROP INDEX IF EXISTS chunks_content_fts_idx;

-- Create new GIN index on the fts column
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON chunks USING GIN(fts);

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================

DO $$
BEGIN
  RAISE NOTICE '========================================';
  RAISE NOTICE 'Migration 006a: Add fts column';
  RAISE NOTICE '========================================';
  RAISE NOTICE '';
  RAISE NOTICE 'Changes made:';
  RAISE NOTICE '  ✓ Added fts tsvector column (generated from contextual_content + content)';
  RAISE NOTICE '  ✓ Dropped old chunks_content_fts_idx index';
  RAISE NOTICE '  ✓ Created new idx_chunks_fts GIN index';
  RAISE NOTICE '';
  RAISE NOTICE 'The fts column will be automatically populated for all existing chunks.';
  RAISE NOTICE 'Migration 006 search functions can now use this column.';
  RAISE NOTICE '';
  RAISE NOTICE 'Migration completed successfully!';
END $$;
