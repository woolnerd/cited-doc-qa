#!/bin/bash
# VPS Setup Script for RAG Chatbot Production Deployment
#
# This script sets up the RAG chatbot on your existing VPS infrastructure.
# Designed for: Ubuntu 24.04.2 LTS with existing Caddy + Docker setup
#
# IMPORTANT: This script assumes you already have:
# - Docker and Docker Compose installed
# - Caddy installed and running
# - SSH access as root user
#
# Usage: Run as root on your VPS
#   sudo bash vps-setup.sh

set -e  # Exit on any error

echo "🚀 RAG Chatbot VPS Setup"
echo "========================"
echo ""

# Configuration
PROJECT_DIR="/root/production-rag-system"
REPO_URL="https://github.com/woolnerd/production-rag-system.git"
CADDY_CONFIG="/etc/caddy/Caddyfile"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root"
    exit 1
fi

echo "✅ Running as root"

# Check Docker installation
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi
echo "✅ Docker is installed"

# Check Docker Compose installation
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi
echo "✅ Docker Compose is installed"

# Check Caddy installation
if ! command -v caddy &> /dev/null; then
    echo "❌ Caddy is not installed. Please install Caddy first."
    exit 1
fi
echo "✅ Caddy is installed"

# Create project directory if it doesn't exist
if [ ! -d "$PROJECT_DIR" ]; then
    echo "📁 Creating project directory: $PROJECT_DIR"
    mkdir -p "$PROJECT_DIR"
else
    echo "📁 Project directory already exists: $PROJECT_DIR"
fi

# Clone or update repository
if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "📥 Cloning repository..."
    git clone "$REPO_URL" "$PROJECT_DIR"
else
    echo "📥 Updating repository..."
    cd "$PROJECT_DIR"
    git fetch origin
    git pull origin main
fi

cd "$PROJECT_DIR"
echo "✅ Repository ready at $PROJECT_DIR"

# Check for .env.production file
if [ ! -f "$PROJECT_DIR/.env.production" ]; then
    echo ""
    echo "⚠️  .env.production file not found!"
    echo ""
    echo "Please create .env.production with the following variables:"
    echo "  SUPABASE_URL=https://your-project.supabase.co"
    echo "  SUPABASE_KEY=your-production-key"
    echo "  GEMINI_API_KEY=your-gemini-key"
    echo "  COHERE_API_KEY=your-cohere-key"
    echo "  OPENROUTER_API_KEY=your-openrouter-key"
    echo "  ENVIRONMENT=production"
    echo "  LOG_LEVEL=WARNING"
    echo ""
    echo "You can copy from .env.example:"
    echo "  cp .env.example .env.production"
    echo "  nano .env.production"
    echo ""
    exit 1
else
    echo "✅ .env.production file exists"
fi

# Check Caddy configuration for RAG subdomain
echo ""
echo "🔍 Checking Caddy configuration..."
if grep -q "rag.getfreetime.ai" "$CADDY_CONFIG"; then
    echo "✅ Caddy configuration includes rag.getfreetime.ai"
else
    echo ""
    echo "⚠️  Caddy configuration does NOT include rag.getfreetime.ai"
    echo ""
    echo "Please add the following to $CADDY_CONFIG:"
    echo ""
    cat "$PROJECT_DIR/deployment/caddy-snippet.txt"
    echo ""
    echo "After adding:"
    echo "  1. Validate: sudo caddy validate --config /etc/caddy/Caddyfile"
    echo "  2. Reload: sudo systemctl reload caddy"
    echo ""
    read -p "Press Enter after you've added the Caddy configuration..."
fi

# Login to GitHub Container Registry (required for private repos)
echo ""
echo "🔑 Docker Registry Authentication"
echo ""
echo "To pull Docker images from GitHub Container Registry, you need to authenticate."
echo "You'll need a GitHub Personal Access Token with 'read:packages' permission."
echo ""
echo "Create token at: https://github.com/settings/tokens/new"
echo "Required scope: read:packages"
echo ""
read -p "Do you want to authenticate now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Enter your GitHub username:"
    read GITHUB_USERNAME
    echo "Enter your Personal Access Token:"
    read -s GITHUB_TOKEN
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin
    echo "✅ Authenticated with GitHub Container Registry"
else
    echo "⚠️  Skipping authentication. You may need to authenticate later to pull images."
fi

# Pull latest Docker image
echo ""
echo "🐳 Pulling latest Docker image..."
docker-compose -f docker-compose.prod.yml pull || echo "⚠️  Could not pull image. Will build locally if needed."

# Start the application
echo ""
echo "🚀 Starting RAG Chatbot..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for health check
echo ""
echo "⏳ Waiting for application to start..."
sleep 10

# Check health endpoint
if curl -f http://localhost:8001/health > /dev/null 2>&1; then
    echo "✅ Health check passed!"
else
    echo "⚠️  Health check failed. Checking logs..."
    docker-compose -f docker-compose.prod.yml logs --tail=50
    echo ""
    echo "The application may still be starting. Check logs with:"
    echo "  docker-compose -f docker-compose.prod.yml logs -f"
    exit 1
fi

# Test Caddy reverse proxy
echo ""
echo "🌐 Testing reverse proxy..."
if curl -f https://rag.getfreetime.ai/health > /dev/null 2>&1; then
    echo "✅ Reverse proxy working! Application is accessible at https://rag.getfreetime.ai"
else
    echo "⚠️  Reverse proxy not responding yet. This is normal if DNS hasn't propagated."
    echo "   Check:"
    echo "   1. DNS records point to this server"
    echo "   2. Caddy configuration is correct"
    echo "   3. Caddy is running: sudo systemctl status caddy"
fi

echo ""
echo "=================================="
echo "✅ Setup Complete!"
echo "=================================="
echo ""
echo "Application is running at:"
echo "  Local: http://localhost:8001"
echo "  Public: https://rag.getfreetime.ai"
echo ""
echo "Useful commands:"
echo "  View logs:     docker-compose -f docker-compose.prod.yml logs -f"
echo "  Restart:       docker-compose -f docker-compose.prod.yml restart"
echo "  Stop:          docker-compose -f docker-compose.prod.yml down"
echo "  Update app:    cd $PROJECT_DIR && git pull && docker-compose -f docker-compose.prod.yml pull && docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo "Caddy commands:"
echo "  Reload config: sudo systemctl reload caddy"
echo "  View logs:     sudo journalctl -u caddy -f"
echo "  Status:        sudo systemctl status caddy"
echo ""
