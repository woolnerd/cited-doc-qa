# Database Setup

This directory contains the SQL schema for the RAG Chatbot database.

## Setup Instructions

1. **Go to your Supabase Dashboard**
   - Navigate to your project at https://supabase.com/dashboard
   - Go to the SQL Editor (left sidebar)

2. **Run the Schema Migration**
   - Click "New Query"
   - Copy the entire contents of `schema.sql`
   - Paste into the SQL editor
   - Click "Run" to execute

3. **Verify Setup**
   The script will create:
   - **Extensions**: `uuid-ossp`, `vector` (pgvector)
   - **Tables**: `documents`, `chunks`
   - **Functions**:
     - `search_chunks` - Vector similarity search
     - `search_chunks_by_document` - Vector search within a document
     - `search_chunks_fulltext` - Full-text keyword search
     - `search_chunks_fulltext_by_document` - Full-text search within a document
   - **Indexes**:
     - Vector index (IVFF lat) for fast similarity search
     - Full-text search index (GIN)
     - Foreign key indexes

## Schema Overview

### Documents Table
Stores uploaded document metadata:
- `id` - UUID primary key
- `filename` - Original filename
- `file_type` - pdf, docx, txt
- `file_size` - Size in bytes
- `upload_date` - When uploaded
- `metadata` - JSON B for additional data
- Timestamps (created_at, updated_at)

### Chunks Table
Stores document chunks with embeddings:
- `id` - UUID primary key
- `document_id` - Foreign key to documents
- `content` - Original chunk text
- `contextual_content` - Chunk with document context (better for retrieval)
- `chunk_index` - Position in document
- `embedding` - 768-dimensional vector (Gemini text-embedding-004)
- `fts` - Full-text search vector (auto-generated)
- `metadata` - JSONB for chunk-level data
- Timestamps (created_at, updated_at)

## Testing the Setup

After running the migration, you can test if everything works:

```sql
-- Check if tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('documents', 'chunks');

-- Check if functions exist
SELECT routine_name FROM information_schema.routines
WHERE routine_schema = 'public'
AND routine_name LIKE 'search_chunks%';

-- Check if extensions are enabled
SELECT * FROM pg_extension WHERE extname IN ('uuid-ossp', 'vector');
```

## Row Level Security (RLS)

For production, you may want to enable RLS:

```sql
-- Enable RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;

-- Create policies based on your auth requirements
-- Example: Allow authenticated users to read all data
CREATE POLICY "Allow read access" ON documents FOR SELECT TO authenticated USING (true);
CREATE POLICY "Allow read access" ON chunks FOR SELECT TO authenticated USING (true);
```

## Troubleshooting

**Error: "extension vector does not exist"**
- The pgvector extension must be enabled in Supabase
- Go to Database → Extensions → Enable "vector"

**Error: "function uuid_generate_v4 does not exist"**
- The uuid-ossp extension must be enabled
- This is usually enabled by default in Supabase

**Slow vector search**
- Adjust the `lists` parameter in the ivfflat index based on your data size
- For < 1M vectors: lists = 100 (default)
- For > 1M vectors: lists = sqrt(rows)
