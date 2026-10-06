# 0003. Single ephemeral EKS cluster with namespace-per-environment

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Context
Design doc §9.1 uses separate DEV/INT/STG/PROD clusters. Each EKS control plane costs about $73/month; the budget is small.
## Decision
One EKS cluster with namespaces `dev`, `int`, `stg`, `prod`, each with quotas, a default-deny NetworkPolicy, PSA `restricted`, and per-namespace Kyverno rules (enforce only in `prod`). The cluster is created by `make env-up` and destroyed by `make env-down` and a nightly workflow. Persistent state (ECR, S3, RDS, Gatekeeper) lives in a separate always-on `shared` Terraform layer. No NAT gateway: a `t4g.nano` NAT instance (fck-nat) lives in the ephemeral cluster layer; the shared layer uses only the free S3 gateway endpoint. Region ap-southeast-2. Secrets come from SSM Parameter Store via External Secrets Operator.
## Consequences
+ About 70 % lower cost; re-creating the cluster is itself a recurring reproducibility test.
- STG and PROD share a control plane and nodes, so there is no topology-parity or blast-radius isolation. Documented as a known deviation; a second cluster for `prod` is a Terraform variable away.
