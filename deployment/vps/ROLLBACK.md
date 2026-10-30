# Rollback Guide

How to undo the 2026-10-29 cutover, how to roll back a bad deploy of this app, and how to undo
later env changes.

## Current Setup (after 2026-10-29 cutover)

| Piece | Value |
|---|---|
| Hostnames | `rag.getfreetime.ai`, `eta.getfreetime.ai` (one Caddy block, no redirect) |
| DNS (Namecheap) | `rag` and `eta` are both A records → VPS IP (`rag` was a CNAME → `eta` until 2026-10-30) |
| Upstream | `localhost:8001` → container `rag-chatbot-prod` |
| Checkout | `/root/production-rag-system` (reset to `origin/main` by the deploy workflow) |
| Image | `ghcr.io/woolnerd/cited-doc-qa:latest` (also tagged `main-<sha>`) |
| Env | `/root/production-rag-system/.env.production` |
| GCS key | `/root/secrets/rag-demo-gcs-viewer.json` → `/run/secrets/rag-demo-gcs-viewer.json` (read-only) |
| Database | Postgres `rag_db` in container `n8n-postgres`, shared with the old eta container |
| Old eta app | Container `eta-rag-demo` on port 8002, **stopped**, `restart=no` |

Backups taken during the cutover (on the VPS):

- `/etc/caddy/Caddyfile.bak-20261029T193307Z-pre-rag-cutover`
- `/root/production-rag-system/.env.production.bak-20261029T175249Z-pre-eta-cutover`

> ⚠️ **Do not make `eta.getfreetime.ai` redirect to `rag.getfreetime.ai`.** Until the cutover,
> `rag` sent a *permanent* (301) redirect to `eta`, and browsers cache that. A reverse redirect
> causes a redirect loop for returning visitors. Both hostnames must serve the app directly.

> ⚠️ **Keep the `eta` DNS record and Caddy hostname.** Browsers that cached the old 301 still send
> `rag` visitors to `eta`, and `eta` is linked from getfreetime.ai/eta/, the landing page's
> `llms.txt`, and past proposals. Deleting `eta` breaks all of them.

### DNS change (2026-10-30)

`rag` changed from a CNAME pointing at `eta` to its own A record pointing at the VPS IP, so it no
longer depends on the `eta` record. Both answers end at the same IP, so this doesn't affect the
rollback options below. To undo it, in Namecheap → Advanced DNS replace the `rag` A record with
`CNAME rag → eta.getfreetime.ai.`, then check:

```bash
dig +short rag.getfreetime.ai @dns1.registrar-servers.com   # expect the VPS IP (A) or eta.getfreetime.ai. + IP (CNAME)
curl -s -o /dev/null -w "%{http_code}\n" https://rag.getfreetime.ai/   # expect 200
```

## Option 1: Roll Back to the Old eta Container (full cutover undo)

Use this if the new container is broken and a redeploy won't fix it quickly.

```bash
ssh root@your-vps-ip

# 1. Restart the old app
docker update --restart=always eta-rag-demo
docker start eta-rag-demo
curl -f http://localhost:8002/health

# 2. Restore the pre-cutover Caddyfile (rag → 301 → eta → :8002)
cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-$(date -u +%Y%m%dT%H%M%SZ)-pre-rollback
cp /etc/caddy/Caddyfile.bak-20261029T193307Z-pre-rag-cutover /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy

# 3. Verify
curl -sI https://rag.getfreetime.ai/ | head -3     # expect 301 → eta
curl -s  https://eta.getfreetime.ai/health
```

**Faster alternative:** if you'd rather leave the Caddyfile structure alone, edit only the upstream
in the combined block (`reverse_proxy localhost:8001` → `localhost:8002`), then validate and reload.

Both containers use the same database, so no data migration is needed in either direction.

## Option 2: Roll Back a Bad Deploy (stay on cited-doc-qa)

