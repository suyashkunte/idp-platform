# idp-platform

An **Intelligent Delivery Pipeline as a product**: a versioned platform that any application adopts to get agentic, spec-driven
development (Claude Code + Jira) and gated, evidence-based promotion (G0–G5) on AWS. It is app-agnostic by design: an application
declares itself in `idp.yaml` and calls one reusable workflow. **StudyTimer** (separate repo) is the first tenant.

> Status: **planning / iteration 0**. Start with [docs/plan/PROJECT_PLAN.md](docs/plan/PROJECT_PLAN.md).

| Doc | Purpose |
|---|---|
| [docs/plan/PROJECT_PLAN.md](docs/plan/PROJECT_PLAN.md) | Goals, topology, stable interfaces, pipeline, iterations |
| [docs/platform/service-contract.md](docs/platform/service-contract.md) | `idp.yaml`, Make, evidence and runtime contracts |
| [docs/platform/onboarding.md](docs/platform/onboarding.md) | Bring any app onto the platform |
| [docs/setup/iteration-0-setup.md](docs/setup/iteration-0-setup.md) | Local toolchain and connectivity, step by step |
| [docs/plan/backlog.md](docs/plan/backlog.md) | Jira setup, epics, StudyTimer stories |
| [docs/plan/open-questions.md](docs/plan/open-questions.md) | Decisions and their status |
| [docs/architecture/overview.md](docs/architecture/overview.md) | Diagrams and trust boundaries |
| [docs/adr/](docs/adr/) | Architecture decision records |
