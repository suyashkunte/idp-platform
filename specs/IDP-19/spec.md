---
ticket: IDP-19
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: auto
---

# IDP-19: examples/minimal-service conformance fixture and make conformance

## Context
Platform changes must not break tenants (PROJECT_PLAN §12, success criterion S9). A tiny, non-product fixture app,
`examples/minimal-service`, exercises the service contract (`idp validate`, IDP-17) and the `python-uv` build profile
defaults (IDP-18) end to end in platform CI, so regressions show up before a release. A new `idp conformance` command
runs `idp validate` and `make verify` for every example; the root `Makefile` (a protected path) only gets a two-line
`conformance` target and a `verify` prerequisite, pasted by a human.

## Requirements
- **AC-1** Given `examples/minimal-service` (stdlib HTTP app exposing `/healthz/{live,ready,startup}`, an `idp.yaml`, a Makefile that includes the python-uv profile defaults, and at least one unit test), when I run `idp validate` and `make verify` inside it, then both exit 0.
  - Layout (ASSUMPTION A1): `app.py` (stdlib `http.server` app), `idp.yaml`, `Makefile`, `README.md`,
    `tests/__init__.py`, `tests/test_app.py`. No `pyproject.toml`, no `uv.lock` (see NFRs and Q7).
  - The app answers `GET /healthz/live`, `/healthz/ready` and `/healthz/startup` with `200` and the JSON body
    `{"status": "ok"}`; any other path gives `404`. `idp.yaml` declares the same three paths under
    `spec.runtime.health`. Host from `HOST` (default `127.0.0.1`), port from `PORT` (default `8000`, equal to
    `spec.runtime.port`). Container binding (`0.0.0.0`) is out of scope (iterations 3-4).
  - The Makefile includes the profile defaults through the variable form documented in service-contract.md:
    `IDP_PROFILE_DIR ?= ../../build-profiles/python-uv` followed by `include $(IDP_PROFILE_DIR)/defaults.mk`. The
    relative default makes `make verify` work by hand inside the platform checkout; `idp conformance` passes the
    resolved profile directory on the command line (see AC-2). `idp validate` skips include words containing `$`
    (IDP-17), so the include does not trip the confinement check.
  - It defines every required target (`lint`, `test`, `test-component`, `verify`, `spec-trace`) as plain rules;
    `spec.tests` enables no kinds, so no `test-<kind>` target is required. ASSUMPTION A2.
  - `make verify` = `lint` + `test`, stdlib only: `lint` = `$(PYTHON) -m compileall -q app.py tests`, `test` =
    `$(PYTHON) -m unittest discover -s tests -t .`, with `PYTHON ?= python3`. `test-component` prints that there is
    nothing to run (no external dependencies); `spec-trace` = `$(IDP) spec-trace $(KEY)` with `IDP ?= idp`. Neither is
    part of `verify`. ASSUMPTION A3, see Q4/Q5.
  - "At least one unit test": `tests/test_app.py` starts the server on `127.0.0.1` port `0` in a thread and asserts
    status and body for the three health paths and a `404` for an unknown path. Tests use plain `assert` statements
    inside `unittest.TestCase` methods so `idp test-quality-lint` (which only counts `assert` statements) and ruff
    (`PT009`) accept them.
  - Code is Python >= 3.9 compatible (`from __future__ import annotations`, no 3.10+ syntax or stdlib APIs) so a
    system `python3` works by hand; inside the platform (`uv run`), `python3` is the workspace's 3.12. ASSUMPTION A4.
  - The example's Python files pass the root `ruff check .` and `ruff format --check .` (they are in the repo tree).
