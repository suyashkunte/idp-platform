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
| `make sbom` / `make sca` | no | the build profile provides defaults |

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

## Evidence formats (I3)
JUnit XML · Cobertura XML · SARIF 2.1 · CycloneDX JSON · `summary.json` (`test-summary.v1`: totals, pass rate by tag, failed tests with
`trace_id`). Tags are `p0`, `p1`, `critical`, `smoke`, `quarantine`, plus `ac:<KEY>:AC-n` for traceability. Non-Python stacks emit tags in test names
(`[p0]`) or JUnit properties; `idp evidence junit2summary` converts them.

## Compatibility rules
- Additive fields → minor version of the schema; removals or renames → `idp-service.v2`, with a migration in `idp validate --fix`.
- Unknown fields fail validation (catches typos); `x-*` fields are allowed for app-private use.
