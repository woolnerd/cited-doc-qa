# VPS Environment Setup

## Creating the .env file on VPS

After running the database setup scripts, you need to create a `.env` file with your configuration.

### Step 1: Copy the example file

```bash
# On VPS
cd ~/production-rag-system
cp .env.vps.example .env
```

### Step 2: Edit the .env file

```bash
nano .env
```

### Step 3: Update the following values

**Required - PostgreSQL Password:**
```bash
POSTGRES_PASSWORD=the_password_from_setup_script
```

**Required - AI Service Keys:**
```bash
# Get from Supabase secrets or your local .env
GOOGLE_API_KEY=your_google_api_key
COHERE_API_KEY=your_cohere_api_key
OPENROUTER_API_KEY=your_openrouter_key
```

**Optional - Adjust if needed:**
```bash
# Frontend domain (if different)
ALLOWED_ORIGINS=["https://rag.getfreetime.ai", "http://localhost:3000"]

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Step 4: Secure the .env file

```bash
chmod 600 .env  # Only root can read/write
```

### Step 5: Verify the configuration

```bash
# Check if all required vars are set
grep -E "^(POSTGRES_PASSWORD|GOOGLE_API_KEY|COHERE_API_KEY|OPENROUTER_API_KEY)=" .env
```

Should show all four keys with values (not the placeholder text).

## Quick Copy Commands

If you have the values, you can update them directly:

```bash
# On VPS
cd ~/production-rag-system

# Update postgres password
sed -i "s/YOUR_SECURE_PASSWORD_HERE/your_actual_password/" .env

# Update API keys
sed -i "s/your_google_api_key_here/AIza.../" .env
sed -i "s/your_cohere_api_key_here/xxx.../" .env
sed -i "s/your_openrouter_key_here/sk-or-.../" .env
```

## Finding Your Current API Keys

If you need to retrieve your current API keys from Supabase:

```bash
# From local machine
cd ~/Desktop/FreetimeAI/claude-projects/rag-demo/backend
cat .env | grep -E "^(GOOGLE|COHERE|OPENROUTER)"
```

Then copy those values to the VPS .env file.

## Troubleshooting

**Issue:** "Database connection failed"
```bash
# Check postgres password
docker exec n8n-test_postgres_1 psql -U rag_user -d rag_db -c "SELECT 1;"
# If this fails, the password is wrong
```

**Issue:** "API key invalid"
```bash
# Test each key individually
# Google (Gemini):
curl -H "x-goog-api-key: YOUR_KEY" \
  "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004"

# Cohere:
curl -H "Authorization: Bearer YOUR_KEY" \
  "https://api.cohere.com/v1/check-api-key"

# OpenRouter:
curl -H "Authorization: Bearer YOUR_KEY" \
  "https://openrouter.ai/api/v1/models"
```

## Next Steps

After creating the .env file:
1. Update backend code to use PostgreSQL (next PR)
2. Update docker-compose.prod.yml to join n8n network
3. Deploy with `docker-compose up -d --build`
4. Verify with `docker-compose logs -f app`
