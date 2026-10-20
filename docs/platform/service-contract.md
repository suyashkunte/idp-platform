# Service contract: `idp.yaml` (schema `idp-service.v1`)

`idp.yaml` sits at the root of every tenant repo. It is the **only** place an application tells the platform who it is and how to
build, test, run and release it. It is validated by `idp validate` on every PR, against `schemas/idp-service.v1.json` and the
platform's catalog entry.

> **Status:** draft v1 (to be frozen when platform `v1.0.0` ships in iteration 11). Fields marked *(later)* are reserved extension points.

## Example (StudyTimer)
```yaml
apiVersion: idp.dev/v1
kind: Service
metadata:
  name: studytimer                  # DNS-safe; becomes namespace suffix, ECR repo, DB name, dashboards label
  owner: suyash                     # team or person; CODEOWNERS default
  tier: 1                           # 1|2|3 → policy profile, SLO strictness, canary pace
  tracker: { kind: jira, site: suyashkunte.atlassian.net, project: IDP, labels: [repo:studytimer] }
spec:
  type: web-api                     # web-api | worker | internal-api (later) | cron (later) | static-site (later)
  target: kubernetes                # kubernetes | lambda (later)
  build:
    profile: python-uv              # python-uv | dockerfile | node-pnpm (later) | go (later) | java-gradle (later)
    dockerfile: Dockerfile
    context: .
  runtime:
    port: 8000
    health: { live: /healthz/live, ready: /healthz/ready, startup: /healthz/startup }
    metrics: { path: /metrics }
    resources: { cpu: 250m, memory: 384Mi, memoryLimit: 512Mi }
    replicas: { dev: 1, int: 1, stg: 2, prod: 3 }
    autoscaling: { min: 3, max: 6, cpuTarget: 65 }      # prod only
    env: { LOG_LEVEL: info }                            # non-secret config; per-env overrides in chart-values/
  dependencies:
    postgres:
      enabled: true
      migrations: { command: "alembic upgrade head", downgrade: "alembic downgrade -1", policy: expand-contract }
    secrets: [SESSION_SECRET]                           # → SSM /idp/<env>/studytimer/SESSION_SECRET via ExternalSecret
  interfaces:
    openapi: openapi.json                               # used for diff (PR), Schemathesis (G2)
    contracts: { provider: false, consumers: [] }       # Pact roles (optional)
  tests:                                                # all via the Make contract; listed so gates know what to expect
    smoke: true          # make test-smoke   (required for G1)
    api: true            # make test-api     (G2)
    e2e: true            # make test-e2e     (G3)
    perf: true           # make test-perf    (G2 smoke / G3 load); false → platform generic HTTP probe
    critical_journeys: [sign-in, start-stop-timer, dashboard]
  delivery:
    slo: { availability: 0.999, p95_read_ms: 300, p95_write_ms: 800 }
    canary: { steps: [5, 25, 50, 100], min_requests: 500 }   # mechanism derived from spec.type
    kpis: []                                                 # optional PromQL ratios, e.g. checkout success
  gates:
    overrides:                                               # TIGHTEN ONLY: evaluator rejects any loosening
      G0: { diff_coverage_min: 0.85 }
  agent:
    protected_paths: [".github/**", "idp.yaml", "migrations/**", "specs/*/APPROVED"]
    risk_defaults: { "migrations/**": high, "src/**/auth/**": high }
```

