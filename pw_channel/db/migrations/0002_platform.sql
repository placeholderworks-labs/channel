CREATE TABLE IF NOT EXISTS records (
    id           BIGSERIAL PRIMARY KEY,
    reference_id TEXT NOT NULL UNIQUE,
    intake       TEXT NOT NULL DEFAULT '',
    agent        TEXT NOT NULL DEFAULT '',
    lead_key     TEXT NOT NULL DEFAULT '',
    phone        TEXT NOT NULL DEFAULT '',
    email        TEXT NOT NULL DEFAULT '',
    canonical    JSONB NOT NULL,
    journey_id   BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS records_lead_key ON records (lead_key);
CREATE INDEX IF NOT EXISTS records_phone_last10 ON records (right(phone, 10));

CREATE TABLE IF NOT EXISTS journeys (
    id               BIGSERIAL PRIMARY KEY,
    lead_key         TEXT NOT NULL,
    reference_id     TEXT NOT NULL,
    intake           TEXT NOT NULL DEFAULT '',
    template         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active',
    stop_reason      TEXT NOT NULL DEFAULT '',
    paused_until     TIMESTAMPTZ,
    expires_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS journeys_one_active_per_lead
    ON journeys (lead_key, template) WHERE status IN ('active', 'paused');
CREATE INDEX IF NOT EXISTS journeys_reference ON journeys (reference_id);

CREATE TABLE IF NOT EXISTS journey_tasks (
    id                   BIGSERIAL PRIMARY KEY,
    journey_id           BIGINT NOT NULL REFERENCES journeys(id) ON DELETE CASCADE,
    key                  TEXT NOT NULL,
    channel              TEXT NOT NULL,
    action               TEXT NOT NULL,
    params               JSONB NOT NULL DEFAULT '{}'::jsonb,
    join_mode            TEXT NOT NULL DEFAULT 'all',
    delay_secs           DOUBLE PRECISION NOT NULL DEFAULT 0,
    response_window_secs DOUBLE PRECISION NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'blocked',
    outcome              TEXT,
    provider_ref         TEXT,
    run_at               TIMESTAMPTZ,
    window_ends_at       TIMESTAMPTZ,
    attempts             INTEGER NOT NULL DEFAULT 0,
    max_attempts         INTEGER NOT NULL DEFAULT 1,
    retry_delay_secs     DOUBLE PRECISION NOT NULL DEFAULT 900,
    locked_by            TEXT,
    lease_until          TIMESTAMPTZ,
    result               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (journey_id, key)
);
CREATE INDEX IF NOT EXISTS journey_tasks_due ON journey_tasks (run_at) WHERE status = 'ready';
CREATE INDEX IF NOT EXISTS journey_tasks_waiting ON journey_tasks (window_ends_at) WHERE status = 'waiting';
CREATE INDEX IF NOT EXISTS journey_tasks_running ON journey_tasks (lease_until) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS journey_tasks_provider_ref ON journey_tasks (provider_ref);

CREATE TABLE IF NOT EXISTS task_deps (
    task_id            BIGINT NOT NULL REFERENCES journey_tasks(id) ON DELETE CASCADE,
    depends_on_task_id BIGINT NOT NULL REFERENCES journey_tasks(id) ON DELETE CASCADE,
    when_outcomes      TEXT[] NOT NULL,
    PRIMARY KEY (task_id, depends_on_task_id)
);
CREATE INDEX IF NOT EXISTS task_deps_parent ON task_deps (depends_on_task_id);

CREATE TABLE IF NOT EXISTS journey_events (
    id           BIGSERIAL PRIMARY KEY,
    journey_id   BIGINT REFERENCES journeys(id) ON DELETE CASCADE,
    lead_key     TEXT NOT NULL DEFAULT '',
    reference_id TEXT NOT NULL DEFAULT '',
    kind         TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT '',
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    dedupe_key   TEXT UNIQUE,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    result       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS journey_events_pending ON journey_events (received_at) WHERE processed_at IS NULL;

CREATE TABLE IF NOT EXISTS outcome_events (
    id           BIGSERIAL PRIMARY KEY,
    event_id     TEXT NOT NULL UNIQUE,
    reference_id TEXT NOT NULL,
    kind         TEXT NOT NULL,
    intake       TEXT NOT NULL DEFAULT '',
    canonical    JSONB NOT NULL,
    raw          JSONB,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outcome_events_reference ON outcome_events (reference_id);

ALTER TABLE ingestion_events ADD COLUMN IF NOT EXISTS canonical JSONB;
ALTER TABLE ingestion_events ADD COLUMN IF NOT EXISTS adapter TEXT NOT NULL DEFAULT '';
ALTER TABLE ingestion_events ADD COLUMN IF NOT EXISTS adapter_version TEXT NOT NULL DEFAULT '';
ALTER TABLE ingestion_events ADD COLUMN IF NOT EXISTS schema_version TEXT NOT NULL DEFAULT '';
ALTER TABLE ingestion_events ADD COLUMN IF NOT EXISTS journey_id BIGINT;

ALTER TABLE qms_intakes ADD COLUMN IF NOT EXISTS adapter TEXT NOT NULL DEFAULT 'builtin.fields';
ALTER TABLE qms_intakes ADD COLUMN IF NOT EXISTS adapter_config JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE qms_intakes ADD COLUMN IF NOT EXISTS journey TEXT NOT NULL DEFAULT '';

ALTER TABLE call_sessions ADD COLUMN IF NOT EXISTS task_id BIGINT;


CREATE TABLE IF NOT EXISTS message_log (
    id           BIGSERIAL PRIMARY KEY,
    channel      TEXT NOT NULL,
    provider     TEXT NOT NULL,
    direction    TEXT NOT NULL,
    address      TEXT NOT NULL,
    provider_ref TEXT,
    task_id      BIGINT,
    body         JSONB NOT NULL DEFAULT '{}'::jsonb,
    status       TEXT NOT NULL DEFAULT 'sent',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS message_log_address ON message_log (channel, address, created_at DESC);
CREATE INDEX IF NOT EXISTS message_log_ref ON message_log (provider_ref);

CREATE TABLE IF NOT EXISTS contact_blocks (
    lead_key   TEXT NOT NULL,
    channel    TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (lead_key, channel)
);
