# IDP: Project Plan

| | |
|---|---|
| **Status** | v0.3: **platform-as-a-product** redesign (any application, end to end). Demo-mode governance (see [open-questions.md](open-questions.md)) |
| **Owner** | Suyash Kunte |
| **Last updated** | 2026-10-06 |
| **Source design** | *IDP Solution Design and Delivery Plan v1.0* ("the design doc"; §n.n refers to its sections) |
| **Companion docs** | [backlog.md](backlog.md) · [open-questions.md](open-questions.md) · [../platform/service-contract.md](../platform/service-contract.md) · [../platform/onboarding.md](../platform/onboarding.md) · [../architecture/overview.md](../architecture/overview.md) · [../adr/](../adr/) · [../setup/iteration-0-setup.md](../setup/iteration-0-setup.md) |

---

## 0. What we are building

An **Intelligent Delivery Pipeline delivered as a product**: a versioned platform that **any application** can adopt to get, end to end:

1. **Agentic, spec-driven development.** A hardened Jira ticket → `/implement-ticket <KEY>` in Claude Code → spec, failing tests, code,
   docs, draft PR (design doc §21). This is shipped as an installable **Claude Code plugin**, not copied files.
2. **Gated promotion of one immutable, signed artifact** through **G0 → G5**: policy as code, WORM evidence, attestations, admission
   control and a metric-based canary (§4, §6, §7, §10). This is shipped as **reusable GitHub workflows** that an app calls in about 10 lines.
3. **Measurement.** Scorecards, escape rate, flake rate, lead time and more come from the same data that drives the gates (§12, §13),
   and work for every onboarded service automatically.

**StudyTimer**, a minimal app for students to plan and track study time, is the **first tenant**. It is a reference consumer, not part of
the platform. Agnosticism is proven by onboarding a **second, different application** with **zero platform code changes** (iteration 11).

### The one design rule
> **The platform knows nothing about any specific application.** Everything app-specific is declared by the app in one file,
> `idp.yaml` (the *service contract*), and every interaction between platform and app goes through a small set of **stable,
> versioned interfaces** (§2). If adding an app ever requires editing platform code, that is a platform bug.

### Non-goals (for now)
Feature richness in StudyTimer · multi-account AWS · 24x7 operations · non-Kubernetes runtime targets (designed as an extension
point, not built) · compliance certification (we still produce audit-shaped evidence).

### Success criteria
| # | Criterion | Proof |
|---|---|---|
| S1 | One command takes a Ready ticket to a draft PR with spec, AC-traced tests, code, docs and evidence, **in any onboarded repo** | Recorded `/implement-ticket` runs in StudyTimer *and* in the second app |
| S2 | No path to production except through G0–G5 | Kyverno rejects (a) a hand-deployed image and (b) an image signed by any workflow other than the platform's reusable G0 |
| S3 | Every production release has a signed decision record + evidence bundle | Gatekeeper scorecard + S3 bundle per release |
| S4 | Bad builds are stopped automatically | Seeded defect aborted by G5 canary; rollback < 5 min |
| S5 | Guardrails hold against the agent | Demonstrated blocks: protected-path edit, push to main, threshold lowering, merge |
| S6 | Platform reproducible from zero | `make bootstrap && make env-up` from a clean account in < 60 min |
| S7 | Cost-bounded | $25/month budget alarm; one-command and nightly teardown |
| **S8** | **Any app, end to end** | A second app of a **different type and build profile** (for example, a Go or Node worker) onboarded in **< 1 day** with **0 lines changed in `idp-platform`**: only its own repo, an `idp.yaml` and one catalog entry |
| **S9** | **Platform evolves safely under tenants** | A platform minor release rolls out to both apps through a Renovate PR; a breaking change is caught by the contract conformance tests before release |

---

## 1. Topology: platform repo + application repos

Recorded in [ADR-0009](../adr/0009-platform-as-a-product.md); it supersedes the single-monorepo ADR-0004.