## The Make contract (I2)
| Target | Required | Contract |
|---|---|---|
| `make lint` | yes | static checks; non-zero on findings |
| `make test` | yes | unit tests; writes `$(REPORTS_DIR)/junit-unit.xml`, `coverage.xml` (Cobertura) |
| `make test-component` | yes | component tests with real dependencies (testcontainers or similar) |
| `make verify` | yes | everything a PR must pass locally (CI calls this) |
| `make verify-fast` | recommended | quick subset (lint + unit tests); the agent's Stop hook calls it |
| `make spec-trace KEY=<KEY>` | yes | AC→test traceability (`idp spec-trace`); the Stop hook and verify call it |
| `make format FILES=...` | recommended | format only the given files; the agent's PostToolUse hook calls it |
| `make test-smoke` / `test-api` / `test-e2e` / `test-perf` | when `tests.*: true` | run against `BASE_URL`; write JUnit + `summary.json` into `REPORTS_DIR` |
| `make sbom` / `make sca` | no | the build profile provides defaults (`defaults.mk`, see [Build profile defaults](#build-profile-defaults)); python-uv writes `$(REPORTS_DIR)/sbom.cdx.json` (CycloneDX JSON) and `$(REPORTS_DIR)/sca.json` (pip-audit JSON) |

### How `idp validate` checks it
- `idp validate` with no argument validates `./idp.yaml`; `idp validate path/to/file.yaml` validates that file. The
  Makefile checked is always `Makefile` in the same directory as the validated file.
- **Unreadable `idp.yaml`.** A file that exists but cannot be read, is not valid UTF-8, or is nested too deeply to
  parse is reported as one violation with an empty `path` (shown as `<root>`) instead of a traceback, and exits `1`:
  `cannot read: <reason>` (e.g. `cannot read: Permission denied`),
  `cannot read: not valid UTF-8 (<reason> at byte <offset>)` or `cannot parse: nesting too deep`. Make checks are
  skipped, as for invalid YAML. A missing file is still exit `2` (see Exit codes).
- **Shadowing makefiles.** GNU make reads `GNUmakefile` and `makefile` before `Makefile`, so such a file would run
  instead of the validated one. When `Makefile` exists, every other entry in the service directory whose name,
  casefolded, is `gnumakefile` or `makefile` (e.g. `GNUmakefile`, `makefile`, `gnumakefile`, also a directory) is
  reported: one violation per entry, sorted by stored name, with `path` = the entry name and the message
  `GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it`. Only the exact name
  `Makefile` is exempt; names such as `Makefile.bak` or `common.mk` are not matched. If the directory cannot be listed,
  the check fails closed with `Makefile: cannot list the service directory`. Remedy: move the content into `Makefile`
  and delete or rename the other file.
- Checks, in this order: reading and parsing `idp.yaml` (above; on failure nothing else is checked), the
  `idp-service.v1` schema, then the Make contract: a missing Makefile is reported as a
  single `Makefile not found` violation (nothing else is checked); otherwise shadowing makefiles (above) first, then
  every target marked "yes" above (`lint`, `test`, `test-component`, `verify`, `spec-trace`), then `test-<kind>` for
  each of `smoke`, `api`, `e2e`, `perf` whose `spec.tests.<kind>` is `true`. Recommended targets (`verify-fast`,
  `format`) are not checked. Every missing target is reported, not only the first. Make checks also run when the schema
  check fails, but are skipped if the YAML cannot be parsed into a mapping.
- Targets are found by **static parsing**; `make` is never executed. The Makefile and every followed include are
  scanned **once**, and that one scan gives both the targets checked here and the include words `idp conformance`
  pins.
- **Makefiles are read in make's logical lines**, as GNU make's reader does, before anything else is looked at:
  - the text is split on LF only, and one CR before each LF is dropped (LF, CRLF and mixed files are accepted);
  - a physical line ending in an odd number of backslashes continues onto the next one (an even number is literal
    backslashes). This applies to every kind of line: assignments, rules, recipes, comments, `define` bodies and
    `endef` lines;
  - each joined line is then collapsed the way make collapses it before it recognises directives: the
    backslash-newline and the blanks after it become one space, and the blanks before a single `\` are dropped (with
    3 or more backslashes, (n-1)/2 literal backslashes stay). So `override \` + `define Y` reads `override define Y`,
    a line holding only `\` followed by `  endef` reads ` endef`, and `lint \` + `  verify:` reads `lint verify:`;
  - only then are comments removed (from the first unescaped `#`; `\#` is a literal hash). So a comment ending in `\`
    swallows the next line, in make and here: `# note \` + `verify:` (or `lint: # note \` + `verify:`) defines no
    `verify`, and `idp validate` reports `missing required target 'verify'`.
- A target counts when a logical line at column 0 names it before `:` or `::` (not `:=`, `::=`, `:::=`). Not counted:
  names listed only in `.PHONY:` or other special targets starting with `.`, pattern rules (`%`), names containing
  `$(...)`, variable assignments, target-specific variable lines (`name: VAR = x`, also with `:=`, `?=`, `+=`, `!=`,
  `export`/`override`), lines inside `define ... endef` (below), recipe (tab-indented) lines, and lines that start
  with a blank, also after a collapsed continuation (`\` + `verify:` reads ` verify:`; make defines `verify` there, the
  scanner fails closed and does not). Define required targets as plain column-0 rules. `include`, `-include` and
  `sinclude` are followed recursively for literal paths relative to the Makefile's directory; words with `$` or glob
  characters and files not on disk are skipped (`idp conformance` pins or rejects `$` words, see
  [Onboarding](onboarding.md#reference-example)). Conditionals (`ifeq`/`ifdef`/...) are not evaluated (targets in
  either branch count) and variables are not expanded. Rules whose target is `Makefile` or an included file (rules
  that would remake them) are not rejected by `idp validate`; `idp conformance` pins those files with `--assume-old`
  instead.
- **`define` blocks.** At top level, `define NAME` and `override define NAME` (also `define NAME = value`) open a
  block; a line starting with a tab does not (make tests the tab before collapsing, and after a rule it is a recipe
  line). `define := 1` and `export define ?= 3` assign a variable named `define`. Body lines are classified like
  make's `do_define`, on the collapsed line and without removing comments: after leading blanks, `endef` alone or
  followed by a blank (`endef # done`) closes the block; everything else is body text (`define#`,
  `override define B`, `export define B`, a tab-indented `define B`). Body lines are not scanned (no targets, no
  includes). Two kinds of line fail closed, one violation per line:
  - `define body in '<file>' has a line make reads differently in skipped conditional branches (nested define, endef followed by '#', or tab-indented endef); remove it`
    for a nested `define` (a body line that is `define` or starts with `define` and a blank), a body line starting
    with `endef#`, or a tab-indented `endef`. Reason: in a taken conditional branch make counts the nested `define` and
    ignores the other two, but in a skipped branch it stops at the first `endef` word without counting; the scanner
    does not evaluate conditionals. Scanning of the file continues. Remedy: define the inner variable in its own
    top-level block, write `endef # comment` (blank before `#`), and do not tab-indent `endef`.
  - `'<file>' has a define with export, unexport or private, which GNU make 3.81 and 4.x read differently; use define or override define`
    for a top-level define line with any modifier list other than one `override` (`export define X`,
    `private define X = 1`, `override export define X`). Reason: make 3.81 has no `private` and no `export define`
    and reads such a line as an assignment or `export` directive, while 4.x opens a block. The line opens no block and
    scanning continues. Remedy: `define X` ... `endef`, then `export X` on its own line.
- **Characters make reads differently.** Each scanned file is checked after UTF-8 decoding and before parsing, in
  this order, and the first offending character is named:
  - `'<file>' contains a line separator make does not use (<what>); use LF or CRLF line endings`, for a CR not
    followed by LF (`<what>` is `CR not followed by LF`) or U+000B, U+000C, U+001C-U+001E, U+0085, U+2028, U+2029
    (`<what>` is e.g. `U+0085`). Python would split lines there; make does not.
  - `'<file>' contains a control or space character make reads differently (<what>); use only spaces, tabs and LF or CRLF line endings`,
    for the C0 controls U+0000-U+0008 and U+000E-U+001B (including NUL) and every other character Python treats as
    whitespace but make does not (U+001F, U+00A0, U+1680, U+2000-U+200A, U+202F, U+205F, U+3000), e.g.
    `'Makefile' contains a control or space character make reads differently (U+00A0); use only spaces, tabs and LF or CRLF line endings`.
    Python would split words there that make reads as one. DEL, the other C1 controls, U+200B and U+FEFF are accepted.

  Such a file is not parsed (its targets and includes are not collected); like the read problems below, the violation
  counts toward the problem cap and other queued files are still scanned. Remedy: convert line endings to LF or CRLF,
  replace non-breaking or other Unicode spaces with plain spaces, and remove control characters (a recipe that needs
  one can produce it at run time, e.g. with `printf`).
- **No backslash on include lines.** An include line (a logical line whose first word, after collapsing and comment
  removal, is `include`, `-include` or `sinclude`) whose uncollapsed text contains a backslash anywhere, whether a
  line continuation (`-include common.mk \` followed by `  gen.mk`, or a line holding only `\` followed by
  `-include gen.mk`, which make reads as an include) or an escape (`-include gen\#.mk`, `x\ y.mk`), gives one
  violation per line:
  `include line in '<file>' uses a backslash (continuation or escape); write each include word literally on one line`,
  where `<file>` is `Makefile` or the include word of the file that holds the line. Reason: make unescapes and joins
  such lines, so the words it includes could differ from the ones checked and pinned. The words of such a line are not
  followed, and, like the read problems below, these violations replace the missing-target list. A backslash only
  inside a comment, or on a non-include line, is not flagged: `X = \` + `-include gen.mk` is one assignment, make
  includes nothing, and the scanner records nothing. Remedy: write each include word literally, on one line, or split
  a long list over several include lines.
- Reads are **confined to the service directory** (the directory of the validated `idp.yaml`): absolute include paths,
  includes escaping it via `..`, include words make expands to a home directory (a leading `~` or `~user`, also after
  leading `./` runs: `~/x.mk`, `./~/x.mk`, `.//~/x.mk`) and files whose real path (after symlinks) is outside it are
  not read and are reported, e.g. `include '../shared.mk' is outside the service directory`,
  `include './~/evil.mk' is outside the service directory` or `Makefile resolves outside the service directory`
  (a `~` elsewhere, as in `a~b.mk`, is literal). Each file is read up to 1 MiB (`'<name>' exceeds 1 MiB`) and at most
  64 files are read (`too many included files (limit 64)`). Unreadable, non-UTF-8 or symlink-loop files give
  `cannot read '<name>'`. Repeated include words are checked once; more than 1024 distinct include spellings (literal
  and `$` words together; `a.mk` and `./a.mk` count separately, even for one file) give
  `too many include words (limit 1024)`, and after 20 problems (backslash include lines, define and character
  violations included) scanning stops with `too many include problems (limit 20)`. Words echoed in messages are
  truncated to 200 characters (`…`). Includes outside the service directory, such as a shared `../common.mk` in a
  monorepo, are rejected even with `-include`; copy shared targets into the service directory instead.
  When any of these occur, only these problems are reported (the target list would be incomplete), in line order,
  after any shadowing-makefile violations.
- **Residual risk (what the scanner does not model).** `idp validate` and `idp conformance` are a fail-closed,
  best-effort correctness check, not a security boundary; the intended boundary is the conformance sandbox (IDP-23, not
  yet implemented) and least-privilege roles ([ADR-0013](../adr/0013-conformance-trust-model.md)). The scanner is a
  static model of GNU make's reader, not make itself (running `make -pn` in a sandbox is reconsidered after IDP-23
  (ADR-0013)). Not modelled:
  - include words that are globs without `$` (`include *.mk`) are skipped, neither scanned nor pinned;
  - includes produced by `$(eval ...)`, or by include lines inside `define` bodies that are later evaluated;
  - make's default include search path: a literal include not found beside the Makefile is looked up in directories
    such as `/usr/local/include` and `/usr/include`, which are never scanned (pinning stops a rule from creating it,
    but a file already there is read);
  - archive-member syntax in include words (`lib(x.mk)`) (follow-up);
  - make 4.x reader features `.RECIPEPREFIX`, `load`/`-load` and `guile`;
  - a tab-indented `define` at top level before any rule: make opens a block there, the scanner reads the body as
    ordinary lines, so it may credit targets make never defines (this fails open only for the target checks; make
    then fails at run time with `No rule to make target`);
  - make 4.x on macOS: which bytes make treats as blanks depends on the C library and locale; the character checks
    above model glibc, which CI uses.
- Text output: `<file>: valid (idp-service.v1.json)`, or one line per violation, e.g.
  `idp.yaml: Makefile: missing required target 'lint'`,
  `idp.yaml: GNUmakefile: GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it`,
  `idp.yaml: Makefile: include line in 'Makefile' uses a backslash (continuation or escape); write each include word literally on one line`
  or `idp.yaml: <root>: cannot read: Permission denied`.
- `--json` prints exactly one JSON line with keys `file`, `valid`, `schema`, `violations` (each `{path, message}`;
  schema violations use the dotted field path, Make violations use `Makefile`, except shadowing-makefile violations,
  whose `path` is the entry name, e.g. `GNUmakefile`; `idp.yaml` read and parse failures, like invalid YAML, use the
  empty path `""`):

```json
{"file": "idp.yaml", "valid": false, "schema": "idp-service.v1", "violations": [{"path": "Makefile", "message": "missing required target 'test-component'"}]}
```

- Exit codes: `0` valid, `1` violations found, `2` file not found or usage error (nothing on stdout, message on stderr,
  also with `--json`).

### Build profile defaults
The build profile named in `spec.build.profile` ([ADR-0012](../adr/0012-build-profiles.md)) ships a `defaults.mk` that
provides the optional targets (`sbom`, `sca` for `python-uv`). Include it through a variable:

```make
include $(IDP_PROFILE_DIR)/defaults.mk
```

- `IDP_PROFILE_DIR` is the profile directory: the `dir` printed by `idp profile show <profile> --json` (set by hand
  locally; in CI by the platform's setup step). Use the variable form: `idp validate` skips include words containing
  `$`, but rejects a literal include outside the service directory (e.g. an absolute path to the installed
  `defaults.mk`) as `include '...' is outside the service directory`. `idp conformance` pins exactly
  `$(IDP_PROFILE_DIR)/<literal file>` and fails any other `$` include word (see
  [Onboarding](onboarding.md#reference-example)).
- A target you define yourself (`sca: ...` with a recipe) replaces the default, with no make warnings, whether the
  include comes before or after your rule. Overriding one default does not affect the other.

Overridable variables (all `?=`; set them in the Makefile or on the command line):

| Variable | python-uv default |
|---|---|
| `IDP_SBOM_CMD` | export the locked runtime dependencies (`--no-dev`), then `cyclonedx-py requirements` → `$(REPORTS_DIR)/sbom.cdx.json` |
| `IDP_SCA_CMD` | export all locked dependency groups (dev included), then `pip-audit --disable-pip --requirement` → `$(REPORTS_DIR)/sca.json` |
| `IDP_CYCLONEDX_SPEC` | `cyclonedx-bom==7.5.0` (pinned; run with `uv tool run --exclude-newer '$(IDP_TOOLS_EXCLUDE_NEWER)' --from`) |
| `IDP_PIP_AUDIT_SPEC` | `pip-audit==2.10.1` (pinned; run with `uv tool run --exclude-newer '$(IDP_TOOLS_EXCLUDE_NEWER)' --from`) |
| `IDP_TOOLS_EXCLUDE_NEWER` | `2026-10-06T00:00:00Z` (fixed RFC 3339 UTC instant; passed single-quoted as `--exclude-newer` to `uv tool run`, so the tools' transitive dependencies resolve reproducibly; empty, more than one word or a single quote fails closed) |
| `REPORTS_DIR` | `reports` |
| `UV` | `uv` |

- The exports use `uv export --locked`: they fail if uv.lock is stale (run `uv lock`), and never change uv.lock or
  the project environment. SBOM = runtime dependencies (`IDP_SBOM_EXPORT_CMD`, `--no-dev`, into
  `IDP_SBOM_REQUIREMENTS`, default `$(REPORTS_DIR)/requirements.sbom.txt`), so it describes what ships. SCA = all
  groups, dev included, because dev tools run in CI (`IDP_EXPORT_CMD`, into `IDP_REQUIREMENTS`, default
  `$(REPORTS_DIR)/requirements.locked.txt`). SCA covers the CI platform only (Linux/CPython, matching the deploy
  target): dependencies conditional on other platforms are not audited. Network is used only when the recipes
  run (tool download, vulnerability database), never at parse time. Names `idp-default-*` and `_idp_*` are reserved.
- When you bump `IDP_CYCLONEDX_SPEC` or `IDP_PIP_AUDIT_SPEC`, move `IDP_TOOLS_EXCLUDE_NEWER` forward to a UTC instant
  after the new release too (a bare date is read in the local time zone); otherwise `uv tool run` cannot resolve the pin.
- `idp profile show <name> [--json]` prints the resolved profile (`profile.yaml` plus `dir`) as YAML, or as one JSON
  line with `--json`, and exits `0`. An invalid name, unknown or invalid profile, or missing profiles directory exits
  `2` with `profile show: ...` on stderr and nothing on stdout.

Caveats:
- A tenant that lists `sbom` or `sca` in `.PHONY` **without defining it** gets **no** default: make skips the
  pattern-rule fallback for phony targets, so `make sca` silently does nothing and exits 0. Only list these in `.PHONY`
  when you define them.
- A rule with prerequisites but no recipe (`sca: lint`) still gets the default recipe, and the default `sca` runs
  **before** `lint`.
- A Makefile with your own match-anything rule (`%:`) may conflict with the fallback.
- If `IDP_PROFILE_DIR` is unset, the include becomes `/defaults.mk` and make fails at the include.
- An empty `IDP_SBOM_CMD`/`IDP_SCA_CMD` fails closed: make stops with an error naming the variable instead of exiting
  0 without evidence. An empty `IDP_TOOLS_EXCLUDE_NEWER`, or one with more than one word or a single quote, fails
  the default `sbom`/`sca` the same way, even if you override the command. A failing command fails the target.
- `make sca` fails (non-zero exit) when pip-audit finds known vulnerabilities; read the findings in
  `reports/sca.json`. This is deliberate while no gate engine exists; once the policy/gate engine lands, `sca` becomes
  report-only and the gate decides, with severity thresholds and expiring waivers.
- Pipelines should check that `reports/sbom.cdx.json` and `reports/sca.json` exist (and are non-empty), not trust the
  exit code alone: a `.PHONY` listing or a tenant-defined target can exit 0 without writing evidence.

## Evidence formats (I3)
JUnit XML · Cobertura XML · SARIF 2.1 · CycloneDX JSON · `summary.json` (`test-summary.v1`: totals, pass rate by tag, failed tests with
`trace_id`). Tags are `p0`, `p1`, `critical`, `smoke`, `quarantine`, plus `ac:<KEY>:AC-n` for traceability. Non-Python stacks emit tags in test names
(`[p0]`) or JUnit properties; `idp evidence junit2summary` converts them.

## Compatibility rules
- Additive fields → minor version of the schema; removals or renames → `idp-service.v2`, with a migration in `idp validate --fix`.
- Unknown fields fail validation (catches typos); `x-*` fields are allowed for app-private use.
