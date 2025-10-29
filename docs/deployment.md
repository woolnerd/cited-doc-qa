# Deployment Guide

This guide covers the automated deployment pipeline for the RAG chatbot system.

> **Note:** For step-by-step setup instructions specific to our production VPS configuration, see [`deployment/VPS-SETUP.md`](../deployment/VPS-SETUP.md). This document provides a general overview of the deployment architecture and workflow.

## Overview

The deployment pipeline automatically:
1. **Builds** Docker images on every push to main
2. **Pushes** images to GitHub Container Registry (ghcr.io)
3. **Deploys** to production VPS (when configured)
4. **Tests** deployment with smoke tests
5. **Rolls back** automatically on failure

## Architecture

```
GitHub Push → CI Tests → Build Docker Image → Push to GHCR → Deploy to VPS → Smoke Tests
                ↓                                                      ↓
              Pass?                                                  Fail?
                ↓                                                      ↓
              Yes → Continue                                    Automatic Rollback
```

## Prerequisites

Before setting up automated deployment:

### 1. VPS Server
- Ubuntu 22.04+ recommended
- 2GB RAM minimum (4GB recommended)
- Docker and Docker Compose installed
- Git installed
- SSH access configured

### 2. Domain Name
- Domain pointing to your VPS
- SSL certificate (Caddy handles this automatically)

### 3. GitHub Secrets
Configure the following secrets in your GitHub repository:

| Secret | Description | Required |
|--------|-------------|----------|
| `VPS_HOST` | VPS IP address or hostname | Yes |
| `VPS_USER` | SSH username (default: `root`) | Yes |
| `VPS_SSH_KEY` | SSH private key for authentication | Yes |

### 4. GitHub Variables
Configure these variables in your repository settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `VPS_CONFIGURED` | Set to `true` to enable deployment | `false` |
| `DEPLOYMENT_URL` | Public URL of your deployment | `https://rag.getfreetime.ai` |

## Setup Instructions

### Step 1: Prepare VPS

SSH into your VPS and run the following commands:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose -y

# Add current user to docker group (if not root)
sudo usermod -aG docker $USER

# Create application directory
sudo mkdir -p /root/production-rag-system
# Or for non-root: sudo mkdir -p /opt/production-rag-system && sudo chown $USER:$USER /opt/production-rag-system
```

### Step 2: Configure SSH Access

On your local machine, generate an SSH key for GitHub Actions:

```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github-deploy

# Copy public key to VPS (replace with your username)
ssh-copy-id -i ~/.ssh/github-deploy.pub root@your-vps-ip
```

Add the private key to GitHub Secrets:
1. Go to your repository → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `VPS_SSH_KEY`
4. Value: Copy contents of `~/.ssh/github-deploy` (the private key)

### Step 3: Clone Repository on VPS

SSH into the VPS:

```bash
ssh root@your-vps-ip
cd /root/production-rag-system
git clone https://github.com/yourusername/production-rag-system.git .
```

### Step 4: Configure Environment Variables

Create `.env.production` on the VPS:

```bash
cd /root/production-rag-system
cp .env.example .env.production
nano .env.production
```

Set the following variables:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-production-supabase-key
GEMINI_API_KEY=your-gemini-api-key
COHERE_API_KEY=your-cohere-api-key
OPENROUTER_API_KEY=your-openrouter-api-key
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

### Step 5: Configure GitHub Repository

1. **Add Secrets:**
   - Go to Settings → Secrets and variables → Actions
   - Add `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`

2. **Add Variables:**
   - Go to Settings → Secrets and variables → Actions → Variables
   - Add `VPS_CONFIGURED` = `true`
   - Add `DEPLOYMENT_URL` = `https://your-domain.com`

3. **Enable Container Registry:**
   - Ensure packages write permission is enabled
   - Go to Settings → Actions → General
   - Under "Workflow permissions", select "Read and write permissions"

### Step 6: Test Deployment

Trigger a manual deployment:

```bash
# On local machine
git checkout main
git pull
git commit --allow-empty -m "Test deployment"
git push
```

Watch the deployment:
1. Go to Actions tab in GitHub
2. Click on "Deploy to Production" workflow
3. Monitor the progress

## Workflow Details

### Build and Push Job

**Triggers on:** Push to main branch or manual trigger

**Actions:**
1. Checks out code
2. Sets up Docker Buildx
3. Logs in to GitHub Container Registry
4. Builds Docker image with caching
5. Tags image with:
   - `main-<git-sha>` (specific version)
   - `latest` (always points to latest main)
6. Pushes to `ghcr.io/yourusername/production-rag-system`

**Outputs:**
- `image-tag`: Full image tag for deployment
- `image-digest`: Image digest for verification

### Deploy to VPS Job

**Runs if:** `VPS_CONFIGURED` variable is `true`