```
┌─────────────────────────────── idp-platform  (this repo, versioned vX.Y.Z) ───────────────────────────────┐
│ Publishes:                                                                                                │
│  • Reusable workflows        owner/idp-platform/.github/workflows/service-pipeline.yml@v1   (G0–G5, PR)  │
│  • Composite actions         owner/idp-platform/actions/<name>@v1                                         │
│  • idp CLI (idp-gate)        uv tool install idp-gate==1.*   (validate, evaluate, evidence, attest, onboard)│
│  • idp-testkit               Python test library + evidence plugin                                        │
│  • Generic Helm chart        oci://<ecr>/charts/idp-service:1.*   (driven by idp.yaml)                    │
│  • Policy profiles           policy/profiles/tier{1,2,3}@vN  (G0–G5 YAML)                                 │
│  • Schemas                   idp-service.v1, evidence-manifest.v1, release-manifest.v1, decision-record.v1│
│  • Claude Code plugin        /plugin marketplace add owner/idp-platform  →  idp-agentic@vN                │
│  • Service templates         copier copy gh:owner/idp-platform --vcs-ref v1 (templates/python-fastapi …)  │
│  • Terraform modules         modules/service-onboarding (ECR, IAM-OIDC roles, DB, secrets, namespaces)    │
│ Operates (shared, multi-tenant): Gatekeeper API · evidence store · EKS cluster + add-ons · observability │
│ Owns: service catalog (catalog/services/*.yaml) = who is onboarded, tier, repo, infra needs               │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
          ▲ pins @v1, Renovate bumps                          ▲ pins @v1
┌─────────┴──────────── studytimer (tenant #1) ┐   ┌──────────┴──────── <app #2> (tenant #2, iteration 11) ┐
│ idp.yaml · .github/workflows/idp.yml (10 ln) │   │ idp.yaml · idp.yml · different language/type          │
│ CLAUDE.md · .claude/settings.json (plugin)   │   │ same plugin, same gates, same dashboards              │
│ src/ tests/ specs/ docs/adr/ Makefile        │   │                                                        │
└──────────────────────────────────────────────┘   └────────────────────────────────────────────────────────┘
```

**Why separate repos rather than one monorepo:** a tenant that lives inside the platform repo can silently depend on internals
(relative paths, unreleased code, shared CI context). Putting the reference app in its own repo **forces** every interaction through the
published interfaces. That is the only honest proof that "any app" works. Local work stays convenient with a VS Code multi-root
workspace (`idp.code-workspace`) that opens both repos side by side.

---

## 2. The stable interfaces (the platform's public API)

Everything below is semver-versioned and has conformance tests in `idp-platform`. Full spec: [../platform/service-contract.md](../platform/service-contract.md).

| # | Interface | What the app provides | What the platform guarantees |
|---|---|---|---|
| I1 | **Service contract** `idp.yaml` (JSON Schema `idp-service.v1`) | name, owner, tier, type, build profile, runtime (port, health, resources), dependencies (postgres, secrets), test locations, SLOs, canary mechanism, Jira project | Validated on every PR (`idp validate`); drives build, chart values, infra, gates, dashboards |
| I2 | **Make target contract** | `make lint`, `make test` (unit), `make test-component`, `make verify` (all local checks), optionally `make test-smoke` / `test-api` / `test-e2e` / `test-perf` that accept `BASE_URL`, `REPORTS_DIR` | Agents, hooks and CI call **only** these targets, so the platform is language-agnostic. Build profiles provide defaults for missing targets |
| I3 | **Evidence formats** | JUnit XML; Cobertura coverage XML; SARIF; `summary.json` (schema `test-summary.v1`: pass rates by tag such as `p0`, `critical`, `smoke`); OpenAPI document | The gates read only these standard formats. `idp-testkit` produces them for Python; any language's JUnit plus a tag convention can be converted (`idp evidence junit2summary`) |
| I4 | **Runtime contract** | Container listens on `port`; `/healthz/{live,ready,startup}`; logs JSON to stdout; config via env vars; OTel via standard `OTEL_*` env vars; Prometheus metrics on `/metrics` with RED metric names (§13.2) | Generic chart wires probes, resources, PDB, HPA, Rollout, ExternalSecrets, PodMonitor, OTel env, labels (`service, env, release, track, team`) |
| I5 | **Pipeline entry point** | `.github/workflows/idp.yml` calling `service-pipeline.yml@v1` | PR checks and G0–G5 with the policy profile for the app's tier; evidence, attestations and decision records |
| I6 | **Agent plugin** | `.claude/settings.json` enabling `idp-agentic@idp-platform`; app-specific `CLAUDE.md` | Skills, subagents, hooks and spec templates, identical across all apps; per-repo protected paths come from `idp.yaml` |
| I7 | **Catalog entry** (in the platform repo, created by `idp onboard`) | repo, tier, owner, infra needs | Terraform provisions ECR, OIDC roles scoped to *that repo*, DB, SSM paths, namespaces `<env>-<service>`; the Gatekeeper registers the service |

