CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  TEXT NOT NULL DEFAULT 'system'
);

-- Rows added by hand from the dashboard's Database screen. The flag is what
-- keeps prune_unknown from dropping a key the registry never declared.
ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS is_custom BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS setting_changes (
    id          BIGSERIAL PRIMARY KEY,
    key         TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_by  TEXT NOT NULL DEFAULT 'system',
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS setting_changes_changed_at_idx
    ON setting_changes (changed_at DESC);

CREATE TABLE IF NOT EXISTS dashboard_users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'operator',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS invited_by TEXT;
ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Seeded from src/auth/permissions.py at boot. A user's role is a name here;
-- one that no longer exists reads as 'viewer' rather than locking them out.
CREATE TABLE IF NOT EXISTS roles (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_system   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS call_records (
    id                BIGSERIAL PRIMARY KEY,
    channel           TEXT NOT NULL,
    phone_no          TEXT NOT NULL,
    reference_id      TEXT NOT NULL DEFAULT '',
    customer_name     TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'requested',
    triggered_by      TEXT NOT NULL DEFAULT 'dashboard',
    provider_call_id  TEXT NOT NULL DEFAULT '',
    provider_response JSONB,
    error             TEXT,
    cart              JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at          TIMESTAMPTZ,
    duration_secs     DOUBLE PRECISION,
    transcript_turns  INTEGER NOT NULL DEFAULT 0,
    ended_reason      TEXT
);

-- What History shows about a finished call: per-turn latency, the providers
-- it ran on, tokens and cost; and a summary written on first view.
ALTER TABLE call_records ADD COLUMN IF NOT EXISTS metrics JSONB;
ALTER TABLE call_records ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE call_records ADD COLUMN IF NOT EXISTS summary_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS call_records_created_at_idx
    ON call_records (created_at DESC);
CREATE INDEX IF NOT EXISTS call_records_reference_idx
    ON call_records (reference_id);

-- Every record the ingestion API received, valid or not, and what became of
-- its call. A rejected record is kept so the dashboard can show why it was
-- not dialled.
-- QMS intakes: each upstream API that asks for calls, the agent it calls and
-- the fields its records carry. The fields drive validation, the API docs,
-- the test forms and what the agent is told about the call.
CREATE TABLE IF NOT EXISTS qms_intakes (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    agent               TEXT NOT NULL,
    channel             TEXT NOT NULL DEFAULT 'acefone',
    kind                TEXT NOT NULL DEFAULT 'custom',
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    fields              JSONB NOT NULL DEFAULT '[]'::jsonb,
    token_hash          TEXT NOT NULL DEFAULT '',
    token_hint          TEXT NOT NULL DEFAULT '',
    delay_secs          DOUBLE PRECISION,
    dedupe_window_secs  DOUBLE PRECISION,
    builtin             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by          TEXT NOT NULL DEFAULT ''
);

-- Self-service password resets: a one-time link, stored as a hash. The
-- current password keeps working until the link is actually used.
CREATE TABLE IF NOT EXISTS password_resets (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    token_hash  TEXT NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The emailed second sign-in step. Codes are stored as an HMAC, never in the clear.
CREATE TABLE IF NOT EXISTS login_challenges (
    id          TEXT PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    code_hash   TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    resends     INTEGER NOT NULL DEFAULT 0,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A teammate asking for a permission their role does not have. Admins grant
-- it by changing the role (or the person's role) and mark the request done.
CREATE TABLE IF NOT EXISTS access_requests (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    email        TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT '',
    permission   TEXT NOT NULL,
    page         TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    resolved_by  TEXT NOT NULL DEFAULT '',
    resolved_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS access_requests_pending_idx ON access_requests (status, created_at);

CREATE TABLE IF NOT EXISTS ingestion_events (
    id               BIGSERIAL PRIMARY KEY,
    received_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_ip        TEXT NOT NULL DEFAULT '',
    reference_id     TEXT NOT NULL DEFAULT '',
    phone_no         TEXT NOT NULL DEFAULT '',
    customer_name    TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL,
    reason           TEXT NOT NULL DEFAULT '',
    errors           JSONB NOT NULL DEFAULT '[]'::jsonb,
    payload          JSONB,
    channel          TEXT NOT NULL DEFAULT '',
    scheduled_for    TIMESTAMPTZ,
    triggered_at     TIMESTAMPTZ,
    call_record_id   BIGINT,
    provider_call_id TEXT NOT NULL DEFAULT '',
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ingestion_events_received_idx
    ON ingestion_events (received_at DESC);
CREATE INDEX IF NOT EXISTS ingestion_events_status_idx
    ON ingestion_events (status);
CREATE INDEX IF NOT EXISTS ingestion_events_reference_idx
    ON ingestion_events (reference_id);
CREATE INDEX IF NOT EXISTS ingestion_events_phone_idx
    ON ingestion_events (phone_no);

-- Which agent a record dials and which intake (QMS source) sent it.
ALTER TABLE ingestion_events ADD COLUMN IF NOT EXISTS agent TEXT NOT NULL DEFAULT '';
ALTER TABLE ingestion_events ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT '';
ALTER TABLE ingestion_events ADD COLUMN IF NOT EXISTS intake TEXT NOT NULL DEFAULT '';
-- When an intake may ring: IST hours (HH:MM). Both empty rings at any hour.
ALTER TABLE qms_intakes ADD COLUMN IF NOT EXISTS call_hours_start TEXT NOT NULL DEFAULT '';
ALTER TABLE qms_intakes ADD COLUMN IF NOT EXISTS call_hours_end TEXT NOT NULL DEFAULT '';
-- An intake may exist before any agent is connected to it.
ALTER TABLE qms_intakes ALTER COLUMN agent SET DEFAULT '';
-- Held records received at or after this are called once the agent is live.
-- NULL: none are released automatically.
ALTER TABLE qms_intakes ADD COLUMN IF NOT EXISTS release_after TIMESTAMPTZ;
UPDATE ingestion_events
   SET source = CASE WHEN source_ip LIKE 'dashboard:%' OR source_ip LIKE 'retry:%' THEN 'phone_test' ELSE 'abandoned_cart' END
 WHERE source = '';
UPDATE ingestion_events SET agent = payload->>'use_case'
 WHERE agent = '' AND jsonb_typeof(payload) = 'object' AND coalesce(payload->>'use_case', '') <> '';
CREATE INDEX IF NOT EXISTS ingestion_events_agent_idx ON ingestion_events (agent);
CREATE INDEX IF NOT EXISTS ingestion_events_source_idx ON ingestion_events (source);

CREATE TABLE IF NOT EXISTS call_sessions (
    id                   BIGSERIAL PRIMARY KEY,
    ref_id               TEXT NOT NULL DEFAULT '',
    original_call_id     TEXT NOT NULL DEFAULT '',
    current_call_id      TEXT NOT NULL DEFAULT '',
    original_uuid        TEXT NOT NULL DEFAULT '',
    current_uuid         TEXT NOT NULL DEFAULT '',
    leg_history          JSONB NOT NULL DEFAULT '[]'::jsonb,
    channel              TEXT NOT NULL DEFAULT 'acefone',
    direction            TEXT NOT NULL DEFAULT '',
    customer_number      TEXT NOT NULL DEFAULT '',
    customer_name        TEXT NOT NULL DEFAULT '',
    booking_reference_id TEXT NOT NULL DEFAULT '',
    did                  TEXT NOT NULL DEFAULT '',
    agent_number         TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'INITIATED',
    status_rank          INTEGER NOT NULL DEFAULT 10,
    ended_reason         TEXT NOT NULL DEFAULT '',
    recording_url        TEXT NOT NULL DEFAULT '',
    duration_secs        DOUBLE PRECISION,
    call_record_id       BIGINT,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at          TIMESTAMPTZ,
    transferred_at       TIMESTAMPTZ,
    agent_answered_at    TIMESTAMPTZ,
    ended_at             TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS call_sessions_ref_idx
    ON call_sessions (ref_id);
CREATE INDEX IF NOT EXISTS call_sessions_current_call_idx
    ON call_sessions (current_call_id);
CREATE INDEX IF NOT EXISTS call_sessions_original_call_idx
    ON call_sessions (original_call_id);
CREATE INDEX IF NOT EXISTS call_sessions_live_idx
    ON call_sessions (status_rank, started_at DESC);
CREATE INDEX IF NOT EXISTS call_sessions_did_idx
    ON call_sessions (did);

CREATE TABLE IF NOT EXISTS call_events (
    id          BIGSERIAL PRIMARY KEY,
    session_id  BIGINT,
    event_key   TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,
    ref_id      TEXT NOT NULL DEFAULT '',
    call_id     TEXT NOT NULL DEFAULT '',
    call_uuid   TEXT NOT NULL DEFAULT '',
    payload     JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS call_events_session_idx
    ON call_events (session_id, received_at DESC);

-- One conversation per call, not one row per utterance. The old table wrote a
-- row per line with nothing enforcing the link back to the call, so reading a
-- call meant stitching rows together and an orphaned row could outlive the
-- session it described.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'call_transcripts' AND column_name = 'role'
    ) THEN
        ALTER TABLE call_transcripts RENAME TO call_transcripts_legacy;
        ALTER INDEX IF EXISTS call_transcripts_session_idx
            RENAME TO call_transcripts_legacy_session_idx;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS call_transcripts (
    id             BIGSERIAL PRIMARY KEY,
    session_id     BIGINT NOT NULL UNIQUE
                   REFERENCES call_sessions (id) ON DELETE CASCADE,
    call_record_id BIGINT REFERENCES call_records (id) ON DELETE SET NULL,
    messages       JSONB NOT NULL DEFAULT '[]'::jsonb,
    turns          INTEGER NOT NULL DEFAULT 0,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS call_transcripts_record_idx
    ON call_transcripts (call_record_id);

-- Carry the old rows over, one conversation per session. A row whose session is
-- already gone cannot come across — the foreign key is the point — so it stays
-- in call_transcripts_legacy rather than being thrown away.
--
-- Only databases that predate the rename above have a legacy table. The copy is
-- EXECUTEd so a fresh database never parses a reference to a table it has no
-- reason to have — an unconditional statement here would fail at parse time and
-- take the whole schema batch down with it.
DO $$
BEGIN
    IF to_regclass('call_transcripts_legacy') IS NOT NULL THEN
        EXECUTE $mig$
            INSERT INTO call_transcripts (session_id, messages, turns, started_at, updated_at)
            SELECT
                l.session_id,
                jsonb_agg(
                    jsonb_build_object(
                        'turn', l.turn,
                        'role', l.role,
                        'text', l.text,
                        'spoken', l.spoken,
                        'at', to_char(l.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
                    )
                    ORDER BY l.turn, l.id
                ),
                max(l.turn),
                min(l.created_at),
                max(l.created_at)
            FROM call_transcripts_legacy l
            JOIN call_sessions s ON s.id = l.session_id
            GROUP BY l.session_id
            ON CONFLICT (session_id) DO NOTHING
        $mig$;
    END IF;
END $$;

-- An empty list reads as "no legs yet"; a null reads as a bug in whoever wrote
-- the row. Existing rows are brought up to the new default.
UPDATE call_sessions SET leg_history = '[]'::jsonb WHERE leg_history IS NULL;

ALTER TABLE call_sessions ALTER COLUMN leg_history SET DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'call_sessions' AND column_name = 'leg_history'
          AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE call_sessions ALTER COLUMN leg_history SET NOT NULL;
    END IF;
END $$;

-- The dial attempt and the call it produced belong on one row. Clear whatever
-- points nowhere, then make the link enforceable.
UPDATE call_sessions s
   SET call_record_id = NULL
 WHERE s.call_record_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM call_records r WHERE r.id = s.call_record_id);

DELETE FROM call_events e
 WHERE e.session_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM call_sessions s WHERE s.id = e.session_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'call_sessions_record_fk'
    ) THEN
        ALTER TABLE call_sessions
            ADD CONSTRAINT call_sessions_record_fk
            FOREIGN KEY (call_record_id) REFERENCES call_records (id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'call_events_session_fk'
    ) THEN
        ALTER TABLE call_events
            ADD CONSTRAINT call_events_session_fk
            FOREIGN KEY (session_id) REFERENCES call_sessions (id) ON DELETE CASCADE;
    END IF;
END $$;

-- Everything about one call on one row, for whoever opens psql rather than the
-- dashboard: who was called, how it was triggered, how it ended, what was said.
CREATE OR REPLACE VIEW call_overview AS
SELECT
    s.id                AS session_id,
    s.ref_id,
    s.channel,
    s.direction,
    s.customer_number,
    s.customer_name,
    s.booking_reference_id,
    s.did,
    s.agent_number,
    s.status,
    s.ended_reason,
    s.recording_url,
    s.duration_secs,
    s.started_at,
    s.answered_at,
    s.transferred_at,
    s.ended_at,
    r.id                AS call_record_id,
    r.triggered_by,
    r.status            AS dial_status,
    r.provider_call_id,
    r.error             AS dial_error,
    r.cart,
    t.turns             AS transcript_turns,
    t.messages          AS transcript
FROM call_sessions s
LEFT JOIN call_records r ON r.id = s.call_record_id
LEFT JOIN call_transcripts t ON t.session_id = s.id;

CREATE TABLE IF NOT EXISTS organizations (
    id          SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL UNIQUE,
    agents      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_by  TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL;
