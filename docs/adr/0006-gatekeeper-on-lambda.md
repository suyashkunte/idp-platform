# 0006. Gatekeeper on Lambda; evidence in S3 Object Lock (governance mode)

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Context
The Gatekeeper must stay available while the cluster is torn down; gates must fail closed (design doc §4.6).
## Decision
Run the FastAPI Gatekeeper on AWS Lambda (Mangum adapter) behind an API Gateway HTTP API with IAM (SigV4) auth, inside the VPC, using **Aurora Serverless v2 PostgreSQL with min capacity 0 ACU** (auto-pause), which also hosts the per-environment app databases. Idle cost is storage only; first query after a pause takes about 15 s, so the gate client retries with backoff. Hold tickets are created by the workflow, not by the Lambda, so no internet egress is needed. Evidence goes to S3 with Object Lock in **governance** mode and a 7-day default retention, configurable to compliance mode.
## Consequences
+ Always available, cents per month, same API as the design doc.
- Cold starts (about 1–2 s) are well within the 5 s evaluation budget. Compliance-grade immutability is a deliberate opt-in.
