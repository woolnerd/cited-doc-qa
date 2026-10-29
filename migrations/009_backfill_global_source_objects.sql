-- Migration 009: Explicit source-object mappings for global documents
-- Description: The source-url endpoint no longer infers GCS object names from
-- document filenames (callers control filenames). Only documents with an
-- explicit metadata.source_object can be viewed. This backfills the mapping for
-- existing global documents, which were previously resolved as
-- "<GCS_SOURCE_PREFIX>/<filename>" (prefix is empty in production).
--
-- Review before running: every global document listed by the SELECT below will
-- become viewable. Remove any you did not intentionally publish.
--
--   SELECT id, filename, metadata FROM documents
--   WHERE session_id = 'global' AND NOT (metadata ? 'source_object');
--
-- If your bucket uses a prefix, replace `filename` with `'<prefix>/' || filename`.

UPDATE documents
SET metadata = coalesce(metadata, '{}'::jsonb)
    || jsonb_build_object('source_object', filename)
WHERE session_id = 'global'
  AND NOT (coalesce(metadata, '{}'::jsonb) ? 'source_object');

-- Rollback (restores filename-inference era state; only needed with pre-009 code):
--   UPDATE documents SET metadata = metadata - 'source_object'
--   WHERE session_id = 'global' AND metadata->>'source_object' = filename;
