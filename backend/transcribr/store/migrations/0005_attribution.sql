-- People profiles and call attribution (add-call-attribution D1). Attribution is per call; it
-- never says which person spoke which line.

-- A profile's voice (its centroid) is computed from its voice samples whenever it is needed,
-- so it can never fall out of step with them; it is not stored.
CREATE TABLE profiles (
    id            INTEGER PRIMARY KEY,
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

-- Spellings and nicknames the transcript might contain. normalized is lowercase, without
-- punctuation or accents, and is what name matching compares.
CREATE TABLE name_variants (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    variant     TEXT NOT NULL,
    normalized  TEXT NOT NULL,
    UNIQUE (profile_id, normalized)
);

-- Transcript lines the admin enrolled for a person's voice. The voiceprint stays on the
-- segment, so a re-transcribed or deleted call takes its samples with it.
CREATE TABLE voice_samples (
    profile_id  INTEGER NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    call_id     INTEGER NOT NULL,
    idx         INTEGER NOT NULL,
    added_at    TEXT NOT NULL,
    PRIMARY KEY (profile_id, call_id, idx),
    FOREIGN KEY (call_id, idx) REFERENCES segments (call_id, idx) ON DELETE CASCADE
);
CREATE INDEX voice_samples_by_segment ON voice_samples (call_id, idx);

-- One row per (call, person). A manual 'rejected' row keeps automatic matching off that pair.
CREATE TABLE attributions (
    call_id      INTEGER NOT NULL REFERENCES calls (id) ON DELETE CASCADE,
    profile_id   INTEGER NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    status       TEXT NOT NULL CHECK (status IN ('confident', 'maybe', 'rejected')),
    source       TEXT NOT NULL CHECK (source IN ('auto', 'manual')),
    method       TEXT NOT NULL CHECK (method IN ('name', 'voice', 'name+voice', 'manual')),
    name_heard   TEXT,              -- the transcript words that matched a name variant
    name_at_s    REAL,              -- when they were said, seconds into the recording
    voice_score  REAL,              -- the call's voice presence score for this person
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (call_id, profile_id)
);
CREATE INDEX attributions_by_profile ON attributions (profile_id, status);
