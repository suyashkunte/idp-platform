# 0007. Keyless signing with Sigstore via GitHub OIDC

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Decision
Sign images and attest gate results with `cosign` keyless (Fulcio + Rekor) using the workflow's OIDC identity. Kyverno `verifyImages` uses keyless attestors pinned to issuer `https://token.actions.githubusercontent.com` and a subject equal to the **platform's reusable G0 workflow** (`https://github.com/<owner>/idp-platform/.github/workflows/_g0-build.yml@refs/tags/v*`). With reusable workflows, Fulcio certificates carry the called workflow (`job_workflow_ref`) as the identity, so every tenant's images are admissible only if they were built by the sanctioned platform pipeline. The calling repo is still checked through the certificate's source-repository extension, matched against the catalog. Gate attestations use predicate type `https://idp.dev/attestation/gate-result/v1`.
## Consequences
+ No key management or KMS cost; identity-bound signatures.
- Signing metadata goes to the public Rekor transparency log (it holds the repo and workflow names, not code). If that is unacceptable, switch to a KMS key (design doc default).
