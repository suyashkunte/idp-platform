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
It runs make as `make -C <dir> -f Makefile --assume-old=Makefile --assume-old=<word> ... verify`, so it reads only the
validated `Makefile`: `Makefile` and every literal include word the validation scan recorded (also words for files not
on disk, and a `./`-prefixed word additionally without its leading `./`) are pinned with `--assume-old`, so make neither
remakes them (for example `Makefile: evil.txt` or a rule that generates `-include gen.mk`) nor restarts with
unvalidated content. The Makefile is scanned once per example: the pinned words come from the same scan whose result
`idp validate` accepted, and that scan reads make's logical lines (continuations, comments and `define` bodies as make
reads them; see [How `idp validate` checks it](service-contract.md#how-idp-validate-checks-it)).

Include words containing `$` are pinned in one form only: `$(IDP_PROFILE_DIR)/<rest>` with a literal `<rest>` is
pinned as `--assume-old=<profile dir>/<rest>`, where `<profile dir>` is the resolved profile directory that is also
passed to make as `IDP_PROFILE_DIR=<profile dir>` (so `include $(IDP_PROFILE_DIR)/defaults.mk` is pinned; the
platform-owned `defaults.mk` itself is not scanned). Any other `$` word fails the example before make runs, naming the
first such word: `FAIL examples/<x>: dynamic include '<word>' cannot be pinned`. That covers other variables
(`$(OTHER)/x.mk`, `${IDP_PROFILE_DIR}/x.mk`, `$(IDP_PROFILE_DIR)x.mk`), `$$` (`a$$b.mk`), a `$` or glob character in
`<rest>` (`$(IDP_PROFILE_DIR)/$(X).mk`, `$(IDP_PROFILE_DIR)/*.mk`), an empty `<rest>`, and a `<rest>` that leaves the
profile directory (a `..` segment such as `$(IDP_PROFILE_DIR)/../x.mk`, or a leading `/`). Fix: include profile
files as `$(IDP_PROFILE_DIR)/<file>`, and anything else by a literal path inside the service directory. If the
`--assume-old=` arguments exceed 64 KiB, the example fails `include words exceed the make argument limit` without
running make.

Makefile problems fail the example as `FAIL examples/<x>: idp validate: <n> violation(s)` with one indented detail
line each, and make is not run. The ones specific to how make reads Makefiles, and their fixes (details in
[How `idp validate` checks it](service-contract.md#how-idp-validate-checks-it)):

| Detail (after `idp.yaml: Makefile: `) | Fix |
|---|---|
| `'<file>' contains a line separator make does not use (<what>); use LF or CRLF line endings` | convert the file to LF or CRLF line endings |
| `'<file>' contains a control or space character make reads differently (<what>); use only spaces, tabs and LF or CRLF line endings` | replace non-breaking/Unicode spaces with spaces; remove control characters (including NUL) |
| `include line in '<file>' uses a backslash (continuation or escape); write each include word literally on one line` | one literal include line per word list, no `\`, also not a continuation leading into the include |
| `define body in '<file>' has a line make reads differently in skipped conditional branches (nested define, endef followed by '#', or tab-indented endef); remove it` | no nested `define`; write `endef # comment`; do not tab-indent `endef` |
| `'<file>' has a define with export, unexport or private, which GNU make 3.81 and 4.x read differently; use define or override define` | `define X` ... `endef`, then `export X` on its own line |
| `include '<word>' is outside the service directory` (also `~/x.mk`, `./~/x.mk`) | copy the file into the service directory and include it by a relative path |
| `missing required target '<t>'` although the rule exists | the rule is on a line swallowed by a comment ending in `\`, inside a `define` body, or starts with a blank after a continuation: write it as a plain column-0 rule |

`idp validate` and `idp conformance` are a fail-closed, best-effort correctness check, not a security boundary; the
boundary is the conformance sandbox (IDP-23) and least-privilege roles
([ADR-0013](../adr/0013-conformance-trust-model.md)). Residual risk, now narrowed to what the static scan does not
model: glob include words without `$` are skipped, includes produced by `$(eval ...)` or by evaluated `define` bodies
are not scanned, `override IDP_PROFILE_DIR` or
`$(eval ...)` can make `$(IDP_PROFILE_DIR)` name another directory than the pinned one, and make's default include
directories, archive syntax (`lib(x.mk)`), `.RECIPEPREFIX`/`load`/`guile`, a top-level tab-indented `define` and
make 4.x on macOS are not modelled (see the residual-risk list in
[How `idp validate` checks it](service-contract.md#how-idp-validate-checks-it)). make's output is not bounded in
bytes, and the files can still change between the scan and make (TOCTOU, IDP-23). Examples are platform-owned and
reviewed. An example entry that is a symlink, or whose real path resolves outside DIR, is reported
`FAIL examples/<x>: outside examples directory` without running `idp validate` or make. An `idp.yaml` that cannot be
read, is not valid UTF-8 or is nested too deeply fails that example (`idp validate: 1 violation(s)` with the
`<root>: ...` detail) and the run continues with the remaining examples.
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
