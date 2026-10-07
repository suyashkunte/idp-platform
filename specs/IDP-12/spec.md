---
ticket: IDP-12
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: guided
---

# IDP-12: Pin GitHub Actions runners to ubuntu-24.04 before the ubuntu-latest migration (Oct 19)

## Context
GitHub moves `ubuntu-latest` to Ubuntu 26 from 2026-10-19 (actions/runner-images#14748). An unpinned runner label lets
the build environment change underneath us without a commit, which breaks reproducibility (design doc §6.1). Today both
workflows use `ubuntu-latest` (`.github/workflows/platform-ci.yml` job `verify`, line 20; `.github/workflows/oidc-smoke.yml`
job `assume-role`, line 17). This ticket pins them to `ubuntu-24.04` and adds a test so the pin cannot silently regress.
`.github/**` is protected: the two workflow edits are made by a human; the agent writes the test only.

## Requirements
- **AC-1** Given any workflow in `.github/workflows/`, when it is inspected, then every job uses `runs-on: ubuntu-24.04` (no `*-latest` labels).
  - "Any workflow" = every `*.yml` and `*.yaml` file directly under `.github/workflows/`. ASSUMPTION A1.
  - "Uses `ubuntu-24.04`" is checked as an allowlist (the only allowed label is `ubuntu-24.04`), not just a `*-latest`
    denylist. The `runs-on` rule is (ASSUMPTION A2, see Q1):
    - string: must equal `ubuntu-24.04`;
    - list: every element must equal `ubuntu-24.04`;
    - mapping (`group:` / `labels:` form): `labels` is checked as above; a mapping without `labels` is a violation;
    - any value containing a `${{ ... }}` expression (including `matrix.*`) is a violation, because it cannot be
      resolved statically;
    - missing `runs-on` is a violation, except for jobs that call a reusable workflow (`uses:` at job level), which
      have no runner of their own (ASSUMPTION A3).
  - The check must not pass vacuously: it fails if no workflow files are found.
- **AC-2** Given a PR that adds `runs-on: ubuntu-latest`, when platform-ci runs, then a check fails and names the file and job.
  - The failing check is the existing required `verify` job: `make verify` runs `make test`, which runs pytest over
    `tests/`, so a failing test in `tests/` fails `verify`. No workflow change is needed for this. ASSUMPTION A4.
  - The failure message lists every violation as `<path relative to repo root>: job '<job id>': runs-on <value> is not allowed; use 'ubuntu-24.04'`, e.g.
    `.github/workflows/platform-ci.yml: job 'verify': runs-on 'ubuntu-latest' is not allowed; use 'ubuntu-24.04'`.
  - All violations are reported in one run (not only the first).
- **AC-3** Given the change, when platform-ci and oidc-smoke run on main, then both pass.
  - Primary evidence is CI, not a local test: the platform-ci run on the PR and on main after merge, and the oidc-smoke
    run on main triggered by the push that changes `.github/workflows/oidc-smoke.yml` (its `push.paths` filter). Run
    links go in the PR description (PR) and the ticket (main).
  - Because `make verify` runs `idp spec-trace IDP-12` on this branch and spec-trace requires every AC to be cited by a
    test, AC-3 is also cited by a local proxy test: both workflows parse, the required-check job `verify` (ruleset
    `main-protection` context) still exists in platform-ci, the job `assume-role` still exists in oidc-smoke, and both
    run on `ubuntu-24.04`. The proxy is necessary, not sufficient. ASSUMPTION A5, see Q2.

## Edge cases and assumptions
- A workflow file with several jobs, some pinned and some not: only the unpinned jobs are reported.
- `runs-on: ubuntu-latest` with surrounding quotes or as a single-element list `[ubuntu-latest]`: reported.
- Other `*-latest` labels (`macos-latest`, `windows-latest`) and other pinned labels (`ubuntu-22.04`, `macos-14`,
  `self-hosted`): reported, because only `ubuntu-24.04` is allowed (A2).
- Invalid YAML in a workflow file: the test errors (fails), which also fails `verify`.
- PyYAML parses the top-level `on:` key as boolean `True`; irrelevant here because only `jobs` is read.
- Files outside `.github/workflows/` (composite actions under `.github/actions/`, none exist today) are not checked.
- ASSUMPTION A1: only `.github/workflows/*.yml` and `*.yaml` (non-recursive; GitHub ignores subdirectories).
- ASSUMPTION A2: allowlist rule as above, with exactly one allowed label `ubuntu-24.04`.
- ASSUMPTION A3: jobs with job-level `uses:` (reusable workflow calls) are exempt from the `runs-on` check; none exist today.
- ASSUMPTION A4: the AC-2 check is the existing required `verify` status check (via pytest), not a new workflow step or job.
- ASSUMPTION A5: a local proxy test tagged `IDP-12:AC-3` is acceptable so that spec-trace passes in `make verify`;
  the CI run links remain the real evidence for AC-3.
- ASSUMPTION A6: the two workflow edits are made by a human on this branch (agent may not edit `.github/**`), and they
  land in the same PR as the test, before or together with the real-repo scan test, so `verify` is never red on main.

## Non-functional requirements
- none (ticket states none). Implicit: no new dependencies (`yaml` is already used in `tests/`); `pyproject.toml`,
  `Makefile` and `uv.lock` unchanged.

## Out of scope
- Moving to Ubuntu 26 (or any other runner image).
- Adding a new CI job or workflow step for the runner check.
- Pinning or checking runners for composite actions, reusable workflows in other repos, or service templates.
- Renovate/Dependabot automation for runner labels.

## Open questions
- Q1: Which `runs-on` rule? Proposed default: allowlist with only `ubuntu-24.04`; lists checked element-wise; mappings
  checked via `labels`; any `${{ }}` expression rejected; missing `runs-on` rejected except job-level `uses:` (A2, A3).
  Alternative: a `*-latest` denylist only (looser; would allow `ubuntu-22.04`, `self-hosted`, expressions). AC-1 says
  "every job uses `runs-on: ubuntu-24.04`", which reads as an allowlist.
- Q2: spec-trace requires every AC to have a citing test, but AC-3 is a CI outcome. Is the local proxy test for AC-3
  acceptable (A5)? Alternative: change spec-trace to support CI-evidenced ACs (out of scope; would touch `idp-gate`).
- Q3: Can oidc-smoke be run via `workflow_dispatch` from the feature branch before merge for early evidence, or does the
  smoke role's OIDC trust policy only accept `main`? Proposed default: rely on the automatic run on main after merge
  (triggered by the `push.paths` filter), and re-run/revert immediately if it fails.
- Q4: Should the CHANGELOG get an entry (`### Changed`)? Proposed default: yes, one line.

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | tests/ci/test_workflow_runners.py::test_every_workflow_job_runs_on_ubuntu_24_04, tests/ci/test_workflow_runners.py::test_runs_on_rule_accepts_pinned_and_rejects_others |
| AC-2 | tests/ci/test_workflow_runners.py::test_ubuntu_latest_is_reported_with_file_and_job, tests/ci/test_workflow_runners.py::test_all_violations_reported_in_one_run, tests/ci/test_workflow_runners.py::test_runs_on_rule_accepts_pinned_and_rejects_others |
| AC-3 | tests/ci/test_workflow_runners.py::test_required_and_smoke_jobs_exist_and_are_pinned (local proxy); CI evidence: platform-ci run on the PR and on main, oidc-smoke run on main after merge (links in PR and ticket) |
