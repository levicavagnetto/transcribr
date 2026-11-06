-- The caller number's digits only, for number search: "555-0142" finds "(405) 555-0142".
-- digits_only() is registered on every connection (transcribr/store/db.py).
ALTER TABLE calls ADD COLUMN caller_digits TEXT NOT NULL DEFAULT '';
UPDATE calls SET caller_digits = digits_only(caller_number);
