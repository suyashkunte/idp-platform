# Onboarding an application

Target: **a new or existing application in < 1 day, with no changes to platform code.**

## New application
```bash
uv tool install idp-gate                          # provides the `idp` CLI
copier copy gh:<owner>/idp-platform --vcs-ref v1 --trust my-app   # pick template: python-fastapi | dockerfile-generic
cd my-app && idp onboard                          # interactive: name, tier, type, tracker → opens a PR in idp-platform
                                                  # adding catalog/services/my-app.yaml
```
Merging that catalog PR (human) runs `catalog-apply.yml`, which provisions ECR, OIDC roles, the database, SSM paths and namespaces.
Then push `my-app`; its first PR runs the full pipeline, with gates in **shadow mode**.

## Existing application
1. Add `idp.yaml` (`idp init` infers a draft from the repo: language, Dockerfile, port, test dirs).
2. Implement the Make contract (thin wrappers around the app's existing commands are fine).
3. Meet the runtime contract: health endpoints, JSON logs, `/metrics`, `OTEL_*` env vars. `idp doctor --runtime` checks a running container.
4. Add `.github/workflows/idp.yml` (10 lines), `.claude/settings.json` (enable the plugin) and `CLAUDE.md`.
5. `idp onboard` → catalog PR → shadow mode → review hold rates for 2 weeks → set `gates.mode: enforced` in the catalog (§7.1 rollout rule).

## Reference example
[`examples/minimal-service/`](../../examples/minimal-service/README.md) is the smallest service that passes
`idp validate` and `make verify` with the `python-uv` profile defaults: stdlib health endpoints
(`/healthz/{live,ready,startup}`), an `idp.yaml` and a Makefile that includes `$(IDP_PROFILE_DIR)/defaults.mk`. It is a
conformance fixture, not a template: start new applications from the templates above.

`make conformance` at the platform root runs `idp conformance examples`: for every `examples/*/` with an `idp.yaml` it
runs `idp validate`, resolves the build profile and runs `make verify` (with `IDP_PROFILE_DIR` set to the resolved
profile directory), printing one `PASS`/`FAIL` line per example and a summary; it exits non-zero if any example fails.
`make verify` includes `make conformance`, so platform CI catches platform changes that would break tenants.

## Readiness checklist (design doc Appendix B.3, adapted)
- [ ] `idp validate` passes; catalog entry merged
- [ ] Make contract targets present; `make verify` green locally
- [ ] Runtime contract verified by `idp doctor --runtime`
- [ ] Smoke suite ≤ 25 tests; critical journeys listed in `idp.yaml`
- [ ] SLOs declared; dashboards appear automatically (filtered by `service`)
- [ ] Canary mechanism resolved for `spec.type` (§10.6)
- [ ] Shadow results reviewed; owner SLAs for holds agreed
- [ ] `/implement-ticket` dry run on one low-risk ticket reaches a draft PR
