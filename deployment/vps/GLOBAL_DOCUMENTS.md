# Managing Global Documents

## Overview
Global documents have `session_id = 'global'` and are visible to all users in the demo.

## Workflow

### 1. Upload Document via Browser
- Open the app in your browser
- Upload the document normally (it gets your browser's session_id)
- Note the filename or document ID

### 2. Make Document Global via VPS

**SSH into VPS:**
```bash
ssh root@your-vps-ip
```

**Connect to PostgreSQL:**
```bash
# If using Docker:
docker exec -it rag-demo-postgres-1 psql -U rag_user -d rag_chatbot

# If using local PostgreSQL:
psql -U rag_user -d rag_chatbot
```

**Make document global:**

By filename (easiest):
```sql
UPDATE documents SET session_id = 'global'
WHERE filename = 'sample-electricity-bill.pdf';
```

By document ID:
```sql
UPDATE documents SET session_id = 'global'
WHERE id = '123e4567-e89b-12d3-a456-426614174000';
```

By listing documents first:
```sql
-- List recent documents
SELECT id, filename, session_id, upload_date
FROM documents
ORDER BY upload_date DESC
LIMIT 10;

-- Then update the one you want
UPDATE documents SET session_id = 'global' WHERE id = '<id-from-above>';
```

**Verify:**
```sql
-- List all global documents
SELECT id, filename, upload_date, session_id
FROM documents
WHERE session_id = 'global';

-- Count documents per session
SELECT session_id, COUNT(*) as doc_count
FROM documents
GROUP BY session_id;
```

**Exit PostgreSQL:**
```sql
\q
```

### 3. Test in Browser
- Open the app in a **new incognito/private window** (different session)
- The global document should appear in the document list
- Try querying it - should work from any session

## Use Cases

**Demo Setup:**
Upload 2-3 sample documents (electricity bills, contracts, etc.) and make them global so all demo users can try the system immediately.

**Shared Resources:**
Documents that should be accessible to everyone (FAQs, terms of service, etc.)

## Quick Reference Commands

```sql
-- Make document global by filename
UPDATE documents SET session_id = 'global' WHERE filename = 'your-file.pdf';

-- List global documents
SELECT filename FROM documents WHERE session_id = 'global';

-- Count chunks for global documents (verify processing)
SELECT d.filename, COUNT(c.id) as chunk_count
FROM documents d
LEFT JOIN chunks c ON d.id = c.document_id
WHERE d.session_id = 'global'
GROUP BY d.filename;

-- Remove global status (make it session-specific again)
UPDATE documents SET session_id = 'session_xyz' WHERE filename = 'your-file.pdf';
```

## Security Note

Global documents are **read-only** for users:
- Users can search/query global documents
- Users **cannot delete** global documents (403 Forbidden)
- Only session-owned documents can be deleted

See `backend/app/api/documents.py:469` for delete protection logic.
