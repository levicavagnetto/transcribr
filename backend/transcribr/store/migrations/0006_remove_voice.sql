-- Voice matching is removed (add-call-attribution design D3): it could not tell the shop's
-- service writers apart on 8 kHz phone audio. No voice data is kept. Attribution is by the
-- name heard in the opening (always Maybe) and by hand.
DROP TABLE voice_samples;
ALTER TABLE segments DROP COLUMN voiceprint;
DELETE FROM settings WHERE key IN ('voice_threshold_low', 'voice_threshold_high');

-- Rebuilt without voice_score and the voice methods. Automatic rows are dropped and a rematch
-- is queued, so every call is re-attributed by name; manual rows are kept as they were.
CREATE TABLE attributions_new (
    call_id      INTEGER NOT NULL REFERENCES calls (id) ON DELETE CASCADE,
    profile_id   INTEGER NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    status       TEXT NOT NULL CHECK (status IN ('confident', 'maybe', 'rejected')),
    source       TEXT NOT NULL CHECK (source IN ('auto', 'manual')),
    method       TEXT NOT NULL CHECK (method IN ('name', 'manual')),
    name_heard   TEXT,              -- the transcript words that matched a name variant
    name_at_s    REAL,              -- when they were said, seconds into the recording
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (call_id, profile_id)
);
INSERT INTO attributions_new
    (call_id, profile_id, status, source, method, name_heard, name_at_s, updated_at)
SELECT call_id, profile_id, status, source, 'manual', name_heard, name_at_s, updated_at
FROM attributions WHERE source = 'manual';
DROP TABLE attributions;
ALTER TABLE attributions_new RENAME TO attributions;
CREATE INDEX attributions_by_profile ON attributions (profile_id, status);

INSERT INTO jobs (type, call_id, created_at)
SELECT 'rematch', NULL, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE EXISTS (SELECT 1 FROM profiles)
    AND NOT EXISTS (SELECT 1 FROM jobs WHERE type = 'rematch' AND claimed_at IS NULL);
