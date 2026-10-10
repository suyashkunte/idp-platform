# Changelog

All notable changes to the IDP platform. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- IDP-7: uv workspace (Python 3.12), Make contract, pre-commit with gitleaks.
- IDP-8: `idp` CLI v0 (`spec-trace`, `test-quality-lint`, `approve-spec`, `validate`).
- IDP-9: service contract schema `idp-service.v1` (draft), shipped inside `idp-gate`.
- IDP-10: `idp-agentic` Claude Code plugin v0.1.0 (11 skills, 9 subagents, 4 guardrail hooks) and marketplace.
- IDP-11: `platform-ci` workflow and `main-protection` ruleset.
- IDP-5: bootstrap Terraform (state bucket, GitHub OIDC provider, smoke role, org budget) and OIDC smoke workflow.
- IDP-13: `idp spec-trace <KEY> --json` machine-readable traceability output (one JSON line with `ticket`, `ok`,
  `required`, `missing`, `unknown`, `tests`; missing spec prints an `error` object, exit 1) and `spec_trace.to_dict()`.
  Text output unchanged.
- IDP-17: `idp validate` checks the Make contract (required targets, `test-<kind>` for enabled `spec.tests`) and adds
  `--json` (still defaults to `./idp.yaml`). Makefile reads are confined to the service directory and capped
  (1 MiB per file, 64 files, 1024 include words, 20 include problems). Includes outside the service directory
  (e.g. a shared `../common.mk`) are rejected, even with `-include`.
- IDP-18: build profile `python-uv` (`build-profiles/python-uv/`: `profile.yaml`; `defaults.mk` with overridable
  `sbom`/`sca` default targets that run pinned `cyclonedx-bom==7.5.0` / `pip-audit==2.10.1` via `uv tool run` against
  the locked dependencies, fail closed on an empty command and are included as `include $(IDP_PROFILE_DIR)/defaults.mk`;
  `agent-notes.md` with pytest idioms, AC tagging and fixture conventions, referenced by the unit-test-generator agent).
  Schema `build-profile.v1` shipped in `idp-gate` (profiles included in the wheel) and `idp profile show <name> [--json]`
  (resolved profile plus `dir`; exit 2 with the profile name and reason on stderr).
- IDP-19: `examples/minimal-service` conformance fixture (stdlib health endpoints, `idp.yaml`, python-uv profile
  defaults; no `pyproject.toml`, not a workspace member) and `idp conformance [DIR]` (default `examples`: runs
  `idp validate` and `make verify` for each example with an `idp.yaml`, one PASS/FAIL line each plus a summary; exit 0
  all passed, 1 any failed, 2 refused). Root `make conformance`, run by `make verify`.

### Changed
- IDP-12: pin GitHub Actions runners to `ubuntu-24.04`; a test fails on any other `runs-on`.
- IDP-21: python-uv `sbom`/`sca` defaults pass `--exclude-newer '$(IDP_TOOLS_EXCLUDE_NEWER)'` (single-quoted) to
  `uv tool run` (default `2026-10-06T00:00:00Z`, overridable; an empty value, more than one word or a single quote
  fails closed), so the pinned tools' transitive dependencies resolve reproducibly. `idp-gate` packages profiles through a hatch build hook (`packages/idp-gate/hatch_build.py`)
  instead of a static `force-include`: only regular, non-symlink `*.yaml`/`*.mk`/`*.md` files without dot-prefixed
  path parts ship, the sdist carries them under `build-profiles/`, and a wheel built from the sdist includes the same
  profiles as a direct wheel build. The sdist is allow-listed too (`only-include`: `src`, `tests`, `hatch_build.py`,
  `pyproject.toml`), so untracked files in `packages/idp-gate/` never ship.
- IDP-24: idp-gate builds use a hashed build-constraints file generated from uv.lock (hatchling pinned and
  hash-checked); test builds run without UV_*/PIP_* variables and user uv config; the build hook never follows
  symlinked profile directories and fails closed when build-profiles itself is a symlink.
- IDP-25: uv sync builds of the editable idp-gate (CI, make setup) use the locked hatchling closure plus `editables`
  (the editable build's extra requirement) via `[tool.uv] build-constraint-dependencies` (versions pinned, not
  hashes); a drift test keeps uv.lock (closures and its build-constraints record), build-constraints.txt and the root
  list in step.
- IDP-22: `idp validate` reports a `GNUmakefile`/`makefile` (any case) beside `Makefile` as a violation (GNU make
  would read it instead of the validated Makefile) and fails closed with `Makefile: cannot list the service directory`;
  `idp conformance` runs `make -f Makefile verify`, fails symlinked or out-of-DIR example entries
  (`outside examples directory`) without running make, and parses `idp.yaml` once. `idp conformance` also pins
  `Makefile` and every literal include word with `--assume-old=<word>` (plus the `./`-stripped spelling), so make
  cannot remake them and restart with unvalidated content; it re-scans the Makefile before make and fails
  `include words exceed the make argument limit` above 64 KiB of such arguments. Dynamic `$(...)` includes (e.g.
  `$(IDP_PROFILE_DIR)/defaults.mk`) remain unpinned. `idp validate` reports an `idp.yaml` that cannot be read, is not
  UTF-8 or is nested too deeply as a `<root>` violation (`cannot read: ...`, `cannot parse: nesting too deep`) instead
  of a traceback, and conformance continues with the other examples; rejects any `include`/`-include`/`sinclude` line
  containing a backslash (continuation or escape); and caps include spellings at 1024, so 1025 spellings of 1024 or
  fewer files now fail with `too many include words (limit 1024)`.