### Extension points (designed now, implemented when needed)
| Extension | Mechanism | Shipped in v1 |
|---|---|---|
| **Build profiles** (language toolchains) | `build-profiles/<name>/profile.yaml` + scripts: setup, default make targets, SBOM/SCA tooling, coverage format | `python-uv`, `dockerfile` (generic: any language that ships a Dockerfile + make targets). Later: `node-pnpm`, `go`, `java-gradle` |
| **Service types** (canary strategy, §10.6) | `spec.type` → chart template + AnalysisTemplate + canary mechanism | `web-api` (ALB weights), `worker` (replica-ratio + queue metrics). Later: `internal-api` (mesh), `cron` (shadow run), `static-site` |
| **Policy profiles** | `policy/profiles/<tier>/g*.yaml`; app `overrides` may only **tighten** (enforced by the evaluator); loosening = waiver | `tier1`, `tier2`, `tier3` |
| **Dependencies** | `spec.dependencies.<kind>` → Terraform submodule + chart wiring | `postgres`, `secrets`. Later: `sqs`, `redis`, `s3` |
| **Deploy targets** | `spec.target` | `kubernetes`. Later: `lambda` (the Gatekeeper itself is the first candidate) |
| **Trackers** | `metadata.tracker` (Jira today) behind the `ticket-intake` skill's adapter | Jira (MCP). Later: GitHub Issues, Linear |

---

## 3. Key adaptations from the design doc

| Design doc | This implementation | ADR |
|---|---|---|
| Jenkins + shared library `idp-jenkins-lib` (§6) | GitHub Actions **reusable workflows** + composite actions; logic stays in the Python `idp` CLI | [0002](../adr/0002-github-actions-instead-of-jenkins.md) |
| 15-line Jenkinsfile per service (§6.5) | 10-line `idp.yml` + `idp.yaml` contract | [0010](../adr/0010-service-contract.md) |
| Service charts extend `idp-service-base` (§4.7) | **Generic `idp-service` chart** driven by `idp.yaml`; escape hatch: an app may ship its own chart that depends on the base library chart | [0010](../adr/0010-service-contract.md) |
| CLAUDE.md, skills, agents and hooks copied per repo (§21.4) | **Claude Code plugin + marketplace** published from the platform repo; apps enable it with two settings lines | [0011](../adr/0011-agentic-plugin.md) |
| 4 EKS clusters | 1 ephemeral EKS cluster, namespaces `<env>-<service>` | [0003](../adr/0003-single-ephemeral-eks-cluster.md) |
| Gatekeeper on the tooling cluster | Multi-tenant Gatekeeper on Lambda + Aurora Serverless v2 (scale to 0) | [0006](../adr/0006-gatekeeper-on-lambda.md) |
| cosign with a KMS key | Keyless Sigstore. Kyverno pins the signer to the **platform's reusable G0 workflow** (`job_workflow_ref`), not the app repo, so only sanctioned pipelines can produce admissible images, whichever app they serve | [0007](../adr/0007-keyless-signing.md) |
| NGINX canary | ALB traffic routing (Argo Rollouts) | [0008](../adr/0008-alb-canary-routing.md) |
| Python only | Language-agnostic via the Make + evidence contracts and build profiles | [0012](../adr/0012-build-profiles.md) |
| 2 human approvers, customer reviewer | Demo mode: 0 PR approvals; self-approved G4 stamped `sod_check: waived:solo-demo` | [open-questions Q4](open-questions.md) |
| Object Lock compliance, 3 years | Governance mode, 7 days (configurable) | [0006](../adr/0006-gatekeeper-on-lambda.md) |
| 4-hour soak, 1.5x peak, Chaos Mesh | Durations and loads are **policy-profile values**; Python k8s resilience scenarios shipped by the platform | — |

