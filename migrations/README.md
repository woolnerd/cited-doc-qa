# Database Migrations

This directory contains SQL migration files for the RAG chatbot database.

## Files

- `001_initial_schema.sql` - Initial database schema with pgvector support

## Running Migrations

### Method 1: Supabase Dashboard (Recommended)

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Create a new query
4. Copy and paste the contents of the migration file
5. Run the query

### Method 2: Supabase CLI

```bash
# Install Supabase CLI
npm install -g supabase

# Login
supabase login

# Link to your project
supabase link --project-ref your-project-ref

# Run migration
supabase db push
```

### Method 3: psql

```bash
psql -h db.your-project.supabase.co \
  -U postgres \
  -d postgres \
  -f migrations/001_initial_schema.sql
```

## Migration History

| Migration | Description | Date |
|-----------|-------------|------|
| 001 | Initial schema with pgvector, documents and chunks tables | 2024-10-27 |
| 008 | Public demo usage event tracking | 2026-05-19 |

## Rollback

To rollback a migration, you'll need to manually drop the objects created:

```sql
-- Rollback 001_initial_schema.sql
DROP FUNCTION IF EXISTS hybrid_search;
DROP FUNCTION IF EXISTS get_document_stats;
DROP TABLE IF EXISTS chunks;
DROP TABLE IF EXISTS documents;
DROP EXTENSION IF EXISTS vector;
```

⚠️ **Warning**: Rollback will delete all data in these tables!

## Testing Migrations

After running a migration, test it with:

```sql
-- Verify tables exist
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('documents', 'chunks');

-- Verify indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
AND tablename IN ('documents', 'chunks');

-- Test inserting a document
INSERT INTO documents (filename, file_type, metadata)
VALUES ('test.pdf', 'pdf', '{"test": true}'::jsonb)
RETURNING *;

-- Test inserting a chunk with embedding
INSERT INTO chunks (
  document_id,
  content,
  contextual_content,
  embedding,
  chunk_index,
  metadata
)
VALUES (
  (SELECT id FROM documents WHERE filename = 'test.pdf'),
  'This is a test chunk.',
  'Document: test.pdf\n\nThis is a test chunk.',
  array_fill(0.1, ARRAY[768])::vector(768),
  0,
  '{"token_count": 5}'::jsonb
)
RETURNING *;

-- Test vector search
SELECT
  id,
  content,
  1 - (embedding <=> array_fill(0.1, ARRAY[768])::vector(768)) AS similarity
FROM chunks
ORDER BY embedding <=> array_fill(0.1, ARRAY[768])::vector(768)
LIMIT 5;

-- Clean up test data
DELETE FROM documents WHERE filename = 'test.pdf';
```

## Best Practices

1. **Always backup** before running migrations in production
2. **Test migrations** in a development environment first
3. **Version control** all migration files
4. **Document changes** in this README
5. **Never modify** existing migration files after they've been applied
6. **Create new migrations** for schema changes

## Troubleshooting

### pgvector Extension Not Available

If you get an error about the `vector` extension:
- Ensure you're using Supabase (pgvector is included by default)
- For self-hosted PostgreSQL, install pgvector separately

### Permission Denied

If you get permission errors:
- Ensure you're using the postgres role
- Check your database password is correct
- Verify your IP is allowed in Supabase network settings

### Index Creation Fails

If index creation fails:
- Check you have data in the table first (IVFFlat needs data)
- Try creating the index after inserting some test vectors
- Adjust the `lists` parameter based on your dataset size
