# VPS Production Setup Guide

This guide covers setting up the RAG chatbot on a production VPS server with existing infrastructure.

## Overview

This setup is designed for a VPS that already has:
- Docker and Docker Compose installed
- Caddy reverse proxy configured and running
- Existing applications and services

The RAG chatbot will be integrated into your existing infrastructure without disrupting other services.

## Prerequisites

- Ubuntu 22.04+ (tested on Ubuntu 24.04.2 LTS)
- Docker and Docker Compose installed
- Caddy installed and running
- SSH access as root user
- Domain configured (rag.getfreetime.ai)
- GitHub account with repository access

## Architecture

```
Internet → Caddy (port 443) → Docker Container (port 8001:8000) → FastAPI App
           rag.getfreetime.ai
```

- **External**: HTTPS traffic to rag.getfreetime.ai
- **Caddy**: Reverse proxy on port 443 → localhost:8001
- **Docker**: Maps port 8001 (host) → 8000 (container)
- **Application**: FastAPI runs on port 8000 inside container

## Setup Instructions

### Step 1: Generate SSH Key for GitHub Actions

On your local machine:

```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github-deploy-rag

# Copy public key to VPS
ssh-copy-id -i ~/.ssh/github-deploy-rag.pub root@67.217.241.245
```

### Step 2: Configure GitHub Repository Secrets

Go to your repository → Settings → Secrets and variables → Actions

Add these secrets:

| Secret | Value | Description |
|--------|-------|-------------|
| `VPS_HOST` | `67.217.241.245` | Your VPS IP address |
| `VPS_USER` | `root` | SSH username (root) |
| `VPS_SSH_KEY` | (contents of `~/.ssh/github-deploy-rag`) | Private key |

Add these variables:

| Variable | Value | Description |
|----------|-------|-------------|
| `VPS_CONFIGURED` | `true` | Enables deployment workflow |
| `DEPLOYMENT_URL` | `https://rag.getfreetime.ai` | Public URL |

### Step 3: Clone Repository on VPS

SSH into your VPS:

```bash
ssh root@67.217.241.245
cd /root
git clone https://github.com/woolnerd/production-rag-system.git
cd production-rag-system
```

### Step 4: Create Environment Variables

Create `.env.production` file:

```bash
cd /root/production-rag-system
cp .env.example .env.production
nano .env.production
```

Set the following:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-production-supabase-key
GEMINI_API_KEY=your-gemini-api-key
COHERE_API_KEY=your-cohere-api-key
OPENROUTER_API_KEY=your-openrouter-api-key
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

Save and exit (Ctrl+O, Enter, Ctrl+X).

### Step 5: Add Caddy Configuration

Edit your Caddyfile:

```bash
sudo nano /etc/caddy/Caddyfile
```

Add this configuration block (the snippet is provided in `deployment/caddy-snippet.txt`):

```caddy
rag.getfreetime.ai {
    reverse_proxy localhost:8001

    encode gzip

    log {
        output file /var/log/caddy/rag-access.log
    }

    header {
        Strict-Transport-Security "max-age=31536000;"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
    }
}
```

Validate and reload Caddy:

```bash
# Validate configuration
sudo caddy validate --config /etc/caddy/Caddyfile

# Reload Caddy
sudo systemctl reload caddy

# Check status
sudo systemctl status caddy
```

### Step 6: Authenticate with GitHub Container Registry

To pull Docker images from GitHub Container Registry:

```bash
# Create a GitHub Personal Access Token at:
# https://github.com/settings/tokens/new
# Required scope: read:packages

# Login to registry
echo "YOUR_GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

### Step 7: Run Setup Script

Run the automated setup script:

```bash
cd /root/production-rag-system
chmod +x deployment/vps-setup.sh
sudo bash deployment/vps-setup.sh
```

The script will:
1. Verify Docker and Caddy are installed
2. Check for .env.production file
3. Verify Caddy configuration
4. Pull latest Docker image
5. Start the application
6. Run health checks
7. Test reverse proxy

### Step 8: Verify Deployment

Check that everything is running:

```bash
# Check container status
docker-compose -f docker-compose.prod.yml ps

# Check logs
docker-compose -f docker-compose.prod.yml logs -f

# Test health endpoint locally
curl http://localhost:8001/health

# Test public URL
curl https://rag.getfreetime.ai/health
```

Expected response:
```json
{"status": "healthy", "timestamp": "2025-10-29T12:00:00.000000"}
```

## Automated Deployments

Once configured, deployments happen automatically:

1. **Push to main branch** triggers the deployment workflow
2. **GitHub Actions** builds and pushes Docker image to GHCR
3. **SSH deployment** pulls latest code and image on VPS
4. **Zero-downtime update** with automatic health checks
5. **Automatic rollback** if deployment fails

### Manual Deployment

Trigger manually from GitHub Actions:
1. Go to Actions → Deploy to Production
2. Click "Run workflow"
3. Select branch (main)
4. Click "Run workflow"

### Manual Update on VPS

If you need to manually update:

```bash
cd /root/production-rag-system

# Pull latest code
git pull origin main

# Pull latest image
docker-compose -f docker-compose.prod.yml pull

# Restart with new version
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d

# Check health
curl http://localhost:8001/health
```

## Useful Commands

### Application Management

```bash
# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Restart application
docker-compose -f docker-compose.prod.yml restart

# Stop application
docker-compose -f docker-compose.prod.yml down

# Start application
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps
```

### Caddy Management

```bash
# Reload configuration
sudo systemctl reload caddy

# Restart Caddy
sudo systemctl restart caddy

# View logs
sudo journalctl -u caddy -f

