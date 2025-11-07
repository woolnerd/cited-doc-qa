#!/bin/bash
# Setup script for RAG database on VPS PostgreSQL (n8n container)
# Run this on the VPS inside the postgres container

set -e

echo "🔧 Setting up RAG database on VPS PostgreSQL..."

# Variables
POSTGRES_CONTAINER="n8n-test_postgres_1"
RAG_DB="rag_db"
RAG_USER="rag_user"
RAG_PASSWORD="${RAG_PASSWORD:-changeme123}"  # Override with env var

echo "📦 Installing pgvector extension..."
# Install pgvector in the postgres container
docker exec -u root $POSTGRES_CONTAINER bash -c "
  apt-get update && \
  apt-get install -y postgresql-16-pgvector
"

echo "🗄️  Creating RAG database and user..."
docker exec -i $POSTGRES_CONTAINER psql -U n8n -d n8n <<EOF
-- Create RAG user
CREATE USER $RAG_USER WITH PASSWORD '$RAG_PASSWORD';

-- Create RAG database
CREATE DATABASE $RAG_DB OWNER $RAG_USER;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $RAG_DB TO $RAG_USER;
EOF

echo "🔌 Enabling pgvector extension..."
docker exec -i $POSTGRES_CONTAINER psql -U n8n -d $RAG_DB <<EOF
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant usage on schema
GRANT ALL ON SCHEMA public TO $RAG_USER;
EOF

echo "✅ Database setup complete!"
echo ""
echo "📝 Connection details:"
echo "  Host: postgres (from docker network) or localhost:5432 (if exposed)"
echo "  Database: $RAG_DB"
echo "  User: $RAG_USER"
echo "  Password: $RAG_PASSWORD"
echo ""
echo "🔗 Connection string format:"
echo "  postgresql://$RAG_USER:$RAG_PASSWORD@postgres:5432/$RAG_DB"
