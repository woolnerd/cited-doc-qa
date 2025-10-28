# Docker Setup for RAG Chatbot

This directory contains Docker configuration for the RAG Chatbot system.

## Quick Start

### Local Development

1. **Ensure you have Docker and Docker Compose installed:**
   ```bash
   docker --version
   docker-compose --version
   ```

2. **Create a `.env` file in the project root** (copy from `.env.example`):
   ```bash
   cp .env.example .env
   # Edit .env with your actual API keys
   ```

3. **Build and run with Docker Compose:**
   ```bash
   docker-compose up --build
   ```

4. **Access the application:**
   - Frontend: http://localhost:8000
   - API docs: http://localhost:8000/docs
   - Health check: http://localhost:8000/health

5. **Stop the application:**
   ```bash
   docker-compose down
   ```

### Production Deployment

1. **Create `.env.production` file:**
   ```bash
   cp .env.example .env.production
   # Edit with production values
   ```

2. **Build the production image:**
   ```bash
   docker build -t production-rag-system:latest .
   ```

3. **Run with production compose file:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

4. **View logs:**
   ```bash
   docker-compose -f docker-compose.prod.yml logs -f
   ```

5. **Stop production deployment:**
   ```bash
   docker-compose -f docker-compose.prod.yml down
   ```

## Docker Configuration Files

### Dockerfile
Multi-stage build for optimized production image:
- **Builder stage:** Installs all dependencies
- **Runtime stage:** Minimal image with only runtime requirements
- **Features:**
  - Python 3.11-slim base
  - Non-root user for security
  - Health checks
  - Optimized for size (<500MB target)

### docker-compose.yml
Development configuration:
- Hot reload with volume mounts
- Environment variables from `.env`
- Port 8000 exposed
- Automatic restart

### docker-compose.prod.yml
Production configuration:
- Uses pre-built image from registry
- Resource limits (2GB memory, 2 CPU)
- Security hardening (read-only filesystem, dropped capabilities)
- Always restart policy
- Health checks

### .dockerignore
Excludes unnecessary files from Docker build context:
- Git files
- Python cache
- Tests
- Documentation
- Development tools

## Environment Variables

Required environment variables (set in `.env`):

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
GEMINI_API_KEY=your-gemini-api-key
COHERE_API_KEY=your-cohere-api-key
OPENROUTER_API_KEY=your-openrouter-api-key
```

Optional variables:
```env
ENVIRONMENT=development|production
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
PORT=8000
```

## Docker Commands

### Build
```bash
# Build development image
docker-compose build

# Build production image
docker build -t production-rag-system:latest .

# Build with no cache
docker build --no-cache -t production-rag-system:latest .
```

### Run
```bash
# Run development
docker-compose up

# Run in detached mode
docker-compose up -d

# Run production
docker-compose -f docker-compose.prod.yml up -d
```

### Manage
```bash
# View logs
docker-compose logs -f

# Stop containers
docker-compose down

# Remove volumes
docker-compose down -v

# Shell into running container
docker exec -it rag-chatbot-dev /bin/bash
```

### Cleanup
```bash
# Remove dangling images
docker image prune

# Remove all unused images
docker image prune -a

# Remove all unused containers, networks, images
docker system prune -a
```

## Troubleshooting

### Container won't start
1. Check logs: `docker-compose logs`
2. Verify environment variables are set
3. Ensure all required API keys are valid
4. Check port 8000 is not already in use

### Health check failing
1. Check if the application started successfully
2. Verify `/health` endpoint is accessible
3. Check logs for startup errors
4. Ensure Supabase connection is working

### Image size too large
1. Check what's being copied with `.dockerignore`
2. Review installed dependencies
3. Use multi-stage build properly
4. Clean up apt cache in Dockerfile

### Permission issues
- Container runs as non-root user (uid 1000)
- Ensure mounted volumes have correct permissions
- Use `chown` if needed: `sudo chown -R 1000:1000 ./data`

## CI/CD Integration

The Docker image is automatically built and tested in CI:
1. Build happens on every PR and push
2. Image is tested for health check
3. Size is checked against 500MB target
4. On main branch merge, image can be pushed to registry

## Security Notes

Production deployment includes:
- Non-root user (appuser, uid 1000)
- Read-only root filesystem
- Dropped all Linux capabilities except NET_BIND_SERVICE
- No new privileges allowed
- Health checks for monitoring
- Resource limits to prevent overconsumption

## Performance

Typical image metrics:
- **Image size:** ~400-500MB (target: <500MB)
- **Build time:** 2-3 minutes (with cache: <1 minute)
- **Startup time:** 10-15 seconds
- **Memory usage:** ~512MB baseline, up to 2GB limit

## Next Steps

After Docker setup:
1. Set up container registry (GitHub Container Registry or Docker Hub)
2. Configure automated deployment pipeline
3. Set up monitoring and logging aggregation
4. Implement blue-green deployment for zero downtime
