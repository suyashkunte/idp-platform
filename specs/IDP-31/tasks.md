# IDP-31: tasks

All tasks are agent tasks. None touches a protected path (`.claude/idp-protected-paths.txt`: root `Makefile`,
root `pyproject.toml`, `infra/**`, plugin hooks, `.claude-plugin/**`, `.pre-commit-config.yaml`, plus the built-in
defaults `.git/**`, `.github/**`, `.claude/settings.json`, `specs/*/APPROVED`), so there is no human task.
Test names and exact expectations are in plan.md (step 1).

- [ ] T1 Doc-structure tests (red).
  - Add `tests/docs/__init__.py` and `tests/docs/test_adr_0013.py` with the four tests from plan.md, tagged
    `@pytest.mark.ac("IDP-31:AC-1")` (two tests), `IDP-31:AC-2` and `IDP-31:AC-3`.
  - Run `uv run pytest tests/docs --no-cov`: all four fail for the expected reason (ADR file missing; no link in the
    residual-risk texts). Run `uv run ruff check tests/docs` and `uv run idp test-quality-lint tests/docs/test_adr_0013.py`.
  - (AC-1, AC-2, AC-3) Files: tests/docs/__init__.py, tests/docs/test_adr_0013.py.
- [ ] T2 ADR-0013.
  - Write `docs/adr/0013-conformance-trust-model.md` from the template and the plan.md outline (status Accepted,
    date 2026-10-20). Do not mention IDP-32.
  - Check by hand that every relative link in it resolves and the headings match the template.
  - The two AC-1 tests and the AC-3 test pass.
  - (AC-1, AC-3) Files: docs/adr/0013-conformance-trust-model.md.
- [ ] T3 Residual-risk sentence in the service contract and onboarding docs.
  - Add the plan.md sentence with the `../adr/0013-conformance-trust-model.md` link to both texts; reword the
    `make -pn` clause in service-contract.md (Q3).
  - The AC-2 test passes for both files; the links resolve.
  - (AC-2) Files: docs/platform/service-contract.md, docs/platform/onboarding.md.
- [ ] T4 CHANGELOG and final checks.
  - Add the IDP-31 line under `[Unreleased]` / `### Added`.
  - Run `git diff --stat origin/main... -- docs/adr/` and record the output for the PR: only
    `docs/adr/0013-conformance-trust-model.md` is listed (AC-3; no "Related" links added, Q2).
  - Run `make verify` (green, including `idp spec-trace IDP-31`). Check that no trailing whitespace was added.
  - (AC-3) Files: CHANGELOG.md.
