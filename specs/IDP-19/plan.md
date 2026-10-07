# IDP-19: plan

## Approach
Add a stdlib-only fixture service under `examples/minimal-service/`, a small `idp_gate/conformance.py` module with an
`idp conformance [DIR]` subcommand that reuses `contract.validate_service()` (IDP-17) and `profiles.resolve()`
(IDP-18) and then runs `make verify` per example, two negative fixtures under `tests/conformance/fixtures/`, tests,
docs and a CHANGELOG entry. The root `Makefile` gets a two-line target and one prerequisite, placed by a human.

### Hard constraints and how the design meets them
1. **Root `Makefile` and root `pyproject.toml` are protected** (`.claude/idp-protected-paths.txt`); agents cannot edit
   them. All logic is in `packages/idp-gate` (editable); the root Makefile only delegates to `idp conformance`. Tests
   of AC-1..AC-3 call the runner directly (`cli.main(["conformance", ...])`, `conformance.check_example()`) and never
   depend on the root Makefile. The AC-4 test parses the root Makefile and **fails until the human has pasted the
   snippet below**; it is therefore written in the task after the human step (T6). Until then `make verify` also fails
   at `idp spec-trace IDP-19` (AC-4 has no test yet); pytest itself stays green.
2. **The example must not become a uv workspace member or change root coverage.** The root `pyproject.toml` cannot
   change (`members = ["packages/*"]`, coverage `source = ["packages"]`, `testpaths = ["packages", "tests"]`).
   Chosen: the example has **no `pyproject.toml` and no `uv.lock`**, and its `make verify` uses only `$(PYTHON)`
   (default `python3`) with `compileall` and `unittest`. Why: uv only treats a directory as a project/member when it
   has a `pyproject.toml`; without one, the nested-but-unlisted-member behaviour of uv (error, warning or silent
   inclusion, which could not be verified in the spec session; spec Q7) cannot occur. `uv run --no-project` was
   rejected: it still needs uv and would pick up the root workspace's environment when run inside the repo, which is
   exactly the coupling to avoid. Root pytest does not collect `examples/` (not in `testpaths`), and coverage measures
   only `packages`, so root coverage is unchanged. No network: `verify` does not depend on `sbom`/`sca` (the
   python-uv defaults only provide fallbacks for targets that are requested), and the unit test binds `127.0.0.1:0`.
3. **Contract and profile location.** `idp validate` requires `apiVersion`, `kind`, `metadata.{name, owner, tier,
   tracker.{kind, site, project}}`, `spec.{type, build.profile, runtime.{port, health.{live, ready}}}` and the Make
   targets `lint`, `test`, `test-component`, `verify`, `spec-trace` (plus `test-<kind>` for enabled `spec.tests`;
   none here). It follows only literal includes inside the service directory and skips include words containing `$`.
   The example therefore uses the documented variable form with a checkout-relative default:
   `IDP_PROFILE_DIR ?= ../../build-profiles/python-uv` + `include $(IDP_PROFILE_DIR)/defaults.mk`. That works by hand
   from `examples/minimal-service/` inside the platform repo. `idp conformance` passes
   `IDP_PROFILE_DIR=<profiles.resolve(spec.build.profile)["dir"]>` on the make command line (overrides `?=`), the same
   directory `idp profile show python-uv --json` prints, so copies of the example in `tmp_path` work too, and the run
   mirrors how CI's setup step will set the variable for tenants.
4. **Smallest change, AC markers, coverage.** One new module (~80 lines) plus a CLI subcommand; tests tagged
   `@pytest.mark.ac("IDP-19:AC-n")`; `conformance.py` covered by in-process tests (only `make` runs as a subprocess),
   so package coverage stays >= 85 % and diff-cover >= 80 %.
5. **Open questions** are listed in spec.md (Q1-Q8).

### Root Makefile snippet (human step, T5)
Paste into the root `Makefile` (recipe lines start with a TAB):

```make
# 1. add `conformance` to the existing .PHONY line:
.PHONY: help setup lint fmt format test verify verify-fast spec-trace approve-spec validate-plugin clean conformance

# 2. add `conformance` as a prerequisite of verify (rest of the rule unchanged):
verify: verify-fast validate-plugin conformance ## Everything a PR must pass locally

# 3. new target (e.g. after validate-plugin):
conformance: ## idp validate + make verify for every examples/*/ with an idp.yaml (IDP-19)
	$(UV) run idp conformance examples
```