- **AC-2** Given `make conformance` at the platform root, then it runs AC-1 for every directory under `examples/` that contains an `idp.yaml` and reports a pass/fail line per example.
  - The logic lives in a new subcommand `idp conformance [DIR]` (`DIR` defaults to `examples`) in `idp-gate`; the root
    target is `conformance: ; $(UV) run idp conformance examples` (human-placed snippet, see plan). AC-2 is proven by
    tests of `idp conformance`; the delegation from the root Makefile is checked under AC-4.
  - "Every directory under `examples/`" = the immediate subdirectories of `DIR` that contain a file `idp.yaml`, in
    sorted name order; names starting with `.` are skipped; other entries are ignored. ASSUMPTION A5, see Q1.
  - Per example, in order (ASSUMPTION A6, see Q3/Q6):
    1. `idp validate` equivalent: `contract.validate_service(<example>/idp.yaml)` (same code as `idp validate`). Any
       violation fails the example; make is not run.
    2. Profile: `profiles.resolve(spec.build.profile)["dir"]` (same code as `idp profile show`). A `ProfileError`
       fails the example; make is not run.
    3. `make --no-print-directory -C <example> verify IDP_PROFILE_DIR=<dir>`, stdout and stderr captured together,
       timeout 60 s, with `MAKEFLAGS`, `GNUMAKEFLAGS`, `MAKELEVEL`, `MFLAGS` and `MAKEFILES` removed from the
       environment (so `make -n`/`-j`/`-k` of an outer make, e.g. root `make verify`, do not leak in). Exit 0 passes.
  - Output on stdout, exactly one result line per example, as each finishes, then a summary (ASSUMPTION A7, see Q8):
    - `PASS <DIR>/<name>`
    - `FAIL <DIR>/<name>: idp validate: <n> violation(s)`, then one line per violation indented by 4 spaces
      (`    <path>: <message>`, the `contract.Violation` string);
    - `FAIL <DIR>/<name>: profile: <reason>` (the `ProfileError` lines joined with `; `);
    - `FAIL <DIR>/<name>: make verify exited <code>`, then the last 40 lines of make's output, indented by 4 spaces;
    - `FAIL <DIR>/<name>: make verify timed out after 60 s`;
    - last line: `conformance: <p> passed, <f> failed`.
    `<DIR>/<name>` is the path as given on the command line joined with the directory name (e.g.
    `examples/minimal-service`).
  - Exit codes: `0` all examples passed; `1` at least one failed; `2` refused, with nothing on stdout and the reason on
    stderr: `conformance: '<DIR>' is not a directory`, `conformance: no examples with idp.yaml in '<DIR>'`,
    `conformance: make not found on PATH`. ASSUMPTION A8, see Q2.
- **AC-3** (edge) Given an example whose `idp.yaml` has an unknown field (or whose Makefile lacks a required target), then `make conformance` exits non-zero and names the example. Proven by a negative fixture under `tests/`, not by breaking `examples/`.
  - The ticket writes the edge marker as part of the AC; it is kept outside the bold so `idp spec-trace` (regex
    `- **AC-n**`) parses it. Meaning unchanged.
  - Negative fixtures (no `.py` files, so pytest collects nothing there): `tests/conformance/fixtures/unknown-field/`
    (`idp.yaml` = the minimal-service contract plus `spec.bogusField: true`; Makefile with all required targets) and
    `tests/conformance/fixtures/missing-target/` (valid `idp.yaml`; Makefile without `verify`). ASSUMPTION A9.
  - A pytest test copies `examples/minimal-service` and one fixture into `tmp_path/examples/` and runs
    `idp conformance <tmp>/examples`: exit code `1`, a `PASS .../minimal-service` line, a
    `FAIL .../<fixture>: idp validate: 1 violation(s)` line, and the detail line naming the defect
    (`'bogusField'` / `missing required target 'verify'`). Both defects are caught at step 1 (IDP-17 checks required
    targets statically). `make conformance` exits non-zero because its recipe exits `1` (make then exits `2`).
  - `examples/` itself only contains passing examples: a test runs `idp conformance <repo>/examples` and expects
    exit `0`.
- **AC-4** Given `make verify` at the platform root, then it runs `make conformance`, so platform CI (`verify` job) covers it without workflow changes.
  - Root Makefile: `conformance` is in `.PHONY`, has a recipe calling `$(UV) run idp conformance examples`, and is a
    prerequisite of `verify` (`verify: verify-fast validate-plugin conformance`). The root Makefile is a protected path:
    a human pastes the snippet from plan.md. No `.github/**` change; `platform-ci.yml` already runs `make verify`.
  - Proven by a test that statically parses the root Makefile (`contract.makefile_targets` for the target, plus the
    `verify:` rule line for the prerequisite). This test FAILS until the human has placed the snippet; it is added in
    the task after the human step (see tasks.md). ASSUMPTION A10.

