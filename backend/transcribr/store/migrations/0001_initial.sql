-- Core schema. Times are ISO 8601 UTC text ("2026-10-22T15:42:00Z") unless named *_local.

-- Every call listed from Ravon. id is Ravon's recording ID.
CREATE TABLE calls (
    id              INTEGER PRIMARY KEY,
    queue           TEXT NOT NULL,
    start_local     TEXT NOT NULL,          -- as Ravon shows it, store time zone
    start_utc       TEXT NOT NULL,
    minutes         REAL NOT NULL,
    caller_number   TEXT NOT NULL,
    answered_by     TEXT NOT NULL,
    listed_at       TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'not_transcribed'
                    CHECK (state IN ('not_transcribed', 'waiting', 'processing', 'transcribed', 'failed')),
    auto_queued     INTEGER NOT NULL DEFAULT 0 CHECK (auto_queued IN (0, 1)),
    failure_reason  TEXT
);
CREATE INDEX calls_by_start ON calls (start_utc DESC, id DESC);
CREATE INDEX calls_by_state ON calls (state);

-- Pending work. One row per (type, call); later changes add job types.
CREATE TABLE jobs (
    id          INTEGER PRIMARY KEY,
    type        TEXT NOT NULL,
    call_id     INTEGER REFERENCES calls (id) ON DELETE CASCADE,
    attempts    INTEGER NOT NULL DEFAULT 0,
    not_before  TEXT,
    claimed_at  TEXT,
    last_error  TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (type, call_id)
);
CREATE INDEX jobs_ready ON jobs (claimed_at, not_before, id);

CREATE TABLE transcripts (
    call_id         INTEGER PRIMARY KEY REFERENCES calls (id) ON DELETE CASCADE,
    language        TEXT NOT NULL,
    model           TEXT NOT NULL,
    transcribed_at  TEXT NOT NULL,
    no_speech       INTEGER NOT NULL DEFAULT 0 CHECK (no_speech IN (0, 1))
);

-- One row per transcript line. words is a JSON array of [start_s, end_s, word].
CREATE TABLE segments (
    id       INTEGER PRIMARY KEY,
    call_id  INTEGER NOT NULL REFERENCES transcripts (call_id) ON DELETE CASCADE,
    idx      INTEGER NOT NULL,
    start_s  REAL NOT NULL,
    end_s    REAL NOT NULL,
    speaker  TEXT NOT NULL,
    text     TEXT NOT NULL,
    words    TEXT NOT NULL DEFAULT '[]',
    UNIQUE (call_id, idx)
);
CREATE INDEX segments_by_call ON segments (call_id, idx);

-- Full-text search over segments, kept in sync by triggers.
CREATE VIRTUAL TABLE segments_fts USING fts5 (
    text,
    content = 'segments',
    content_rowid = 'id',
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts (rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts (segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER segments_au AFTER UPDATE OF text ON segments BEGIN
    INSERT INTO segments_fts (segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO segments_fts (rowid, text) VALUES (new.id, new.text);
END;

-- One row per speaker label in a call. fingerprint is a float32 vector; never returned by the API.
CREATE TABLE speakers (
    call_id         INTEGER NOT NULL REFERENCES calls (id) ON DELETE CASCADE,
    label           TEXT NOT NULL,
    speech_seconds  REAL NOT NULL,
    fingerprint     BLOB,
    PRIMARY KEY (call_id, label)
);

-- Instance settings, one JSON value per key.
CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Periods when the worker was running (from heartbeats).
CREATE TABLE uptime_spans (
    id            INTEGER PRIMARY KEY,
    started_at    TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

-- Small runtime facts shared between services (Ravon state, last poll, counters), as JSON.
CREATE TABLE service_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE admin (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    username             TEXT NOT NULL,
    password_hash        TEXT NOT NULL,
    password_changed_at  TEXT NOT NULL
);

-- id_hash is the SHA-256 of the session token; the token itself is never stored.
CREATE TABLE admin_sessions (
    id_hash     TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX admin_sessions_by_expiry ON admin_sessions (expires_at);

CREATE TABLE admin_setup_code (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    code_hash   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