`platform-ci.yml` already runs `make verify` in the `verify` job, so no workflow change is needed (AC-4).

### Runner design (`idp_gate/conformance.py`)
```python
MAKE_TIMEOUT_S = 60
OUTPUT_TAIL_LINES = 40
EXAMPLE_FILE = "idp.yaml"
# Inherited make state must not change the example's run (outer `make -n/-k/-j`, MAKEFILES).
_MAKE_ENV_STRIPPED = frozenset({"MAKEFLAGS", "GNUMAKEFLAGS", "MAKELEVEL", "MFLAGS", "MAKEFILES"})

@dataclass(frozen=True)
class Result:
    example: Path               # DIR / name, as given on the command line
    ok: bool
    reason: str = ""            # e.g. "idp validate: 1 violation(s)"
    details: tuple[str, ...] = ()
    def lines(self) -> list[str]  # "PASS <example>" or "FAIL <example>: <reason>" + "    <detail>" lines

def find_examples(root: Path) -> list[Path]   # sorted immediate subdirs with idp.yaml, dot-dirs skipped
def check_example(directory: Path, make: str) -> Result
```
`check_example`:
1. `violations = contract.validate_service(directory / "idp.yaml")`; non-empty -> `Result(ok=False,
   reason=f"idp validate: {len(violations)} violation(s)", details=tuple(str(v) for v in violations))`.
2. `doc, _ = contract._load_yaml(...)` (already used by `profiles.py`); `profiles.resolve(doc["spec"]["build"]["profile"])`;
   `ProfileError` -> `reason="profile: " + "; ".join(exc.lines)`. (Schema-valid documents always have this key.)
3. `subprocess.run([make, "--no-print-directory", "-C", str(directory), "verify", f"IDP_PROFILE_DIR={dir}"],
   stdout=PIPE, stderr=STDOUT, text=True, env=<os.environ minus _MAKE_ENV_STRIPPED>, timeout=MAKE_TIMEOUT_S,
   check=False)`; `TimeoutExpired` -> `reason=f"make verify timed out after {MAKE_TIMEOUT_S} s"`; non-zero ->
   `reason=f"make verify exited {rc}"`, `details` = last `OUTPUT_TAIL_LINES` output lines. Annotated
   `# noqa: S603  # nosec B603` and `import subprocess  # nosec B404`, as in `approve_spec.py` (fixed argv, no shell;
   `make` is an absolute path from `shutil.which`).

CLI `_cmd_conformance(args)`: `root = Path(args.dir)`; not a directory -> stderr
`conformance: '<DIR>' is not a directory`, exit 2; `make = shutil.which("make")` is None -> stderr
`conformance: make not found on PATH`, exit 2; no examples -> stderr `conformance: no examples with idp.yaml in
'<DIR>'`, exit 2. Otherwise print each result's lines as it finishes (`flush=True`), then
`conformance: <p> passed, <f> failed`; exit 1 if any failed, else 0. Parser: `conformance` subparser, help "run idp
validate and make verify for every example (IDP-19)", positional `dir` (`nargs="?"`, default `examples`).

