---
name: lint-fix
description: Fix lint, format and type-check failures reported by `make lint` without suppressing rules. Use when make lint or make verify fails on style or types.
---

# Lint and type fixes

Loop at most 3 times: run `make lint`, fix the reported issues in the code, re-run.
Never add `noqa`, `type: ignore`, `# pragma: no cover`, per-file ignores or config changes to silence a finding. If a
finding looks wrong, leave it and report it with the reason.
