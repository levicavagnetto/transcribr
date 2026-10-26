-- Speaker labels are gone (add-call-attribution D0): no per-line speaker, no per-call speakers.
-- Each line of 1 second or more gets its own voiceprint instead (D1): an L2-normalized float32
-- vector, never returned by the API. Lines transcribed before this migration have none.
DROP TABLE speakers;
ALTER TABLE segments DROP COLUMN speaker;
ALTER TABLE segments ADD COLUMN voiceprint BLOB;