## Changes
| File | Change |
|------|--------|
| examples/minimal-service/app.py | New. Stdlib `http.server` app: `HEALTH_PATHS = ("/healthz/live", "/healthz/ready", "/healthz/startup")`; `Handler(BaseHTTPRequestHandler)` with `do_GET` returning `200` + `{"status": "ok"}` (`Content-Type: application/json`) for health paths, `404` otherwise, request logging silenced; `make_server(host, port) -> ThreadingHTTPServer`; `main()` reads `HOST` (default `127.0.0.1`) and `PORT` (default `8000`) and serves forever; `if __name__ == "__main__": main()`. Python >= 3.9 compatible. (AC-1) |
| examples/minimal-service/tests/__init__.py | New, empty (unittest discovery with `-t .`). (AC-1) |
| examples/minimal-service/tests/test_app.py | New. `unittest.TestCase` with `setUpClass` starting `make_server("127.0.0.1", 0)` in a daemon thread and `tearDownClass` shutting it down; tests use `http.client` and plain `assert` statements: each health path -> `200` and body `{"status": "ok"}`; `/nope` -> `404`. No sleeps (server is bound before the thread starts). (AC-1) |
| examples/minimal-service/idp.yaml | New. `apiVersion: idp.dev/v1`, `kind: Service`, `metadata: {name: minimal-service, owner: platform, tier: 3, tracker: {kind: jira, site: suyashkunte.atlassian.net, project: IDP, labels: [repo:idp-platform]}}`, `spec: {type: web-api, target: kubernetes, build: {profile: python-uv}, runtime: {port: 8000, health: {live: /healthz/live, ready: /healthz/ready, startup: /healthz/startup}}}`. A header comment says it is a conformance fixture, not a product. (AC-1) |
| examples/minimal-service/Makefile | New. Header comment (fixture, stdlib only, no uv project). `PYTHON ?= python3`, `IDP ?= idp`, `IDP_PROFILE_DIR ?= ../../build-profiles/python-uv`, `include $(IDP_PROFILE_DIR)/defaults.mk`, `.PHONY: verify lint test test-component spec-trace` (not `sbom`/`sca`: IDP-18 caveat), `verify: lint test`, `lint: $(PYTHON) -m compileall -q app.py tests`, `test: $(PYTHON) -m unittest discover -s tests -t .`, `test-component: @echo "test-component: no external dependencies; nothing to run"`, `spec-trace: $(IDP) spec-trace $(KEY)`. All required targets as plain column-0 rules (IDP-17 static parser). (AC-1) |
| examples/minimal-service/README.md | New, short: what the fixture is (not a product, not a template), how to run (`idp validate && make verify` here, or `make conformance` at the root), `IDP_PROFILE_DIR`, and "do not run `make sbom`/`make sca` here" (no own lockfile; spec Q7). (AC-1) |
| packages/idp-gate/src/idp_gate/conformance.py | New, as designed above. (AC-2, AC-3) |
| packages/idp-gate/src/idp_gate/cli.py | Import `conformance`, `shutil`; add `_cmd_conformance` and the `conformance` subparser as designed above. Existing commands unchanged. (AC-2, AC-3) |
| packages/idp-gate/tests/test_conformance.py | New; tagged `IDP-19:AC-2`. Helper writes tiny examples into `tmp_path/examples/<name>/` (valid `idp.yaml` from a dict; Makefile with all required targets and a chosen `verify` recipe, no include); `make` tests skip if `shutil.which("make")` is None. Tests: one line per example + summary for two passing examples, a dir without `idp.yaml` and a `.hidden` dir (exact stdout, exit 0); failing `verify` (`exit 3`) -> `FAIL <p>: make verify exited 2` plus indented output tail, exit 1; timeout via `monkeypatch.setattr(conformance.subprocess, "run", <raises TimeoutExpired>)`; `spec.build.profile: dockerfile` -> `FAIL <p>: profile: 'dockerfile' not found (available: python-uv)`; `monkeypatch.setenv("MAKEFLAGS", "n")` with failing `verify` still FAILs; missing dir / empty dir -> exit 2, stdout empty, exact stderr; `monkeypatch.setattr(cli.shutil, "which", lambda _: None)` (the CLI does the lookup) -> exit 2. (AC-2) |
| tests/conformance/__init__.py | New, empty (root `tests/` is a package tree). |
| tests/conformance/fixtures/unknown-field/idp.yaml, Makefile | New negative fixture: minimal-service contract plus `spec.bogusField: true`; Makefile with all required targets (trivial recipes). (AC-3) |
| tests/conformance/fixtures/missing-target/idp.yaml, Makefile | New negative fixture: valid contract; Makefile with `lint`, `test`, `test-component`, `spec-trace` but no `verify`. (AC-3) |
| tests/conformance/test_examples.py | New. `ROOT = Path(__file__).resolve().parents[2]`. AC-1: `cli.main(["validate"])` after `monkeypatch.chdir(<example>)` -> 0, and `conformance.check_example(<example>, make)` -> `ok`; static layout test (files exist, Makefile contains `include $(IDP_PROFILE_DIR)/defaults.mk`, `idp.yaml` health paths equal the three `/healthz/*` paths, `tests/test_*.py` exists); stdlib-imports test (`ast`, `sys.stdlib_module_names`); not-a-member test (no `pyproject.toml`/`uv.lock` in the example; `tomllib` on root `pyproject.toml`: `members == ["packages/*"]`, coverage `source == ["packages"]`, `"examples"` not in `testpaths`); no-network test (`make -n --no-print-directory -C <example> verify` with stripped env: exit 0, none of `idp-default-`, `uv `, `pip-audit`, `cyclonedx` in output). AC-2: `cli.main(["conformance", str(ROOT / "examples")])` -> 0, one `PASS` line per `examples/*/idp.yaml`, wall time < 60 s. AC-3: copy `examples/minimal-service` and one fixture into `tmp_path/examples/` (`shutil.copytree`, ignoring `__pycache__`), run conformance -> exit 1, `PASS .../minimal-service`, `FAIL .../<fixture>: idp validate: 1 violation(s)`, detail contains `'bogusField'` / `missing required target 'verify'`. AC-4 (added in T6): `contract.makefile_targets(ROOT / "Makefile").targets` contains `conformance`; the `verify:` rule line's prerequisites (before `##`) contain `conformance`; the root Makefile text contains `idp conformance examples`. Make-dependent tests skip without `make`. (AC-1..AC-4) |
| docs/platform/onboarding.md | New section "## Reference example": `examples/minimal-service/` is the smallest service that passes `idp validate` and `make verify` with the `python-uv` profile defaults (stdlib health endpoints, `idp.yaml`, Makefile); platform CI runs `make conformance` (`idp conformance examples`: `idp validate` + `make verify` for every `examples/*/` with an `idp.yaml`, one PASS/FAIL line each) inside `make verify`; it is a fixture, not a template. (DoD) |
| CHANGELOG.md | Under `[Unreleased]` / `### Added`: `- IDP-19: \`examples/minimal-service\` conformance fixture (stdlib health endpoints, \`idp.yaml\`, python-uv profile defaults) and \`idp conformance [DIR]\` (\`idp validate\` + \`make verify\` per example, one PASS/FAIL line each); root \`make conformance\`, run by \`make verify\`.` (DoD) |
| Makefile (root, PROTECTED) | Human only (T5): the snippet above. (AC-4) |

