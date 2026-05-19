-- Migration 008: Add public demo usage tracking
-- Description: Store minimal, privacy-conscious usage events for DEMO_MODE limits.

CREATE TABLE IF NOT EXISTS demo_usage_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id varchar(255),
    hashed_ip char(64),
    route varchar(100) NOT NULL,
    event_type varchar(50) NOT NULL,
    limit_type varchar(80),
    request_bytes bigint,
    query_hash char(64),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT demo_usage_events_type_check CHECK (
        event_type IN ('query', 'upload', 'limit_exceeded')
    )
);

CREATE INDEX IF NOT EXISTS idx_demo_usage_events_session_type_created
    ON demo_usage_events (session_id, event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_demo_usage_events_ip_type_created
    ON demo_usage_events (hashed_ip, event_type, created_at DESC)
    WHERE hashed_ip IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_demo_usage_events_type_created
    ON demo_usage_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_demo_usage_events_duplicate_query
    ON demo_usage_events (session_id, query_hash, created_at DESC)
    WHERE query_hash IS NOT NULL;

DO $$
BEGIN
  RAISE NOTICE 'Migration 008_add_demo_usage_events.sql completed successfully!';
  RAISE NOTICE 'Created demo_usage_events for privacy-conscious public demo limits.';
END $$;
