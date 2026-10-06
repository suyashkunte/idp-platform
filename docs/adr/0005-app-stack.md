# 0005. StudyTimer application stack

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Decision
Python 3.12, FastAPI, Jinja2 + HTMX (server-rendered, no JS toolchain), SQLAlchemy 2 + Alembic, PostgreSQL, Pydantic v2, argon2 for passwords, OpenTelemetry + prometheus-client, uv workspace, ruff, mypy strict, pytest (+ xdist, testcontainers, Playwright for E2E, Locust for perf, Schemathesis for OpenAPI).
## Rationale
One language end to end (design doc §5); HTMX keeps the UI testable with Playwright without a separate front-end build or service.
