# VPS PostgreSQL Migration Plan

Migrate from Supabase to self-hosted PostgreSQL on VPS (n8n's postgres container).

## Overview

**Current:** Supabase (slow free tier)
**Target:** Self-hosted PostgreSQL 16 with pgvector on VPS

## Prerequisites

- VPS with running n8n PostgreSQL container (`n8n-test_postgres_1`)
- PostgreSQL 16 (already installed)
- Docker access on VPS
- SSH access to VPS

## Migration Steps

### Phase 1: Database Setup (On VPS)

1. **Install pgvector extension**
```bash
# SSH into VPS
ssh root@getfreetime.ai

# Run setup script
cd ~/production-rag-system
chmod +x database/setup_vps_postgres.sh
export RAG_PASSWORD="your_secure_password_here"
./database/setup_vps_postgres.sh
```

2. **Run migrations**
```bash
chmod +x database/run_migrations_vps.sh
./database/run_migrations_vps.sh
```

### Phase 2: Code Changes (Local Development)

1. **Update dependencies in `backend/requirements.txt`**
```
# Remove:
supabase==2.0.0

# Add:
asyncpg==0.29.0
psycopg2-binary==2.9.9
```

2. **Update configuration in `backend/app/core/config.py`**
```python
# Replace Supabase config with PostgreSQL
DATABASE_URL: str = "postgresql+asyncpg://rag_user:password@postgres:5432/rag_db"
# Or use individual components:
POSTGRES_HOST: str = "postgres"
POSTGRES_PORT: int = 5432
POSTGRES_DB: str = "rag_db"
POSTGRES_USER: str = "rag_user"
POSTGRES_PASSWORD: str = "changeme123"
```

3. **Replace Supabase client with PostgreSQL client**
   - Update `backend/app/core/dependencies.py`
   - Replace all Supabase operations with direct SQL
   - Update services to use asyncpg/SQLAlchemy

### Phase 3: Docker Configuration

1. **Update `docker-compose.prod.yml`**
```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: rag-chatbot-prod
    ports:
      - "8001:8000"
    environment:
      # Remove Supabase vars
      # SUPABASE_URL: ${SUPABASE_URL}
      # SUPABASE_KEY: ${SUPABASE_KEY}

      # Add PostgreSQL vars
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_DB: rag_db
      POSTGRES_USER: rag_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

      # Keep other vars
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
      COHERE_API_KEY: ${COHERE_API_KEY}
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
    networks:
      - n8n-test_default  # Join n8n's network to access postgres
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  n8n-test_default:
    external: true  # Use n8n's existing network
```

2. **Update `.env` on VPS**
```bash
# Add to ~/production-rag-system/.env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=rag_db
POSTGRES_USER=rag_user
POSTGRES_PASSWORD=your_secure_password
```

### Phase 4: Data Migration (Optional)

If you want to migrate existing data from Supabase:

1. **Export from Supabase**
```bash
# Use Supabase CLI or pg_dump
supabase db dump > supabase_dump.sql
```

2. **Import to VPS**
```bash
# Copy dump to VPS
scp supabase_dump.sql root@getfreetime.ai:~/

# Import
docker cp ~/supabase_dump.sql n8n-test_postgres_1:/tmp/
docker exec -i n8n-test_postgres_1 psql -U rag_user -d rag_db -f /tmp/supabase_dump.sql
```

### Phase 5: Testing

1. **Test locally with port forwarding**
```bash
# Forward VPS postgres port
ssh -L 5432:localhost:5432 root@getfreetime.ai

# Update local .env
DATABASE_URL=postgresql://rag_user:password@localhost:5432/rag_db

# Test connection
python -m backend.tests.test_db_connection
```

2. **Deploy and verify**
```bash
# On VPS
cd ~/production-rag-system
git pull
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --build

# Check logs
docker-compose -f docker-compose.prod.yml logs -f app
```

## Network Configuration

The RAG app needs to communicate with the n8n postgres container:

```yaml
# Option 1: Join n8n's network (Recommended)
networks:
  n8n-test_default:
    external: true

# Option 2: Expose postgres port (Less secure)
# In n8n's docker-compose.yaml:
postgres:
  ports:
    - "5432:5432"
```

## Connection String Formats

**From within Docker network:**
```
postgresql://rag_user:password@postgres:5432/rag_db
postgresql+asyncpg://rag_user:password@postgres:5432/rag_db
```

**From host machine (if port exposed):**
```
postgresql://rag_user:password@localhost:5432/rag_db
```

## Security Considerations

1. **Change default password** - Use strong password for `rag_user`
2. **Network isolation** - Keep postgres internal to docker network
3. **Regular backups** - Set up automated pg_dump backups
4. **Connection pooling** - Use pgbouncer if needed for connection management

## Rollback Plan

If migration fails:

1. Revert code changes
2. Update docker-compose to use Supabase again
3. Redeploy previous version
4. Drop `rag_db` if needed:
```bash
docker exec -i n8n-test_postgres_1 psql -U n8n <<EOF
DROP DATABASE IF EXISTS rag_db;
DROP USER IF EXISTS rag_user;
EOF
```

## Performance Benefits

**Before (Supabase free tier):**
- Vector search: ~600ms-2000ms (highly variable)
- Frequent timeouts
- Connection issues

**After (VPS PostgreSQL):**
- Vector search: ~50-200ms (consistent)
- No connection issues
- Full control over indexing and tuning

## Next Steps

1. Run database setup scripts on VPS
2. Update code to use asyncpg
3. Test locally with SSH tunnel
4. Deploy to VPS
5. Monitor performance
6. Set up automated backups

## Useful Commands

**Check database size:**
```bash
docker exec n8n-test_postgres_1 psql -U rag_user -d rag_db -c "SELECT pg_size_pretty(pg_database_size('rag_db'));"
```

**Check table sizes:**
```bash
docker exec n8n-test_postgres_1 psql -U rag_user -d rag_db -c "
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

**Backup database:**
```bash
docker exec n8n-test_postgres_1 pg_dump -U rag_user rag_db > rag_backup_$(date +%Y%m%d).sql
```

**Restore database:**
```bash
docker exec -i n8n-test_postgres_1 psql -U rag_user -d rag_db < rag_backup_20251106.sql
```