Not compromised: digest promotion, signed attestations, admission enforcement, policy as code with fail-closed evaluation, WORM
evidence, hold-and-return, expiring waivers, G4 decision records, G5 canary with automatic abort, spec-driven agent workflow with
hooks/permissions/subagents, AC→test traceability, mutation and assertion-quality validation of AI-written tests.

---

## 4. Repository layouts

### 4.1 `idp-platform` (this repo)
```
idp-platform/
├── README.md  CLAUDE.md  CONTRIBUTING.md  SECURITY.md  CHANGELOG.md  LICENSE  idp.code-workspace
├── pyproject.toml  uv.lock  Makefile  .pre-commit-config.yaml  .mcp.json  .python-version
├── .claude/                         # settings for working ON the platform (enables its own plugin from ./ — dogfooding)
├── .claude-plugin/marketplace.json  # marketplace "idp-platform" listing the plugin below
├── plugins/idp-agentic/             # THE agentic SDLC, distributed (I6)
│   ├── .claude-plugin/plugin.json
│   ├── skills/                      # implement-ticket, ticket-intake, spec-author, gen-unit-tests, gen-e2e-tests, lint-fix,
│   │                                # review-self, doc-upkeep, pr-generate, spec-drift-check, triage-ci-failure, create-story, onboard-service
│   ├── agents/                      # spec-analyst, unit-test-generator, e2e-test-generator, code-implementer, code-reviewer,
│   │                                # security-reviewer, doc-upkeeper, pr-composer, ci-triage
│   ├── hooks/hooks.json + scripts/  # protect-paths (reads idp.yaml), block-dangerous-bash, format-on-edit, definition-of-done
│   └── templates/                   # spec.md, plan.md, tasks.md, test-plan.md, PR body
├── .github/
│   ├── workflows/
│   │   ├── service-pipeline.yml     # ENTRY POINT for tenants (workflow_call): routes PR vs main vs dispatch
│   │   ├── _pr-checks.yml  _g0-build.yml  _g1-dev.yml  _g2-int.yml  _g3-stg.yml  _g4-g5-prod.yml   # reusable stages
│   │   ├── platform-ci.yml          # the platform's own PR checks (incl. contract conformance vs examples/)
│   │   ├── platform-release.yml     # release-please → tags vX.Y.Z + moves v1; publishes CLI, chart, plugin
│   │   ├── catalog-apply.yml        # terraform for services layer when catalog/ changes
│   │   ├── env-up.yml  env-down.yml  nightly.yml   # cluster lifecycle, drift, flake registry, mutation, auto-destroy
│   │   └── gatekeeper-deploy.yml    # tier-0: same G0 + decision replay test (§7.8), then Terraform deploy to Lambda
│   └── CODEOWNERS  PULL_REQUEST_TEMPLATE.md  dependabot.yml  rulesets/
├── actions/                         # composite actions: setup-profile, aws-oidc, idp-validate, gate-evaluate, upload-evidence,
│                                    # attest, deploy-helm, open-hold-ticket
├── build-profiles/                  # python-uv/, dockerfile/   (profile.yaml + default make targets + SBOM/SCA config)
├── packages/
│   ├── idp-gate/                    # `idp` CLI: validate, onboard, evaluate[--offline], evidence (upload, junit2summary), attest,
│   │                                # manifest (release), values (render chart values from idp.yaml), scorecard, doctor
│   └── idp-testkit/                 # fixtures, traced client, factories base, evidence pytest plugin, waits, k8s, slo_probe
├── services/gatekeeper/             # multi-tenant FastAPI on Lambda (Mangum), Alembic, tests
├── schemas/                         # idp-service.v1.json, test-summary.v1, evidence-manifest.v1, release-manifest.v1, decision-record.v1
├── policy/profiles/{tier1,tier2,tier3}/g0..g5.yaml  policy/CHANGELOG.md
├── charts/
│   ├── idp-service/                 # generic app chart (Rollout|Deployment, Service, Ingress, PDB, HPA, ExternalSecret, PodMonitor, NetworkPolicy)
│   └── idp-service-base/            # library chart (escape hatch for apps with custom charts)
├── deploy/                          # helmfile for cluster add-ons; kyverno/ policies; rollouts/ AnalysisTemplates per service type
├── suites/platform/                 # generic suites applied to every service: deploy conformance, contract-driven smoke,
│                                    # Schemathesis-from-OpenAPI, ZAP baseline, resilience (pod-kill, node-drain), rollback rehearsal
├── observability/                   # OTel collector, Prometheus rules, Grafana dashboards templated by `service` variable
├── catalog/services/*.yaml          # tenant registry (I7)
├── infra/terraform/
│   ├── modules/                     # vpc, eks, nat-instance, ecr, evidence-store, aurora, gatekeeper, github-oidc,
│   │                                # namespace-baseline, service-onboarding
│   └── live/{bootstrap,shared,cluster,services}/
├── templates/python-fastapi/        # copier template = a new tenant repo, ready for the pipeline and the agent
├── examples/minimal-service/        # tiny fixture app used by platform-ci conformance tests (not a product)
├── prompts/  evals/                 # versioned prompts; golden sets (triage, test quality)
├── tools/                           # doctor.sh, github_bootstrap.py, jira_bootstrap.py
└── docs/{plan,adr,architecture,platform,process,runbooks,metrics,setup}/
```