The deploy workflow has an automatic rollback job that runs only if the deploy fails. To roll back
manually to a known-good image:

```bash
ssh root@your-vps-ip
cd /root/production-rag-system

# List available images (newest first)
docker images ghcr.io/woolnerd/cited-doc-qa --format '{{.Tag}}  {{.CreatedAt}}'

# Pin a previous tag (e.g. main-3670d8a) and recreate
IMAGE_TAG=main-<sha> docker compose -f docker-compose.prod.yml up -d --remove-orphans
curl -f http://localhost:8001/health
```

The next push to `main` redeploys `latest`, so revert the bad commit on `main` (via PR) before then.

## Option 3: Restore the Previous Env

Only needed if a config change on 8001 is the problem. The pre-cutover env used Gemini embeddings,
which **do not match** the 3072-dim `openai/text-embedding-3-large` vectors of the global documents,
so restoring it will break search over them. Its `OPENROUTER_API_KEY` has also been revoked
(checked 2026-10-30), so copy the current key into it first. Prefer fixing the single bad value
instead.

```bash
cd /root/production-rag-system
cp .env.production .env.production.bak-$(date -u +%Y%m%dT%H%M%SZ)
cp .env.production.bak-20261029T175249Z-pre-eta-cutover .env.production
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

## Option 4: Restore the Vector Similarity Threshold

On 2026-10-30 at 11:54 UTC, `SEARCH_SIMILARITY_THRESHOLD` in `.env.production` changed from `0.45`
to `0.0`, matching the new code default from PR #91. With `0.45`, 6 of the 29 answerable eval
questions got no search results; see "What I measured and what I changed" in the README. This was
the only line changed. Backup:

- `/root/production-rag-system/.env.production.bak-20261030T115411Z-similarity-threshold`

To go back to `0.45`, set it explicitly. Removing the line does not restore the old behavior,
because the code default is now `0.0`.

```bash
cd /root/production-rag-system
cp .env.production .env.production.bak-$(date -u +%Y%m%dT%H%M%SZ)-pre-threshold-rollback
sed -i 's/^SEARCH_SIMILARITY_THRESHOLD=.*/SEARCH_SIMILARITY_THRESHOLD=0.45/' .env.production
docker compose -f docker-compose.prod.yml up -d --force-recreate

# Confirm the container loaded it
docker exec rag-chatbot-prod python -c \
  "from app.core.config import settings; print(settings.SEARCH_SIMILARITY_THRESHOLD)"
```

`docker compose restart` does not reread `env_file`; recreate the container as above.

### Unused env lines removed (2026-10-30, 12:14 UTC)

Right after the threshold change, seven lines the app never reads were removed from
`.env.production`: `DATABASE_URL`, `MAX_FILE_SIZE_MB`, `ALLOWED_FILE_TYPES`, `UPLOAD_RATE_LIMIT`,
`QUERY_RATE_LIMIT`, `CHUNK_SIZE_TARGET`, `GCS_SOURCE_PREFIX`. The app's defaults for the ones
defined in `config.py` are the same values. Backup:

- `/root/production-rag-system/.env.production.bak-20261030T121437Z-remove-unused-vars`

To undo, copy that backup over `.env.production` and recreate the container. It already contains
`SEARCH_SIMILARITY_THRESHOLD=0.0`, so this does not undo the threshold change.

The stale `/root/production-rag-system/.env` (a January 2026 copy of an older env, not used by
`docker-compose.prod.yml`) was deleted at the same time. It was not backed up: it only held older
credentials and settings that nothing reads.

## Option 5: Undo Migration 010 (full-text OR query)

On 2026-10-30 at about 16:51 UTC, `migrations/010_fulltext_or_query.sql` (PR #97) was applied by
hand to `rag_db` in the `n8n-postgres` container. It adds `fulltext_or_query(text)` and replaces
`search_chunks_fulltext_by_session` and `search_chunks_fulltext_by_document_and_session` so a
question matches chunks containing any of its words instead of all of them. No data changed, and
the app needed no restart. Schema backup taken just before:

- `/root/backups/rag_db-schema-20261030T165115Z-pre-010.sql`

To undo, re-run migration 006, then drop the helper. 006 was the last migration before 010 to
define these functions, so it restores the versions that ran before. It also redefines the two
non-session full-text functions, which the app doesn't call and 010 didn't touch. Run from a
checkout of this repo on your laptop:

```bash
ssh root@<vps> 'docker exec -i n8n-postgres psql -v ON_ERROR_STOP=1 --single-transaction -U rag_user -d rag_db' \
  < migrations/006_optimize_fulltext_search.sql
