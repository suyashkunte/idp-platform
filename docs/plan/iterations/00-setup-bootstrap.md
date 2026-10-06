# Iteration 0: setup and bootstrap

| | |
|---|---|
| **Epic** | IDP-5 |
| **Dates** | 2026-10-06 → 2026-10-07 |
| **Outcome** | ✅ Exit criteria met |

## Shipped
- Local toolchain on macOS arm64, verified by `tools/doctor.sh` (all green).
- AWS: Paid plan + advanced features; organisation `o-58u6ldre2q` (team `idp-platform`). Workload account `idp-workloads`
  (736162637380, profile `idp`); management account 324072340710 (profile `idp-mgmt`, org-wide budget only). CLI access via
  `aws login` (short-lived credentials, no access keys).
- Jira space **IDP** (renamed from SCRUM): work types Bug and Gate Hold; fields Severity and Found in phase; workflow
  To Do → Ready → In Progress → In Review → Done. IDs recorded in `docs/plan/backlog.md`.
- `infra/terraform/live/bootstrap` applied: state bucket (S3 native locking, state migrated into it), GitHub OIDC provider,
  permission-less smoke role, $25/month org budget (before credits).
- Public repo https://github.com/suyashkunte/idp-platform; `oidc-smoke` workflow green (assume role, `sts get-caller-identity`,
  S3 access denied as expected).

## Evidence
- Smoke run: https://github.com/suyashkunte/idp-platform/actions/runs/37516007030
- `terraform plan` on bootstrap: *No changes*.

## Deviations and learnings
| Finding | Resolution |
|---|---|
| New "Sign up for AWS (new)" Free-plan accounts sit in an AWS-managed organisation whose SCP denies IAM identity providers, which blocks OIDC | Paid plan + advanced features (Q12). Root SCPs now: workloads only in ap-southeast-2, `/managed/` roles protected, spend-limit SCP on standby |
| GitHub issues **immutable OIDC subjects** (`repo:owner@id/repo@id:…`) for this repo | Trust policies match on numeric IDs, now a platform rule (plan §11) |
| The Homebrew AWS CLI is a script, so an "arm64 binary" check gave a false failure | `doctor.sh` checks `aws-cli/2` instead |
| Atlassian renamed Jira projects to "spaces" | Docs say "space"; key `IDP` |
| The AWS MCP server in Claude Code has its own credential session | Re-authorise via `/mcp` when needed; the CLI remains the fallback |

## Next
Iteration 1: platform skeleton and the `idp-agentic` Claude Code plugin (hand-built).