Not changed: root `pyproject.toml`, `uv.lock`, `.github/**`, `build-profiles/**`, existing tests.

## Interfaces and data
- CLI (additive): `idp conformance [DIR]` (default `examples`). Exit `0` all passed, `1` any failed, `2` refused
  (DIR not a directory, no examples, `make` not on PATH; stderr only, stdout empty). Output per spec AC-2:
  ```
  PASS examples/minimal-service
  FAIL examples/unknown-field: idp validate: 1 violation(s)
      spec: Additional properties are not allowed ('bogusField' was unexpected)
  conformance: 1 passed, 1 failed
  ```
- Make (root): new `conformance` target; `verify` gains it as a prerequisite.
- Python API: new module `conformance` (`find_examples`, `check_example`, `Result`, constants). No changes to
  `contract`, `profiles` or the `idp-service.v1` schema.
- Example interface for make: `PYTHON`, `IDP`, `IDP_PROFILE_DIR` (all `?=`).
- No dependency, lockfile or wheel-content change.

## Telemetry
None. Local CLI and Make target; the per-example PASS/FAIL lines appear in the `verify` job log.

## Risks, rollout and rollback
- Risk: the AC-4 test and `idp spec-trace IDP-19` fail until the human places the snippet. Mitigation: explicit human
  task T5 before T6; called out in the PR description.
- Risk: `python3` on PATH differs (macOS system 3.9 by hand vs workspace 3.12 under `uv run`). Mitigation: example code
  is 3.9-compatible; CI (ubuntu-24.04) and `uv run` use 3.12.
- Risk: loopback port or thread issues make the example test flaky. Mitigation: port `0` (kernel-assigned), server
  bound before the thread starts, no sleeps, 60 s make timeout.
- Risk: double runtime: the real example runs in pytest (`make test`) and again in `make conformance`. Cost is a few
  seconds; NFR test asserts < 60 s.
- Risk: diff-cover counts example `.py` lines. They are not in `coverage.xml` (source = `packages`), which diff-cover
  ignores; detected by `make verify` if not.
- Risk: future examples with other profiles (e.g. `dockerfile`) fail until that profile has a directory (spec Q3).
- Rollout: lands with the PR; the root snippet activates it in `make verify` and so in platform CI.
- Rollback: revert the PR and remove the root Makefile snippet (human); no state or data.
