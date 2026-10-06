---
name: gen-tests
description: Test-first step - generate failing tests for every acceptance criterion via the unit-test-generator and e2e-test-generator subagents, then validate them. Use after the spec is approved (or in auto mode) and before implementation.
---

# Generate failing tests (design doc §21.7 step 5, §11.3)

1. Delegate to `unit-test-generator` with `specs/<KEY>/spec.md` and `tasks.md`.
2. If an AC needs proof through a running service (API, integration, end-to-end), also delegate to `e2e-test-generator`.
3. Validate deterministically before accepting:
   - `uv run idp test-quality-lint <new test files>` (or `idp test-quality-lint`) reports nothing;
   - every AC id has ≥ 1 test: `make spec-trace KEY=<KEY>` lists no MISSING and no UNKNOWN;
   - the new tests fail now, for the expected reason (missing behaviour, not ImportError or SyntaxError). Run them and
     read the failure messages;
   - repeat the run 3 times: the failures are the same each time (determinism);
   - `git diff --name-only` shows only test files and fixtures.
4. If a check fails, send the specific failure back to the generator (max 2 rounds), then stop and report.
