# Change notes: add-call-transcription-core

Results from steps that run against the real Ravon site, as the tasks ask. Counts only; no
caller numbers or call content.

## 3.7 `transcribr ravon-check` against admin.ravon.net (2026-10-22)

- **Login:** works with the plain form POST through the allow list.
- **Queues:** Ravon lists 9 queues: `tireProz-hudsales` (Hudson Sales/CS x700), `tireProz-salescustserv` (Stillwater Sales/CS x600), `tireProz-accounting` (x500), `tireProz-AndysQueue` (x550), `tireProz-Hudson_AfterHOURS` (x701), `tireProz-internetsales` (x400), `tireProz-salesqone` (x200), `tireProz-salesqtwo` (x300), `tireProz-SWafterHRS` (x599).
- **Parser check against a known day:** `tireProz-salescustserv` on 2026-10-09 returned **79 calls**, the same count v1 measured for that day. That confirms the DataTable parsing on the real page.
- **2026-10-21:** 128 calls in total (Hudson 76, Stillwater 52, the other queues 0).
- **Search speed:** each one-day search took 1.1–1.7 s.
- **Finding:** the user's first run hit a one-off `ReadTimeout` on the first search, beyond the 20-second limit, and the check stopped without counting any queue. A rerun showed no queue is consistently slow. Two changes followed:
  1. The client now allows 10 s to connect and 60 s for Ravon to answer. Persistent slowness still trips the 5-failure backoff.
  2. `ravon-check` reports each queue's failure and carries on, exiting 1 if any queue failed.
- **Tooling note:** on Windows, uv 0.13's `--env-file` drops backslashes from the path (`..\.env` becomes `...env`). Use forward slashes: `uv run --env-file ../.env transcribr ravon-check`.
