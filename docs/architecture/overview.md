# Architecture overview

This document gives the high-level view. The platform (`idp-platform`) serves any number of tenant repos (StudyTimer is the first); see [../platform/service-contract.md](../platform/service-contract.md) for the interface between them. Decisions are in [../adr/](../adr/) and delivery sequencing is in [../plan/PROJECT_PLAN.md](../plan/PROJECT_PLAN.md).

## 1. From ticket to production

```mermaid
flowchart LR
  J[Jira ticket<br/>hardened template] -->|Atlassian MCP| CC[Claude Code in any tenant repo<br/>idp-agentic plugin: /implement-ticket]
  CC --> S[spec / plan / tasks]
  S -->|spec:guided| HA{{Human: make approve-spec}}
  S -->|spec:auto| T
  HA --> T[failing tests<br/>AC-tagged]
  T --> I[implement]
  I --> V[make verify]
  V --> R[reviewer subagents]
  R --> PR[Draft PR]
  PR --> CI[PR checks<br/>GitHub Actions]
  CI --> HB{{Human: approve + merge}}
  %% PR checks and G0-G5 run from idp-platform reusable workflows, parameterised by the tenant's idp.yaml
  HB --> G0[G0 build/sign]
  G0 --> G1[G1 dev smoke]
  G1 --> G2[G2 int cert]
  G2 --> G3[G3 stg cert]
  G3 --> G4{{G4 human decision<br/>GitHub Environment}}
  G4 --> G5[G5 canary in prod<br/>auto-abort]
  G0 & G1 & G2 & G3 -.HOLD.-> H[Jira Gate Hold<br/>→ owner fixes → new digest]
```

## 2. Platform components

```mermaid
flowchart TB
  subgraph GH[GitHub]
    WF[idp-platform reusable workflows @v1]
    T1[studytimer repo<br/>idp.yaml + idp.yml]
    T2[app #2 repo<br/>idp.yaml + idp.yml]
    T1 & T2 -->|uses| WF
  end
  subgraph AWS
    subgraph Shared[shared layer: always on]
      ECR[(ECR<br/>by digest + Sigstore sigs/attestations)]
      S3[(S3 evidence<br/>Object Lock)]
      RDS[(Aurora Serverless v2 PG<br/>gatekeeper + per-tenant DBs)]
      GK[Gatekeeper<br/>Lambda + HTTP API, IAM auth]
      SSM[(SSM Parameter Store)]
    end
    subgraph EKS[cluster layer: ephemeral]
      NS1[ns dev-&lt;svc&gt;]
      NS2[ns int-&lt;svc&gt;]
      NS3[ns stg-&lt;svc&gt;]
      NS4[ns prod-&lt;svc&gt;]
      ADD[ALB ctrl · ESO · Kyverno · Argo Rollouts]
      OBS[Prometheus · Loki · Tempo · Grafana · OTel]
    end
  end
  WF -->|OIDC AssumeRole per gate| ECR & GK & EKS
  GK --> RDS & S3
  ADD -->|verify sig + G3/G4 attestations| NS4
  NS1 & NS2 & NS3 & NS4 -->|ESO| SSM
  NS1 & NS2 & NS3 & NS4 --> RDS
  NS1 & NS2 & NS3 & NS4 --> OBS
```

## 3. Trust boundaries (summary; full threat model in iteration 3)
- **GitHub → AWS:** OIDC only, with each role's trust policy scoped to `repo:<owner>/<tenant-repo>:environment:<env>`. One role per tenant per gate, least privilege.
- **Artifact trust:** keyless cosign signatures and attestations made by the **platform's reusable workflows** on behalf of any tenant repo. Kyverno pins the signer to `idp-platform/.github/workflows/_g0-build.yml@refs/tags/v*` and checks the source repo against the catalog.
- **Tenant isolation:** OIDC roles, ECR repos, DB users, SSM paths and namespaces are per service (`modules/service-onboarding`); a tenant's workflow can only assume its own roles.
- **Evidence trust:** the Gatekeeper accepts evidence only from gate roles (SigV4); it verifies bundle hashes against the S3 WORM copy.
- **Agent trust:** the agent runs under your identity, inside permissions + hooks + rulesets. It has no AWS mutating rights and no merge or approve rights.
