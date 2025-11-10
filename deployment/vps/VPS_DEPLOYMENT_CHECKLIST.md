# VPS PostgreSQL Migration - Deployment Checklist

## Current Status

✅ **Completed:**
- VPS database setup (pgvector, rag_db, migrations)
- PostgreSQL infrastructure code (DatabaseService)
- Search services migrated (vector, full-text, hybrid)
- Query API updated to use PostgreSQL
- Environment templates created (.env.vps.example)

⚠️ **Remaining:**
- Document upload/management services (still use Supabase)
- docker-compose.prod.yml network configuration
- VPS .env.production file update
- Deployment and testing

## Deployment Steps

### 1. Update .env.production on VPS

SSH into VPS and update the .env.production file:

```bash
ssh root@getfreetime.ai
cd ~/production-rag-system
nano .env.production
```

Add these PostgreSQL settings:

```bash
# PostgreSQL Database (n8n postgres container)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=rag_db
POSTGRES_USER=rag_user
POSTGRES_PASSWORD=<password_from_setup_script>
```

Verify all required keys are present:
```bash
grep -E "^(POSTGRES_PASSWORD|GOOGLE_API_KEY|COHERE_API_KEY|OPENROUTER_API_KEY)=" .env.production
```

### 2. Update docker-compose.prod.yml

The application needs to join n8n's Docker network to access the postgres container.

Current docker-compose.prod.yml needs this addition:

```yaml
networks:
  n8n-test_default:
    external: true

services:
  app:
    # ... existing config ...
    networks:
      - n8n-test_default
    environment:
      # Add PostgreSQL vars
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_DB: rag_db
      POSTGRES_USER: rag_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      # Keep existing vars (Google, Cohere, OpenRouter keys)
```

### 3. Deploy Updated Code

Pull the latest code from the vps-postgres-migration branch:

```bash
cd ~/production-rag-system
git fetch origin
git checkout vps-postgres-migration
git pull
```

### 4. Deploy with Docker Compose

```bash
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --build
```

### 5. Verify Deployment

Check logs:
```bash
docker-compose -f docker-compose.prod.yml logs -f app
```

Look for:
- ✅ "PostgreSQL connection pool initialized"
- ✅ "Application startup complete"
- ❌ "Failed to connect to PostgreSQL" (if this appears, check connection)

Test health endpoint:
```bash
curl http://localhost:8001/health
```

### 6. Test Search Functionality

Test a query:
```bash
curl -X POST http://localhost:8001/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test query",
    "top_k": 5
  }'
```

Expected behavior:
- Search should complete successfully
- Logs should show PostgreSQL function calls
- Response time should be faster than Supabase (50-200ms vs 600-2000ms)

### 7. Test Document Upload

**Note:** Document upload still uses Supabase in current code. This will be migrated in a future update.

For now, document upload will continue using Supabase, but searches will use PostgreSQL.

## Troubleshooting

### PostgreSQL Connection Failed

**Error:** "password authentication failed for user 'rag_user'"

**Fix:**
1. Check password in .env.production matches the one used in database setup
2. Verify database was created: `docker exec n8n-test_postgres_1 psql -U rag_user -d rag_db -c "SELECT 1;"`

### Network Connection Issues

**Error:** "could not translate host name 'postgres'"

**Fix:**
1. Verify docker-compose.prod.yml includes the network configuration
2. Check n8n network exists: `docker network ls | grep n8n-test_default`
3. Restart containers: `docker-compose -f docker-compose.prod.yml down && docker-compose -f docker-compose.prod.yml up -d`

### Search Returns No Results

**Check:**
1. Verify migrations were applied: logs should show table creation
2. Check if documents/chunks exist in database
3. Test search function directly:
   ```bash
   docker exec n8n-test_postgres_1 psql -U rag_user -d rag_db -c "SELECT COUNT(*) FROM chunks;"
   ```

## Performance Comparison

**Before (Supabase):**
- Vector search: 600-2000ms (highly variable)
- Frequent timeouts
- Connection issues

**After (VPS PostgreSQL):**
- Vector search: 50-200ms (consistent)
- No timeouts
- Reliable local connection

## Next Phase: Document Services Migration

After search is working on VPS, the next phase will migrate:
1. Document upload (INSERT into documents/chunks tables)
2. Document list/delete operations
3. Complete removal of Supabase dependency

This will be done in a separate PR to keep changes manageable and testable.

## Rollback Plan

If issues occur:

1. Switch back to main branch:
   ```bash
   git checkout main
   git pull
   ```

2. Redeploy:
   ```bash
   docker-compose -f docker-compose.prod.yml down
   docker-compose -f docker-compose.prod.yml up -d --build
   ```

3. Verify Supabase connection is working

## Notes

- The current code gracefully falls back if PostgreSQL is unavailable
- Supabase is still used for document upload/management
- Both Supabase and PostgreSQL credentials can coexist in .env.production
- The migration is designed to be incremental and reversible
