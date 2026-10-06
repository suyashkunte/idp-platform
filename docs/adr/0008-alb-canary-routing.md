# 0008. ALB traffic routing for Argo Rollouts canaries

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Context
Design doc §10 uses NGINX ingress; upstream ingress-nginx has since been retired.
## Decision
Use the AWS Load Balancer Controller with one shared ALB (IngressGroup), and Argo Rollouts `trafficRouting.alb` for weighted canaries. The `track` label comes from Rollouts pod metadata and is copied onto telemetry by the OTel Collector / PodMonitor (design doc §10.1 design note).
## Consequences
+ Native AWS, one load balancer for all environments.
- ALB weights apply to north-south traffic only; internal canary patterns follow design doc §10.6.