## Edge cases and assumptions
- Directory under `examples/` without `idp.yaml` (e.g. a README or a work-in-progress folder): ignored, no line.
- `examples/` missing or with no example: exit `2` (a conformance run that checks nothing must not look green). Q2.
- `idp.yaml` that is unparseable or schema-invalid: FAIL at step 1 with the violations; make is not run.
- `spec.build.profile: dockerfile` (schema-valid, but no profile directory exists yet): FAIL at step 2,
  `profile: 'dockerfile' not found (available: python-uv)`. Q3.
- A failing recipe in `make verify`: FAIL with make's exit code (normally `2`) and the output tail.
- Make hangs (e.g. a server that never stops): killed after 60 s, FAIL "timed out".
- Inherited `MAKEFLAGS=n` from an outer make: stripped, so a failing example still fails (tested).
- `make sbom` / `make sca` inside the example would run the profile defaults; with no `uv.lock` of its own, `uv export`
  would find the platform workspace above and describe the platform's dependencies, not the example's. They are not
  part of `verify` and need network; the example README says not to run them. Q7.
- Running the real example in place writes `__pycache__/` under `examples/minimal-service/` (gitignored).
- ASSUMPTION A1: example layout as listed under AC-1 (flat `app.py`, `tests/` package, README).
- ASSUMPTION A2: no `spec.tests` kinds enabled in the example.
- ASSUMPTION A3: example `verify` = `lint` + `test` with stdlib tools only; `test` does not write JUnit/Cobertura
  (stdlib cannot without third-party tools); `test-component` is a no-op that says so.