ssh root@<vps> "docker exec n8n-postgres psql -U rag_user -d rag_db -c 'DROP FUNCTION IF EXISTS fulltext_or_query(text);'"

# Verify: expect no rows, then "f"
ssh root@<vps> "docker exec n8n-postgres psql -U rag_user -d rag_db -tAc \
  \"SELECT proname FROM pg_proc WHERE proname='fulltext_or_query'; \
    SELECT position('fulltext_or_query' in pg_get_functiondef('search_chunks_fulltext_by_session'::regproc)) > 0;\""
```

The schema backup is a reference for what the functions looked like, not something to restore
wholesale: replaying a full schema dump over the live database would fail on existing objects.

Smoke test for 010 itself: "Is there an open-door policy for raising workplace concerns?" should
cite `small_business_handbook.pdf`. Before 010, full-text search returned nothing for it.

Gotcha: Postgres warns on every connection that `rag_db` has a collation version mismatch
(created with glibc 2.41, container now provides 2.36). It predates this change and doesn't
affect it.

## Option 6: Undo Migration 011 (full-text tiebreak)

`migrations/011_fulltext_tiebreak.sql` changes only the `ORDER BY` of the two session full-text
functions, so tied ranks come back by filename and chunk index instead of storage order. It
requires 010. No data changes and no app restart. Apply it the same way as 010, with a schema
backup first:

```bash
ssh root@<vps> 'docker exec n8n-postgres pg_dump -U rag_user -d rag_db --schema-only \
  > /root/backups/rag_db-schema-$(date -u +%Y%m%dT%H%M%SZ)-pre-011.sql'
ssh root@<vps> 'docker exec -i n8n-postgres psql -v ON_ERROR_STOP=1 --single-transaction -U rag_user -d rag_db' \
  < migrations/011_fulltext_tiebreak.sql

# Verify: expect "t"
ssh root@<vps> "docker exec n8n-postgres psql -U rag_user -d rag_db -tAc \
  \"SELECT position('c.chunk_index, c.id' in pg_get_functiondef('search_chunks_fulltext_by_session'::regproc)) > 0;\""
```

Applied to production about 18:37 UTC on 2026-10-30. Schema backup taken first:
`/root/backups/rag_db-schema-20261030T183646Z-pre-011.sql`.

To undo, re-run `migrations/010_fulltext_or_query.sql` (verification then prints "f"), then run
the smoke test below.

## Smoke Test After Any Rollback

```bash
# Health on both hostnames
curl -s https://rag.getfreetime.ai/health
curl -s https://eta.getfreetime.ai/health

# A query against the global documents should return a cited answer
curl -s -X POST https://rag.getfreetime.ai/api/query \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"rollback-check-'"$(date +%s)"'","query":"What is the HVAC maintenance schedule?"}' \
  | python3 -m json.tool | head -20
```

Expect an answer citing `HVAC-maintenance.pdf`. Asking the same question twice within 30 seconds
returns a 429 from the demo limiter; that is expected.

## Cleanup (once rollback is no longer needed)

After the new setup has run cleanly for a while, the old eta container (`eta-rag-demo`, plus an
older `eta-rag-demo-old`) and `/root/eta-rag-demo` can be removed. Removing them makes Option 1
impossible, so update this doc when that happens.