**Actions:**
1. SSHs into VPS
2. Pulls latest code from main branch
3. Pulls latest Docker image from registry
4. Stops old containers
5. Starts new containers with `docker-compose.prod.yml`
6. Waits 10 seconds for startup
7. Verifies health endpoint
8. Cleans up old Docker images
9. Runs smoke tests from GitHub Actions runner
10. Generates deployment summary

**Environment:**
- Name: `production`
- URL: Configured deployment URL

### Rollback Job

**Runs if:** Deploy job fails

**Actions:**
1. SSHs into VPS
2. Finds previous Docker image
3. Restarts containers with previous image
4. Verifies rollback success
5. Notifies of rollback

## Smoke Tests

The deployment runs the following smoke tests:

1. **Health Check** - Verifies `/health` endpoint returns 200
2. **API Docs** - Verifies `/docs` endpoint is accessible
3. **Container Status** - Verifies container is running

## Rollback Mechanism

If deployment fails:
1. Automatically triggers rollback job
2. Finds the previous Docker image on VPS
3. Restarts containers with previous version
4. Verifies rollback was successful
5. Reports failure in GitHub Actions summary

## Manual Operations

### Manual Deployment

Trigger manually from GitHub Actions:
1. Go to Actions → Deploy to Production
2. Click "Run workflow"
3. Select branch (usually main)
4. Click "Run workflow"

### Manual Rollback

If automatic rollback fails, manually rollback on VPS:

```bash
ssh root@your-vps-ip
cd /root/production-rag-system

# List available images
docker images | grep production-rag-system

# Use specific version
export IMAGE_TAG=ghcr.io/yourusername/production-rag-system:main-abc123
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d

# Verify
curl http://localhost:8001/health
```

### View Logs

```bash
# On VPS
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f app

# Last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail=100
```

### Restart Services

```bash
# Restart all
docker-compose -f docker-compose.prod.yml restart

# Restart specific service
docker-compose -f docker-compose.prod.yml restart app
```

## Monitoring Deployments

### GitHub Actions Dashboard

Monitor deployments:
- **Actions Tab** - View deployment status
- **Environments** - See production deployment history
- **Packages** - View published Docker images

### VPS Monitoring

Check container status:
```bash
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs --tail=50
```

Health check:
```bash
curl http://localhost:8001/health
```

## Troubleshooting

### Deployment Fails with "Connection Refused"

**Issue:** Cannot connect to VPS via SSH

**Solutions:**
1. Verify `VPS_HOST` is correct
2. Verify `VPS_SSH_KEY` is the private key
3. Ensure public key is in `~/.ssh/authorized_keys` on VPS
4. Check VPS firewall allows SSH (port 22)

### Deployment Fails with "Health Check Failed"

**Issue:** Application starts but health check fails

**Solutions:**
1. Check logs: `docker-compose logs -f`
2. Verify environment variables in `.env.production`
3. Ensure Supabase connection works
4. Check if port 8001 is available

### Image Pull Fails

**Issue:** Cannot pull Docker image from registry

**Solutions:**
1. Ensure VPS can access ghcr.io
2. Verify image was pushed successfully
3. Check if registry is public or login required
4. For private registry, add `docker login ghcr.io`

### Rollback Doesn't Work

**Issue:** Automatic rollback fails

**Solutions:**
1. Manually rollback (see Manual Operations)
2. Check if previous images exist: `docker images`
3. Verify health endpoint is accessible
4. Check container logs for errors

## Security Considerations

### SSH Keys
- **Never commit SSH keys to repository**
- Use separate keys for deployment
- Rotate keys periodically
- Use `ssh-keygen -t ed25519` for modern keys

### Secrets Management
- All API keys in `.env.production` on VPS
- Never commit `.env.production` to Git
- Use GitHub Secrets for sensitive data
- Rotate API keys regularly

### VPS Security
- Keep system updated: `sudo apt update && sudo apt upgrade`
- Configure firewall: Only allow 22 (SSH), 80 (HTTP), 443 (HTTPS)
- Use key-based SSH authentication only
- Disable password authentication
- Consider fail2ban for brute force protection

## Performance

### Deployment Time

Typical deployment timeline:
- **Build Image:** 1-2 minutes (with cache)
- **Push Image:** 30-60 seconds
- **Deploy to VPS:** 30 seconds
- **Smoke Tests:** 10 seconds
- **Total:** ~3-4 minutes

### Optimizations

- **Build cache:** Speeds up subsequent builds
- **Multi-stage builds:** Smaller images, faster downloads
- **Docker layer caching:** Reuses unchanged layers
- **Parallel jobs:** Build and test run concurrently

## Next Steps

After deployment pipeline is set up:
1. **Configure Caddy reverse proxy** (Issue #16)
2. **Set up monitoring** (Prometheus/Grafana)
3. **Configure log aggregation** (ELK stack or Loki)
4. **Set up alerts** (email/Slack on deployment failures)
5. **Implement blue-green deployment** (zero downtime)

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [SSH Action](https://github.com/appleboy/ssh-action)