- ASSUMPTION A4: example code runs on Python >= 3.9.
- ASSUMPTION A5: only immediate subdirectories of `DIR` with `idp.yaml`, sorted, dot-directories skipped.
- ASSUMPTION A6: step order validate -> profile -> make; the first failing step decides and later steps are skipped;
  `IDP_PROFILE_DIR` is always passed from `spec.build.profile` (mirrors how CI's setup step will set it for tenants).
- ASSUMPTION A7: output formats as listed under AC-2; details only for failures; results streamed in order.
- ASSUMPTION A8: exit codes 0/1/2 as listed; exit-2 cases print nothing on stdout.
- ASSUMPTION A9: two negative fixtures under `tests/conformance/fixtures/`, one per defect named in AC-3.
- ASSUMPTION A10: AC-4 is satisfied by a `verify` prerequisite (not a `$(MAKE) conformance` recipe line); the test
  expects exactly that form.

## Non-functional requirements
- Conformance runs in < 60 s locally: the test that runs `idp conformance <repo>/examples` asserts its wall time is
  below 60 s (`time.monotonic`); the per-example make timeout is 60 s.
- The fixture has no third-party runtime dependencies: a test parses every `.py` file under `examples/minimal-service/`
  with `ast` and asserts each imported top-level module is in `sys.stdlib_module_names` or is local (`app`, `tests`).
- Not a workspace member, no change to root coverage: the example has no `pyproject.toml`/`uv.lock` (so uv never treats
  it as a project or member), the root `pyproject.toml` is unchanged (`[tool.uv.workspace] members = ["packages/*"]`,
  `[tool.coverage.run] source = ["packages"]`, pytest `testpaths = ["packages", "tests"]`). A test asserts these facts.
  The example's tests run only through its own `make test`, never in the root pytest session.
- No network in the example's `make verify`: the unit test binds `127.0.0.1` port `0` only; a test runs
  `make -n verify` in the example and asserts the output has none of `idp-default-`, `uv `, `pip-audit`, `cyclonedx`.
- No new runtime dependencies for `idp-gate` (stdlib `subprocess`, `shutil`, `os` plus existing modules); `uv.lock`
  unchanged. No protected path is edited by agents (root `Makefile` is a human step).
- Quality bars unchanged: mypy strict, ruff, bandit (subprocess use annotated like `approve_spec.py`), coverage
  >= 85 %, diff-cover >= 80 %.

## Out of scope
- Container build and chart render for the example (iterations 3-4).
- CI job changes under `.github/**`.
- StudyTimer conformance (separate repo), `--json` output for `idp conformance`, parallel runs, recursive discovery.
- Running `sbom`/`sca` for examples.
- Copier template (`templates/python-fastapi`); the example is a fixture, not a starting point.

## Open questions
- Q1: "Every directory under `examples/`": immediate subdirectories only, or any depth? Proposed default: immediate
  subdirectories, sorted, dot-directories skipped (A5).
  DECIDED (reviewer, PR #7): proposed default accepted.
- Q2: Missing `examples/` or no example with `idp.yaml`: exit `2` (refuse) or exit `0` with `conformance: 0 passed,
  0 failed`? Proposed default: exit `2`, so a misconfigured run cannot look green (A8).
  DECIDED (reviewer, PR #7): proposed default accepted.
- Q3: Should the runner pass `IDP_PROFILE_DIR` resolved from `spec.build.profile` (proposed; exercises profile
  discovery and lets examples be copied anywhere, e.g. into `tmp_path`), or run plain `make verify` and rely on the
  Makefile's relative default? Consequence of the proposal: an example whose profile has no directory (today
  `dockerfile`) fails conformance (A6).
  DECIDED (reviewer, PR #7): proposed default accepted.
- Q4: The Make contract says `make test` writes `junit-unit.xml` and `coverage.xml`. Is a stdlib-only fixture whose
  `test` writes neither acceptable (proposed, A3), or should it write a minimal JUnit file via a small custom unittest
  runner?
  DECIDED (reviewer, PR #7): proposed default accepted.
- Q5: Is a no-op `test-component` acceptable for a dependency-free fixture (proposed), or should it start the server
  as a subprocess and probe the health endpoints?
  DECIDED (reviewer, PR #7): proposed default accepted.
- Q6: When `idp validate` fails, skip `make verify` (proposed) or run it anyway and report both?
  DECIDED (reviewer, PR #7): proposed default accepted.
- Q7: uv behaviour for a `pyproject.toml` nested under the workspace root but not listed in `members` was not verified
  here (no shell access in the spec session). The design avoids the question by giving the example no
  `pyproject.toml` and not invoking uv in its `verify`. Is a pyproject-less example acceptable for a "python-uv"
  fixture, given that `make sbom`/`make sca` in it would describe the platform workspace (not run by conformance)?
  DECIDED (reviewer, PR #7): proposed default accepted.
- Q8: Output format: one result line per example plus indented details and a summary line (proposed, A7). Should
  details go to stderr instead of stdout?
  DECIDED (reviewer, PR #7): proposed default accepted.

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | tests/conformance/test_examples.py::test_minimal_service_passes_idp_validate_and_make_verify, tests/conformance/test_examples.py::test_minimal_service_has_app_contract_makefile_and_unit_test, tests/conformance/test_examples.py::test_minimal_service_uses_only_stdlib, tests/conformance/test_examples.py::test_minimal_service_is_not_a_workspace_member_or_coverage_source, tests/conformance/test_examples.py::test_minimal_service_verify_needs_no_network |
| AC-2 | tests/conformance/test_examples.py::test_platform_examples_pass_conformance_within_60_seconds, packages/idp-gate/tests/test_conformance.py::test_conformance_prints_one_line_per_example_and_summary, packages/idp-gate/tests/test_conformance.py::test_conformance_reports_failing_make_verify_with_output_tail, packages/idp-gate/tests/test_conformance.py::test_conformance_reports_make_timeout, packages/idp-gate/tests/test_conformance.py::test_conformance_reports_unresolvable_profile, packages/idp-gate/tests/test_conformance.py::test_conformance_ignores_inherited_make_flags, packages/idp-gate/tests/test_conformance.py::test_conformance_refuses_missing_or_empty_examples_dir, packages/idp-gate/tests/test_conformance.py::test_conformance_without_make_exits_2 |
| AC-3 | tests/conformance/test_examples.py::test_conformance_fails_and_names_example_with_unknown_field, tests/conformance/test_examples.py::test_conformance_fails_and_names_example_missing_required_target |
| AC-4 | tests/conformance/test_examples.py::test_root_make_verify_runs_conformance |
