---
key: IDP-5
type: Epic
status: Done
summary: "E1 Setup & bootstrap (iteration 0)"
parent:
labels: [component:infra, iteration:0, layer:infra, repo:idp-platform]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-06T23:45:27.143+0530
updated: 2026-10-07T00:33:59.439+0530
resolved: 2026-10-07T00:33:59.413+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-5
---

# IDP-5: E1 Setup & bootstrap (iteration 0)

## Description

## Context / why

Foundations for the IDP platform: local toolchain, AWS / GitHub / Jira connectivity, and the Terraform bootstrap that every later iteration depends on. Hand-built; the agentic flow does not exist yet. See `docs/plan/PROJECT_PLAN.md` §9 (iteration 0) and `docs/setup/iteration-0-setup.md`.

## Scope

* Local toolchain verified by `tools/doctor.sh` ✅ (done 2026-10-06)
* AWS CLI via `aws login` (profile `idp`, ap-southeast-2) ✅
* GitHub CLI auth with workflow scope ✅
* Jira space IDP: work types Bug / Gate Hold, fields Severity / Found in phase, workflow To Do → Ready → In Progress → In Review → Done ✅
* Terraform `live/bootstrap`: state bucket + lock, GitHub OIDC provider, $25 budget
* Public GitHub repo `idp-platform`, first commit
* OIDC smoke workflow: GitHub Actions assumes an AWS role with no stored keys

## Exit criteria

* `tools/doctor.sh` all green
* A GitHub Actions run shows `aws sts get-caller-identity` succeeding via OIDC
* Claude Code can read and transition IDP issues via MCP

## Comments (1)

### Suyash Kunte, 2026-10-07T00:33:56.601+0530

**Iteration 0 complete: all exit criteria met.**

* `tools/doctor.sh`: all green
* GitHub Actions → AWS via OIDC (no stored keys): ✅ [run 37516007030](https://github.com/suyashkunte/idp-platform/actions/runs/37516007030). The role was assumed, and least privilege was confirmed (S3 access denied).
* Claude Code reads and transitions IDP issues via the Atlassian MCP: ✅ (this comment, plus the transition to Done)
* Bootstrap Terraform applied; state in `s3://idp-tfstate-736162637380-ap-southeast-2`; `terraform plan` reports no changes
* Repo: https://github.com/suyashkunte/idp-platform (commits 7c627f2, df6ba8f, 3ddc07f)

Learnings (Free-plan SCP → Paid plan + advanced features; GitHub immutable OIDC subjects) are in `docs/plan/iterations/00-setup-bootstrap.md`.
