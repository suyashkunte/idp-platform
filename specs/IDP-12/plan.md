# IDP-12: plan

## Approach
Two parts in one PR on `feature/IDP-12-pin-ubuntu-runners`:

1. **Human (protected path):** change `runs-on: ubuntu-latest` to `runs-on: ubuntu-24.04` in the two workflow files.
   The agent may not edit `.github/**`, so a human makes and commits this edit on the branch.
2. **Agent:** add one pytest module, `tests/ci/test_workflow_runners.py`, that parses every workflow with
   `yaml.safe_load` and checks each job's `runs-on` against the rule in spec AC-1. Because platform-ci's required
   `verify` job runs `make verify` -> `make test` -> pytest over `tests/`, a regression to `ubuntu-latest` fails the
   required check with a message naming the file and job (AC-2). No workflow, Makefile or pyproject change is needed.

The checker is a few small module-level helpers inside the test module (not a new `idp-gate` command): smallest
change, no packaging, no coverage impact (coverage `source` is `packages`). It is unit-tested on synthetic workflow
files written to `tmp_path`, and run once against the real repo root.

## Changes
| File | Change |
|------|--------|
| .github/workflows/platform-ci.yml | **HUMAN ONLY.** Line 20: `runs-on: ubuntu-latest` -> `runs-on: ubuntu-24.04` (diff below). |
| .github/workflows/oidc-smoke.yml | **HUMAN ONLY.** Line 17: `runs-on: ubuntu-latest` -> `runs-on: ubuntu-24.04` (diff below). |
| tests/ci/__init__.py | New, empty (matches `tests/plugin/__init__.py` package style). |
| tests/ci/test_workflow_runners.py | New. Helpers `workflow_files(root) -> list[Path]`, `runs_on_problem(job: dict) -> str \| None`, `runner_violations(root) -> list[str]`; constant `ALLOWED_RUNNERS = {"ubuntu-24.04"}`; `ROOT = Path(__file__).resolve().parents[2]`. Tests tagged `@pytest.mark.ac("IDP-12:AC-n")` per spec traceability. |
| CHANGELOG.md | Under `[Unreleased]` add `### Changed` with `- IDP-12: pin GitHub Actions runners to \`ubuntu-24.04\`; test fails on any other \`runs-on\`.` (Q4). |

Exact human diff (apply on this branch, commit as `IDP-12: pin workflow runners to ubuntu-24.04`):

```diff
--- a/.github/workflows/platform-ci.yml
+++ b/.github/workflows/platform-ci.yml
@@ -17,7 +17,7 @@ concurrency:
 
 jobs:
   verify:
-    runs-on: ubuntu-latest
+    runs-on: ubuntu-24.04
     timeout-minutes: 15
     steps:
       - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
--- a/.github/workflows/oidc-smoke.yml
+++ b/.github/workflows/oidc-smoke.yml
@@ -14,7 +14,7 @@ permissions:
 
 jobs:
   assume-role:
-    runs-on: ubuntu-latest
+    runs-on: ubuntu-24.04
     timeout-minutes: 5
     steps:
       - name: Assume AWS role via OIDC
```

## Interfaces and data
- No API, schema, config or migration changes. No new dependencies (`yaml` is already imported by
  `tests/plugin/test_structure.py`).
- Rule implemented by `runs_on_problem(job)` (spec AC-1, Q1):
  - job has job-level `uses:` -> no problem (reusable workflow call);
  - `runs-on` missing -> problem;
  - value (or any list element / `labels` element) is a string containing `${{` -> problem;
  - string -> must be in `ALLOWED_RUNNERS`; list -> every element must be; mapping -> `labels` (string or list) checked
    the same way, missing `labels` -> problem; any other type -> problem.
- `runner_violations(root)` returns sorted messages
  `<rel path>: job '<job id>': runs-on <repr(value)> is not allowed; use 'ubuntu-24.04'` (missing case:
  `... runs-on is missing; use 'ubuntu-24.04'`). The real-repo test asserts `violations == []` with the joined list as
  the assertion message, so pytest output names every offending file and job (AC-2).
- Tests:
  - `test_every_workflow_job_runs_on_ubuntu_24_04` (AC-1): `workflow_files(ROOT)` is non-empty and
    `runner_violations(ROOT) == []`.
  - `test_runs_on_rule_accepts_pinned_and_rejects_others` (AC-1, AC-2): parametrized over `runs-on` values:
    accepted `ubuntu-24.04`, `[ubuntu-24.04]`, `{labels: ubuntu-24.04}`, job with `uses:` and no `runs-on`; rejected
    `ubuntu-latest`, `[ubuntu-latest]`, `macos-latest`, `ubuntu-22.04`, `${{ matrix.os }}`, `{group: g}`, missing.
  - `test_ubuntu_latest_is_reported_with_file_and_job` (AC-2): writes `.github/workflows/bad.yml` with job `build:
    runs-on: ubuntu-latest` under `tmp_path`; asserts the single message equals
    `.github/workflows/bad.yml: job 'build': runs-on 'ubuntu-latest' is not allowed; use 'ubuntu-24.04'`.
  - `test_all_violations_reported_in_one_run` (AC-2): two files / three jobs (one pinned) -> exactly two messages,
    pinned job absent; also covers `.yaml` extension.
  - `test_required_and_smoke_jobs_exist_and_are_pinned` (AC-3 local proxy): real repo; platform-ci has job `verify`
    (the ruleset's required context) and oidc-smoke has job `assume-role`, both `runs-on == "ubuntu-24.04"`.

## Telemetry
None new. The evidence is the pytest failure output in the `verify` check log and the JUnit report
(`reports/junit-unit.xml`, uploaded as the `reports` artifact), plus the CI run links recorded for AC-3.

## Risks, rollout and rollback
- Risk: ordering. If the real-repo test lands before the human workflow edit, `verify` goes red on the branch.
  Mitigation: tasks order the human edit (T2) before the real-repo tests (T3); both are in the same PR, so main is
  never red.
- Risk: `ubuntu-24.04` image differs from the current `ubuntu-latest` image. Today `ubuntu-latest` resolves to 24.04,
  so the change should be a no-op. Detected by the platform-ci run on the PR (AC-3).
- Risk: oidc-smoke does not run on PRs; a failure is only seen after merge. It is triggered automatically on main by
  the `push.paths` filter (the PR changes `oidc-smoke.yml`). If it fails, check the run log; rollback is a revert PR
  (human, protected path). See Q3 for an earlier `workflow_dispatch` run from the branch.
- Risk: the allowlist blocks a legitimate future runner (e.g. macOS). Mitigation: change `ALLOWED_RUNNERS` in the test
  in the same PR that adds the runner; the test failure makes the decision explicit.
- Risk: spec-trace needs a test citing AC-3; handled by the proxy test (spec A5, Q2).
- Rollout: merge the PR before 2026-10-16 (ticket due date; migration starts 2026-10-19). Record platform-ci (PR and
  main) and oidc-smoke (main) run links on the ticket.
- Rollback: revert the PR (human, because it touches `.github/**`). The test and the pin revert together.
