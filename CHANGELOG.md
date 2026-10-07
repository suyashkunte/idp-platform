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

### Changed
- IDP-12: pin GitHub Actions runners to `ubuntu-24.04`; a test fails on any other `runs-on`.
