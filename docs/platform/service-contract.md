# Service contract: `idp.yaml` (schema `idp-service.v1`)

`idp.yaml` sits at the root of every tenant repo. It is the **only** place an application tells the platform who it is and how to
build, test, run and release it. It is validated by `idp validate` on every PR, against `schemas/idp-service.v1.json` and the
platform's catalog entry.

> **Status:** draft v1 (to be frozen when platform `v1.0.0` ships in iteration 11). Fields marked *(later)* are reserved extension points.

## Example (StudyTimer)
```yaml
apiVersion: idp.dev/v1
kind: Service
metadata:
  name: studytimer                  # DNS-safe; becomes namespace suffix, ECR repo, DB name, dashboards label
  owner: suyash                     # team or person; CODEOWNERS default
  tier: 1                           # 1|2|3 → policy profile, SLO strictness, canary pace
  tracker: { kind: jira, site: suyashkunte.atlassian.net, project: IDP, labels: [repo:studytimer] }
spec:
  type: web-api                     # web-api | worker | internal-api (later) | cron (later) | static-site (later)
  target: kubernetes                # kubernetes | lambda (later)
  build:
    profile: python-uv              # python-uv | dockerfile | node-pnpm (later) | go (later) | java-gradle (later)
    dockerfile: Dockerfile
    context: .
  runtime:
    port: 8000
    health: { live: /healthz/live, ready: /healthz/ready, startup: /healthz/startup }
    metrics: { path: /metrics }
    resources: { cpu: 250m, memory: 384Mi, memoryLimit: 512Mi }
    replicas: { dev: 1, int: 1, stg: 2, prod: 3 }
    autoscaling: { min: 3, max: 6, cpuTarget: 65 }      # prod only
    env: { LOG_LEVEL: info }                            # non-secret config; per-env overrides in chart-values/
  dependencies:
    postgres:
      enabled: true
      migrations: { command: "alembic upgrade head", downgrade: "alembic downgrade -1", policy: expand-contract }
    secrets: [SESSION_SECRET]                           # → SSM /idp/<env>/studytimer/SESSION_SECRET via ExternalSecret
  interfaces:
    openapi: openapi.json                               # used for diff (PR), Schemathesis (G2)
    contracts: { provider: false, consumers: [] }       # Pact roles (optional)
  tests:                                                # all via the Make contract; listed so gates know what to expect
    smoke: true          # make test-smoke   (required for G1)
    api: true            # make test-api     (G2)
    e2e: true            # make test-e2e     (G3)
    perf: true           # make test-perf    (G2 smoke / G3 load); false → platform generic HTTP probe
    critical_journeys: [sign-in, start-stop-timer, dashboard]
  delivery:
    slo: { availability: 0.999, p95_read_ms: 300, p95_write_ms: 800 }
    canary: { steps: [5, 25, 50, 100], min_requests: 500 }   # mechanism derived from spec.type
    kpis: []                                                 # optional PromQL ratios, e.g. checkout success
  gates:
    overrides:                                               # TIGHTEN ONLY: evaluator rejects any loosening
      G0: { diff_coverage_min: 0.85 }
  agent:
    protected_paths: [".github/**", "idp.yaml", "migrations/**", "specs/*/APPROVED"]
    risk_defaults: { "migrations/**": high, "src/**/auth/**": high }
```