### 4.2 A tenant repo (generated from `templates/python-fastapi`; StudyTimer is the first)
```
studytimer/
├── idp.yaml                         # service contract (I1)
├── CLAUDE.md                        # app context + "follow idp-agentic plugin conventions"
├── .claude/settings.json            # enables idp-agentic@idp-platform; app-specific permission additions
├── .mcp.json                        # Jira
├── .github/workflows/idp.yml        # ~10 lines → idp-platform/service-pipeline.yml@v1
├── .github/CODEOWNERS  PULL_REQUEST_TEMPLATE.md  renovate.json
├── Makefile                         # make contract (I2)
├── pyproject.toml  uv.lock  Dockerfile
├── src/studytimer/  migrations/
├── tests/{unit,component,smoke,api,e2e}/  perf/
├── specs/<JIRA-KEY>/                # spec.md, plan.md, tasks.md, APPROVED
├── chart-values/                    # optional per-env overrides beyond idp.yaml (validated)
└── docs/adr/  CHANGELOG.md
```

---

## 5. The application: StudyTimer (tenant #1)

Python 3.12 · FastAPI · Jinja2 + HTMX · SQLAlchemy 2 · Alembic · PostgreSQL · OTel ([ADR-0005](../adr/0005-app-stack.md)).
Generated from `templates/python-fastapi`, so the scaffold (health, layout, DB, telemetry, Dockerfile, test skeletons, `idp.yaml`)
**is the template's output**: the template is tested by generating StudyTimer. Features arrive as Jira stories ([backlog.md §3](backlog.md)):
sign-up/sign-in · subjects · timer · manual log · dashboard · daily goal · weekly plan · Pomodoro · CSV export.

---

## 6. AWS topology and cost

**Region** `ap-southeast-2` · single account · **$25/month budget** · cluster up only during working sessions (≤ 15 h/week).

