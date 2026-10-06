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
  tracker: { kind: jira, project: IDP, labels: [repo:studytimer] }
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
| `make verify` | yes | everything a PR must pass locally (the plugin's Stop hook and CI both call this) |
| `make test-smoke` / `test-api` / `test-e2e` / `test-perf` | when `tests.*: true` | run against `BASE_URL`; write JUnit + `summary.json` into `REPORTS_DIR` |
| `make sbom` / `make sca` | no | the build profile provides defaults |

## Evidence formats (I3)
JUnit XML · Cobertura XML · SARIF 2.1 · CycloneDX JSON · `summary.json` (`test-summary.v1`: totals, pass rate by tag, failed tests with
`trace_id`). Tags are `p0`, `p1`, `critical`, `smoke`, `quarantine`, plus `ac:<KEY>:AC-n` for traceability. Non-Python stacks emit tags in test names
(`[p0]`) or JUnit properties; `idp evidence junit2summary` converts them.

## Compatibility rules
- Additive fields → minor version of the schema; removals or renames → `idp-service.v2`, with a migration in `idp validate --fix`.
- Unknown fields fail validation (catches typos); `x-*` fields are allowed for app-private use.