## The Make contract (I2)
| Target | Required | Contract |
|---|---|---|
| `make lint` | yes | static checks; non-zero on findings |
| `make test` | yes | unit tests; writes `$(REPORTS_DIR)/junit-unit.xml`, `coverage.xml` (Cobertura) |
| `make test-component` | yes | component tests with real dependencies (testcontainers or similar) |
| `make verify` | yes | everything a PR must pass locally (CI calls this) |
| `make verify-fast` | recommended | quick subset (lint + unit tests); the agent's Stop hook calls it |
| `make spec-trace KEY=<KEY>` | yes | AC→test traceability (`idp spec-trace`); the Stop hook and verify call it |
| `make format FILES=...` | recommended | format only the given files; the agent's PostToolUse hook calls it |
| `make test-smoke` / `test-api` / `test-e2e` / `test-perf` | when `tests.*: true` | run against `BASE_URL`; write JUnit + `summary.json` into `REPORTS_DIR` |
| `make sbom` / `make sca` | no | the build profile provides defaults (`defaults.mk`, see [Build profile defaults](#build-profile-defaults)); python-uv writes `$(REPORTS_DIR)/sbom.cdx.json` (CycloneDX JSON) and `$(REPORTS_DIR)/sca.json` (pip-audit JSON) |

### How `idp validate` checks it
- `idp validate` with no argument validates `./idp.yaml`; `idp validate path/to/file.yaml` validates that file. The
  Makefile checked is always `Makefile` in the same directory as the validated file (`makefile` and `GNUmakefile` are not
  recognised).
- Checks, in this order: the `idp-service.v1` schema, then the Make contract: every target marked "yes" above
  (`lint`, `test`, `test-component`, `verify`, `spec-trace`), then `test-<kind>` for each of `smoke`, `api`, `e2e`,
  `perf` whose `spec.tests.<kind>` is `true`. Recommended targets (`verify-fast`, `format`) are not checked. Every missing
  target is reported, not only the first. A missing Makefile is reported as a single `Makefile not found` violation.
  Make checks also run when the schema check fails, but are skipped if the YAML cannot be parsed into a mapping.
- Targets are found by **static parsing**; `make` is never executed. A target counts when a line at column 0 names it
  before `:` or `::` (not `:=`, `::=`, `:::=`); comments after an unescaped `#` are ignored (`\#` is a literal hash).
  Not counted: names listed only in `.PHONY:` or other special targets starting with `.`, pattern rules (`%`), names
  containing `$(...)`, variable assignments, target-specific variable lines (`name: VAR = x`, also with `:=`, `?=`,
  `+=`, `!=`, `export`/`override`), lines inside `define ... endef` (skipped, nesting supported), recipe (tab-indented)
  and indented lines. `include`, `-include` and `sinclude` are followed recursively for literal paths relative to the
  Makefile's directory; words with `$` or glob characters and files not on disk are skipped. Limitations: conditionals
  (`ifeq`/`ifdef`/...) are not evaluated (targets in either branch count); line continuations in rule lines and
  variable expansion are not interpreted, so define required targets as plain rules.
- Reads are **confined to the service directory** (the directory of the validated `idp.yaml`): absolute include paths,
  includes escaping it via `..`, and files whose real path (after symlinks) is outside it are not read and are reported,
  e.g. `include '../shared.mk' is outside the service directory` or `Makefile resolves outside the service directory`.
  Each file is read up to 1 MiB (`'<name>' exceeds 1 MiB`) and at most 64 files are read
  (`too many included files (limit 64)`). Unreadable, non-UTF-8 or symlink-loop files, and include words containing a
  NUL byte, give `cannot read '<name>'`. Repeated include words are checked once; more than 1024 distinct include words
  give `too many include words (limit 1024)`, and after 20 problems scanning stops with
  `too many include problems (limit 20)`. Words echoed in messages are truncated to 200 characters (`…`).
  Includes outside the service directory, such as a shared `../common.mk` in a monorepo, are rejected even with
  `-include`; copy shared targets into the service directory instead.
  When any of these occur, only these problems are reported (the target list would be incomplete), in line order.
- Text output: `<file>: valid (idp-service.v1.json)`, or one line per violation, e.g.
  `idp.yaml: Makefile: missing required target 'lint'`.
- `--json` prints exactly one JSON line with keys `file`, `valid`, `schema`, `violations` (each `{path, message}`;
  schema violations use the dotted field path, Make violations use `Makefile`):

```json
{"file": "idp.yaml", "valid": false, "schema": "idp-service.v1", "violations": [{"path": "Makefile", "message": "missing required target 'test-component'"}]}
```

- Exit codes: `0` valid, `1` violations found, `2` file not found or usage error (nothing on stdout, message on stderr,
  also with `--json`).

### Build profile defaults
The build profile named in `spec.build.profile` ([ADR-0012](../adr/0012-build-profiles.md)) ships a `defaults.mk` that
provides the optional targets (`sbom`, `sca` for `python-uv`). Include it through a variable:

```make
include $(IDP_PROFILE_DIR)/defaults.mk
```

- `IDP_PROFILE_DIR` is the profile directory: the `dir` printed by `idp profile show <profile> --json` (set by hand
  locally; in CI by the platform's setup step). Use the variable form: `idp validate` skips include words containing
  `$`, but rejects a literal include outside the service directory (e.g. an absolute path to the installed
  `defaults.mk`) as `include '...' is outside the service directory`.
- A target you define yourself (`sca: ...` with a recipe) replaces the default, with no make warnings, whether the
  include comes before or after your rule. Overriding one default does not affect the other.

Overridable variables (all `?=`; set them in the Makefile or on the command line):

| Variable | python-uv default |
|---|---|
| `IDP_SBOM_CMD` | export the locked runtime dependencies (`--no-dev`), then `cyclonedx-py requirements` → `$(REPORTS_DIR)/sbom.cdx.json` |
| `IDP_SCA_CMD` | export all locked dependency groups (dev included), then `pip-audit --disable-pip --requirement` → `$(REPORTS_DIR)/sca.json` |
| `IDP_CYCLONEDX_SPEC` | `cyclonedx-bom==7.5.0` (pinned; run with `uv tool run --from`) |
| `IDP_PIP_AUDIT_SPEC` | `pip-audit==2.10.1` (pinned; run with `uv tool run --from`) |
| `REPORTS_DIR` | `reports` |
| `UV` | `uv` |

- The exports use `uv export --locked`: they fail if uv.lock is stale (run `uv lock`), and never change uv.lock or
  the project environment. SBOM = runtime dependencies (`IDP_SBOM_EXPORT_CMD`, `--no-dev`, into
  `IDP_SBOM_REQUIREMENTS`, default `$(REPORTS_DIR)/requirements.sbom.txt`), so it describes what ships. SCA = all
  groups, dev included, because dev tools run in CI (`IDP_EXPORT_CMD`, into `IDP_REQUIREMENTS`, default
  `$(REPORTS_DIR)/requirements.locked.txt`). SCA covers the CI platform only (Linux/CPython, matching the deploy
  target): dependencies conditional on other platforms are not audited. Network is used only when the recipes
  run (tool download, vulnerability database), never at parse time. Names `idp-default-*` and `_idp_*` are reserved.
- `idp profile show <name> [--json]` prints the resolved profile (`profile.yaml` plus `dir`) as YAML, or as one JSON
  line with `--json`, and exits `0`. An invalid name, unknown or invalid profile, or missing profiles directory exits
  `2` with `profile show: ...` on stderr and nothing on stdout.

Caveats:
- A tenant that lists `sbom` or `sca` in `.PHONY` **without defining it** gets **no** default: make skips the
  pattern-rule fallback for phony targets, so `make sca` silently does nothing and exits 0. Only list these in `.PHONY`
  when you define them.
- A rule with prerequisites but no recipe (`sca: lint`) still gets the default recipe, and the default `sca` runs
  **before** `lint`.
- A Makefile with your own match-anything rule (`%:`) may conflict with the fallback.
- If `IDP_PROFILE_DIR` is unset, the include becomes `/defaults.mk` and make fails at the include.
- An empty `IDP_SBOM_CMD`/`IDP_SCA_CMD` fails closed: make stops with an error naming the variable instead of exiting
  0 without evidence. A failing command fails the target.
- `make sca` fails (non-zero exit) when pip-audit finds known vulnerabilities; read the findings in
  `reports/sca.json`. This is deliberate while no gate engine exists; once the policy/gate engine lands, `sca` becomes
  report-only and the gate decides, with severity thresholds and expiring waivers.
- Pipelines should check that `reports/sbom.cdx.json` and `reports/sca.json` exist (and are non-empty), not trust the
  exit code alone: a `.PHONY` listing or a tenant-defined target can exit 0 without writing evidence.

## Evidence formats (I3)
JUnit XML · Cobertura XML · SARIF 2.1 · CycloneDX JSON · `summary.json` (`test-summary.v1`: totals, pass rate by tag, failed tests with
`trace_id`). Tags are `p0`, `p1`, `critical`, `smoke`, `quarantine`, plus `ac:<KEY>:AC-n` for traceability. Non-Python stacks emit tags in test names
(`[p0]`) or JUnit properties; `idp evidence junit2summary` converts them.

## Compatibility rules
- Additive fields → minor version of the schema; removals or renames → `idp-service.v2`, with a migration in `idp validate --fix`.
- Unknown fields fail validation (catches typos); `x-*` fields are allowed for app-private use.