| Layer (Terraform `live/`) | Resources | Lifecycle |
|---|---|---|
| `bootstrap` | TF state bucket + lock, GitHub OIDC provider, Budget | once |
| `shared` | VPC (no NAT gateway; free S3 gateway endpoint), evidence S3 (Object Lock), Aurora Serverless v2 PG (min 0 ACU), Gatekeeper Lambda + HTTP API (IAM auth), chart OCI repo | always on, near-zero idle |
| `services` | **per catalog entry** via `modules/service-onboarding`: ECR repo, OIDC roles trusted only for that repo + environment, DB + user per env, SSM paths `/idp/<env>/<service>/*`, namespace definitions | follows the catalog |
| `cluster` | EKS, 2× t3.large spot, NAT instance (t4g.nano), add-ons, shared ALB, namespaces from catalog | `make env-up` / `env-down`, nightly destroy |

| Item | Per cluster-hour | ~15 h/week |
|---|---|---|
| EKS control plane | $0.10 | ~$6.5 |
| 2× t3.large spot | ~$0.07 | ~$4.5 |
| ALB + NAT instance | ~$0.035 | ~$2.5 |
| Aurora (active only) + storage | ~$0.10 | ~$6 |
| ECR/S3/SSM/Lambda/APIGW/CloudWatch | — | ~$2–5 |
| **Total** | **~$0.30/h** | **~$20–25/month** |

Indicative prices; verify. If the Free plan blocks EKS, upgrade to the Paid plan (credits still apply), per setup step 4.4.

---

## 7. The pipeline (identical for every tenant)

A tenant's entire CI/CD definition:
```yaml
# .github/workflows/idp.yml (in the app repo)
name: idp
on: { pull_request: {}, push: { branches: [main] }, workflow_dispatch: { inputs: { emergency: { type: boolean, default: false } } } }
permissions: { id-token: write, contents: read, pull-requests: write, checks: write, attestations: write, packages: write }
jobs:
  idp:
    uses: <owner>/idp-platform/.github/workflows/service-pipeline.yml@v1
    with: { emergency: ${{ inputs.emergency || false }} }
    secrets: inherit
```

`service-pipeline.yml` reads `idp.yaml`, resolves the build profile, the tier → policy profile and the service type, then runs:

| Stage | When | What (from §6.4 / §7.1, parameterised by contract + profile) | Promotion on PASS |
|---|---|---|---|
| **Contract** | always | `idp validate`: schema, catalog consistency, tighten-only overrides | — |
| **PR checks** | pull_request | `make verify` (profile defaults: lint, types, unit, component, diff-cover, SAST, secrets, SCA), `test_quality_lint` + `spec_trace` (agentic conformance), OpenAPI diff, chart render + kubeconform, *advisory* AI review | — |
| **G0** | push to main | build once (buildx), SBOM (Syft), Trivy, keyless sign **from the platform workflow identity**, push ECR by digest, provenance | attest G0 |
| **G1** | after G0 | `helm upgrade --atomic` (generic chart, values from `idp.yaml`) → `dev-<svc>`; rollout/probe/restart checks; `make test-smoke` + platform contract smoke | attest G1 |
| **G2** | after G1 | deploy `int-<svc>` against prod-manifest baseline; `make test-api`; platform suites (Schemathesis from OpenAPI, ZAP baseline, perf smoke via `make test-perf` or the generic Locust probe, migration up/down if `postgres.migrations`); Pact if `contracts` declared | attest G2, freeze release manifest |
| **G3** | nightly / dispatch | N-1 → candidate upgrade, full regression + `make test-e2e`, load/soak (profile durations), platform resilience scenarios, rollback + canary-abort rehearsal, drift + values diff | attest G3 |
| **G4** | after G3 | GitHub Environment `production-<svc>` approval → `POST /v1/decisions/g4` (decision record) | attest G4 |
| **G5** | after G4 | Argo Rollout with the canary mechanism for `spec.type`; AnalysisTemplate from `delivery.slo`; auto-abort; hypercare outcome recorded | — |
| Hold-and-return | any HOLD | Jira Gate Hold in `metadata.jira.project`, with failing criteria, evidence links, trace ids | — |

