---
name: spec-drift-check
description: Detect drift between specs, tests and code - ACs without tests, tests citing unknown ACs, approved specs edited after approval. Use on request or in scheduled/CI runs.
---

# Spec drift check

For each folder in `specs/` (or only `<KEY>` if given):
1. `make spec-trace KEY=<KEY>`: report MISSING and UNKNOWN entries.
2. If an `APPROVED` marker exists, compare its `spec_sha256` with the current `spec.md` hash; report "edited after approval".
Output a table: ticket, ACs, missing, unknown, approval state. Read-only: change nothing.
