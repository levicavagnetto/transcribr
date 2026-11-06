-- When a call last failed, for the "failed in the last 24 hours" status figure.
ALTER TABLE calls ADD COLUMN failed_at TEXT;
