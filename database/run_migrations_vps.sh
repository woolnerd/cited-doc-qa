#!/bin/bash
# Run RAG migrations on VPS PostgreSQL
# Run this on the VPS

set -e

POSTGRES_CONTAINER="n8n-test_postgres_1"
RAG_DB="rag_db"
RAG_USER="rag_user"
MIGRATIONS_DIR="$(dirname "$0")/../migrations"

echo "🔄 Running RAG migrations on VPS PostgreSQL..."

# Check if migrations directory exists
if [ ! -d "$MIGRATIONS_DIR" ]; then
    echo "❌ Migrations directory not found: $MIGRATIONS_DIR"
    exit 1
fi

# Run each migration in order
for migration in "$MIGRATIONS_DIR"/*.sql; do
    migration_name=$(basename "$migration")
    echo "📝 Applying migration: $migration_name"

    # Copy migration to container and execute
    docker cp "$migration" "$POSTGRES_CONTAINER:/tmp/$migration_name"
    docker exec -i $POSTGRES_CONTAINER psql -U $RAG_USER -d $RAG_DB -f "/tmp/$migration_name"

    # Cleanup
    docker exec $POSTGRES_CONTAINER rm "/tmp/$migration_name"

    echo "✅ Applied: $migration_name"
done

echo ""
echo "🎉 All migrations applied successfully!"
echo ""
echo "🔍 Verifying setup..."
docker exec -i $POSTGRES_CONTAINER psql -U $RAG_USER -d $RAG_DB <<EOF
-- Check tables
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Check pgvector extension
SELECT * FROM pg_extension WHERE extname = 'vector';
EOF