Shadow → enforced rollout per gate (§7.1) is a **catalog field per service** (`gates.mode: shadow|enforced` per gate), so a new tenant
starts in shadow mode without touching the policy.

---

## 8. Agentic development (any tenant)

Distributed as the `idp-agentic` plugin ([ADR-0011](../adr/0011-agentic-plugin.md)). Inside any onboarded repo:

```
/implement-ticket IDP-42
 intake (tracker adapter, Definition of Ready) ─► branch ─► spec/plan/tasks ─► [A: spec approval: guided stops; auto defers to PR]
 ─► failing tests (red, tagged AC ids) ─► implement (green) ─► make verify ─► reviewer subagents (≤2 loops) ─► docs
 ─► draft PR + tracker "In Review" ─► [B: human merge] ─► G0..G3 auto ─► [C: G4 approval] ─► G5 auto
```

- Skills and agents call only the **Make contract** and read only **`idp.yaml`**, so they work on any stack. Language-specific know-how
  (test idioms, fixtures) comes from the build profile's `agent-notes.md` and the app's `CLAUDE.md`.
- Hooks read protected paths from `idp.yaml` (`spec.agent.protected_paths`, defaulting to `.github/**`, `idp.yaml`, `specs/*/APPROVED`,
  `migrations/**` for `risk:low`).
- Plugin versions are pinned per repo; plugin changes ship through the platform release, with evals in `evals/` as the release test.
- Demo mode (Q4/Q5): PR approvals 0; `spec-approved` advisory; G4 self-approval stamped in the record.

---

## 9. Delivery plan (iterations)

Iterations 0–1 are hand-built. From iteration 2 on, **every** change, in either repo, is a Jira ticket run through `/implement-ticket`.
Each iteration ends with a log in `docs/plan/iterations/NN-<name>.md`.

| # | Iteration | Key deliverables | Exit criteria |
|---|---|---|---|
| 0 | **Setup & bootstrap** | Toolchain ([setup guide](../setup/iteration-0-setup.md)); AWS SSO; Jira MCP; `live/bootstrap` (state, OIDC provider, $25 budget); GitHub repo `idp-platform`; OIDC smoke workflow | `tools/doctor.sh` green; an Action assumes an AWS role via OIDC; Claude reads a IDP issue |
| 1 | **Platform skeleton & agentic plugin** | uv workspace, Makefile, pre-commit; `plugins/idp-agentic` (all skills, agents, hooks, templates); marketplace; platform `CLAUDE.md`; `spec_trace`, `test_quality_lint`, `approve_spec` inside the `idp` CLI; `schemas/idp-service.v1.json` v0; `platform-ci.yml` | Plugin installs in an empty test repo; guardrail demos (S5) pass |
| 2 | **Contract, template, PR pipeline → StudyTimer born** | `idp validate`; `python-uv` build profile; `templates/python-fastapi`; `service-pipeline.yml` + `_pr-checks.yml`; `examples/minimal-service` conformance; release-please `v0.1.0`; **generate the `studytimer` repo from the template** | StudyTimer PR checks run entirely from `@v0` reusable workflows; first `/implement-ticket` in StudyTimer reaches a draft PR |
| 3 | **Gate engine & G0 (multi-tenant)** | `idp evaluate` + policy profiles (shadow); Gatekeeper (tenants, artifacts, gate runs, waivers, decisions); `live/shared`; `catalog/` + `modules/service-onboarding` + `catalog-apply.yml`; `_g0-build.yml` with keyless signing | StudyTimer merge → signed image + G0 attestation + WORM bundle; `cosign verify-attestation` passes with the platform workflow identity |
| 4 | **Cluster, generic chart, G1** | `live/cluster` (EKS, spot, NAT instance, namespaces from catalog); add-ons; `charts/idp-service`; `idp values`; env-up/down + nightly destroy; `_g1-dev.yml` | merge → G0 → G1 green; cluster rebuild < 25 min |
| 5 | **G2** | `idp-testkit` v0.1; platform suites (contract smoke, Schemathesis, ZAP, migration, perf probe); Pact plumbing; release manifest; hold ticket action | G2 enforced for StudyTimer; seeded failure → Jira Gate Hold |
| 6 | **Observability** | kube-prometheus-stack, Loki, Tempo, OTel (track/release labels), dashboards templated by `service`, SLO burn alerts generated from `delivery.slo` | failing test trace id → backend trace (§13.6) |
| 7 | **G3** | regression/E2E plumbing, load/soak, resilience scenarios, rollback + canary-abort rehearsal, drift + values diff, readiness score (M5) | nightly G3 green; seeded perf regression held with trace evidence |
| 8 | **G4 + G5** | decision records, Kyverno enforce (signer = platform G0 workflow + G3/G4 attestations), Rollouts per service type, waivers, break-glass | S2, S3, S4 demonstrated |
| 9 | **Metrics, scorecard, AI validation** | metrics dictionary + SQL per tenant, weekly scorecard, mutmut, flake registry, triage assistant + golden set | scorecard 1 published |
| 10 | **Run the loop on StudyTimer** | MVP stories via `/implement-ticket` → prod | S1 for StudyTimer |
| 11 | **Prove "any app"** | Onboard tenant #2 of a different type and stack (proposal: a **Go or Node `worker`** using the `dockerfile` profile, for example a reminder/notification worker on SQS) with `idp onboard`; platform `v1.0.0`; Renovate upgrade drill | **S8, S9** |

