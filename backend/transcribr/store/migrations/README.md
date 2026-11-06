Numbered schema migrations: `0001_initial.sql`, `0002_...sql`, with no gaps.

- The runner (`transcribr/store/migrate.py`) wraps each file in one transaction together with its
  `PRAGMA user_version` bump, so a file must not contain its own `BEGIN`, `COMMIT` or `ROLLBACK`.
- Never edit a migration that has shipped; add a new one.
- An existing database is backed up to `backups/pre-migration-v<N>-<time>.db` before upgrading.