# Check status
sudo systemctl status caddy

# Test configuration
sudo caddy validate --config /etc/caddy/Caddyfile
```

### Troubleshooting

```bash
# View application logs
docker-compose -f docker-compose.prod.yml logs --tail=100

# Check container health
docker inspect rag-chatbot-prod | grep -A 10 Health

# Test health endpoint
curl -v http://localhost:8001/health

# Check if port is listening
sudo netstat -tlnp | grep 8001

# Check Caddy logs
sudo tail -f /var/log/caddy/rag-access.log
sudo tail -f /var/log/caddy/rag-error.log
```

## Common Issues

### Issue: Container won't start

**Check logs:**
```bash
docker-compose -f docker-compose.prod.yml logs
```

**Common causes:**
- Missing or invalid .env.production file
- Port 8001 already in use
- Invalid API keys
- Docker out of disk space

**Fix:**
```bash
# Check .env.production exists and has correct values
cat .env.production

# Check if port is in use
sudo netstat -tlnp | grep 8001

# Check disk space
df -h

# Check Docker disk usage
docker system df
```

### Issue: Health check fails

**Check application:**
```bash
# View recent logs
docker-compose -f docker-compose.prod.yml logs --tail=50

# Check if container is running
docker ps | grep rag-chatbot-prod

# Try health endpoint
curl -v http://localhost:8001/health
```

**Common causes:**
- Application still starting (wait 30 seconds)
- Supabase connection issues
- Environment variables not set
- Application crash on startup

### Issue: Public URL not accessible

**Check reverse proxy:**
```bash
# Test local endpoint works
curl http://localhost:8001/health

# Check Caddy is running
sudo systemctl status caddy

# Check Caddy configuration
sudo caddy validate --config /etc/caddy/Caddyfile

# View Caddy logs
sudo journalctl -u caddy -n 50
```

**Common causes:**
- DNS not propagated yet (wait 5-10 minutes)
- Caddy configuration error
- Caddy not reloaded after config change
- Firewall blocking port 443

**Fix:**
```bash
# Reload Caddy
sudo systemctl reload caddy

# Check DNS resolution
dig rag.getfreetime.ai

# Check firewall (should allow 80, 443)
sudo ufw status
```

### Issue: Deployment fails in GitHub Actions

**Check workflow logs:**
1. Go to repository → Actions tab
2. Click on failed deployment
3. Review logs for specific error

**Common causes:**
- SSH authentication failed
- VPS_HOST, VPS_USER, or VPS_SSH_KEY incorrect
- Repository not cloned on VPS
- .env.production missing

**Fix:**
```bash
# Test SSH connection
ssh -i ~/.ssh/github-deploy-rag root@67.217.241.245

# Verify repository exists
ssh root@67.217.241.245 "ls -la /root/production-rag-system"

# Check .env.production exists
ssh root@67.217.241.245 "ls -la /root/production-rag-system/.env.production"
```

## Security Notes

### SSH Keys

- Use separate SSH key for deployments
- Never commit SSH keys to repository
- Rotate keys periodically
- Use ed25519 algorithm for modern security

### Secrets Management

- All API keys in `.env.production` on VPS
- Never commit `.env.production` to Git
- Use GitHub Secrets for sensitive data in workflows
- Rotate API keys regularly

### Firewall

Your VPS should only allow:
- Port 22 (SSH)
- Port 80 (HTTP - Caddy redirects to HTTPS)
- Port 443 (HTTPS)

```bash
# Check firewall status
sudo ufw status

# Example configuration
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Docker Security

The production setup includes:
- Non-root user (appuser, uid 1000) inside container
- Read-only root filesystem
- Dropped all capabilities except NET_BIND_SERVICE
- No new privileges allowed
- Resource limits (2GB memory, 2 CPU)

## Performance

### Resource Usage

- **Memory:** ~512MB baseline, up to 2GB limit
- **CPU:** 0.5-2.0 cores
- **Disk:** ~400-500MB image size
- **Network:** Minimal (API calls to external services)

### Monitoring

```bash
# Check resource usage
docker stats rag-chatbot-prod

# View container metrics
docker inspect rag-chatbot-prod
```

## Updating the Application

### Automatic Updates (Recommended)

Push to main branch and GitHub Actions handles the rest.

### Manual Updates

```bash
cd /root/production-rag-system
git pull origin main
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

### Rolling Back

```bash
# List available images
docker images | grep production-rag-system

# Use specific version
export IMAGE_TAG=ghcr.io/woolnerd/production-rag-system:main-abc123
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d

# Verify
curl http://localhost:8001/health
```

## Maintenance

### Regular Tasks

**Weekly:**
- Check logs for errors
- Review resource usage
- Update system packages

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Clean up Docker
docker system prune -f
```

**Monthly:**
- Rotate API keys if needed
- Review Caddy logs
- Check disk space
- Backup environment configuration

```bash
# Backup .env.production
cp .env.production .env.production.backup.$(date +%Y%m%d)

# Check disk usage
df -h
docker system df
```

## Next Steps

After successful deployment:

1. **Set up monitoring** - Add Uptime Robot or similar
2. **Configure alerts** - Email/Slack notifications for downtime
3. **Enable backups** - Backup Supabase database regularly
4. **Add analytics** - Track usage and performance
5. **Document runbook** - Common operations and troubleshooting

## Support

For issues or questions:
- Check logs first: `docker-compose -f docker-compose.prod.yml logs -f`
- Review this guide's troubleshooting section
- Check GitHub repository issues
- Contact repository maintainer

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Caddy Documentation](https://caddyserver.com/docs/)
- [GitHub Container Registry](https://docs.github.com/en/packages)