---

## 10. Jira and GitHub conventions

**Jira** (Q8): `IDP` on `suyashkunte.atlassian.net` for both repos in demo mode. Each tenant declares its own project in
`idp.yaml.metadata.jira`, so other apps can use other projects. Labels: `repo:idp-platform|studytimer`,
`component:*`, `risk:*`, `spec:auto|guided`, `gate:*`, `layer:*`. Issue type **Gate Hold**; fields **Found in phase**, **Severity**.

**GitHub (demo mode):** both repos public; ruleset on `main` (PR required, 0 approvals, required checks, linear history, no force push);
platform tags protected (only `platform-release.yml` creates `v*`); environments per tenant `dev|int|stg|production-<svc>`;
AWS OIDC trust scoped per repo + environment by `service-onboarding`.

## 11. Security model (summary)
No static cloud credentials anywhere · per-tenant, per-gate IAM roles · OIDC trust policies match GitHub's **immutable subject** (`repo:<owner>@<owner_id>/<repo>@<repo_id>:…`), so a deleted-and-recreated repo or renamed owner can't reuse a role; `idp onboard` resolves the IDs · images admissible only if signed by the platform's G0 workflow
and carrying G3/G4 attestations · tenants can tighten policy, never loosen it · Actions pinned by SHA · agent guardrails from the plugin +
rulesets · threat model in iteration 3 (`docs/architecture/threat-model.md`), extended with tenant-isolation threats (cross-tenant
namespace access, role confusion, evidence spoofing between tenants).

## 12. Risks
| Risk | Mitigation |
|---|---|
| Over-generalising before anything works | Build each interface **for StudyTimer first**, then let the second tenant (iteration 11) force out leaks; v1.0.0 only after S8 |
| Breaking tenants with platform changes | Semver; `examples/minimal-service` + StudyTimer conformance in platform CI; deprecations kept for 2 minors |
| Reusable-workflow limits (nesting depth, 6 h job cap) | Flat stage structure; G3 split into parallel jobs |
| AWS spend | Budget alarm, ephemeral cluster, Aurora scale-to-zero, spot |
| Small cluster vs observability stack | Slim values, short retention, temporary node scale-up during G3 |
| Solo approver | Visible `waived:solo-demo` stamp; one ruleset change to tighten |
| Tool/version drift | Pinned versions; Renovate in both repos; syntax validated at build time |
