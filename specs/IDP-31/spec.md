---
ticket: IDP-31
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: auto
---

# IDP-31: ADR-0013: conformance trust model (the Makefile scanner is a correctness check, not a security boundary)

## Context
IDP-22 and IDP-28 hardened the static Makefile scanner (`idp validate`, and the scan inside `idp conformance`) over
four review rounds. Each round found another place where the scanner and GNU make disagree, and IDP-29 and IDP-30
would continue that. IDP-22 decision D3 already concluded that `idp validate` "is not a security boundary for tenant
content". The human agreed on 2026-10-20 to record this as an ADR, so that future reviews and tickets weigh scanner
findings as correctness findings, not as security findings. Documentation only. Labels: component:pipeline,
repo:idp-platform, risk:low, spec:auto. Parent: IDP-16.

Facts checked in the repository (2026-10-20, branch `feature/IDP-31-conformance-trust-adr`, at 88c2d63):
- `docs/adr/` holds `0000-template.md` and `0001`-`0012`, one file per number, no gaps and no duplicates. 0013 is
  free.
- `docs/adr/0000-template.md` has the title line `# 0000. ADR template`, the metadata bullets `- **Status:**`,
  `- **Date:**`, `- **Deciders:**`, and the headings, in order: `## Context and problem statement`,
  `## Decision drivers`, `## Considered options`, `## Decision outcome`, `### Consequences`, `## Links`.
- No existing ADR uses the template headings, a `## Links` section or "Related" links. Only 0001 is `Accepted`;
  0004 is superseded, the others are `Proposed`. ADR-0001: "Agents may draft ADRs (doc-upkeeper); humans accept them
  in PR review."
- `.github/workflows/platform-ci.yml`: one job `verify` with `permissions: contents: read`. It checks out the PR, runs
  `uv sync` and `make verify` (the PR's own root `Makefile` and its own `idp-gate`, including `idp conformance
  examples`). No stored secrets are used.
- `docs/platform/service-contract.md`, section "How `idp validate` checks it": the bullet
  `**Residual risk (what the scanner does not model).**` (line 182) says "running `make -pn` in a sandbox is an ADR
  candidate after IDP-23". `docs/platform/onboarding.md`, section "Reference example": the paragraph starting
  `Residual risk, now narrowed to what the static scan does not model:` (line 65). Neither links an ADR or says
  "security boundary".
- `specs/IDP-22/spec.md` D3: "`idp validate` is not a security boundary for tenant content; the conformance
  assume-old pinning (AC-5) is the guarantee that the validated file is what runs".
- `idp spec-trace` (`packages/idp-gate/src/idp_gate/spec_trace.py`) needs at least one test tagged
  `@pytest.mark.ac("IDP-31:AC-n")` for every AC. `make verify` runs it for the branch's key, so a docs-only ticket
  still needs a test per AC. Precedents for doc tests: `tests/ci/test_workflow_runners.py` (IDP-12, repository-level
  checks under `tests/`) and `test_adr_0012_known_gaps_state_sync_build_limit` in
  `packages/idp-gate/tests/test_profiles.py` (IDP-25, phrase checks on an ADR with wrapped lines joined).

## Requirements
- **AC-1** Given `docs/adr/0013-conformance-trust-model.md`, then it uses the headings of `docs/adr/0000-template.md`, has status Accepted, and records:
    - the decision: `idp validate` and the conformance scan are a fail-closed, best-effort correctness check, and the security boundary is IDP-23 plus least-privilege roles;
    - the rule that new scanner-hardening work is only taken on for a regression, or for a bypass in a job that holds credentials or runs code it didn't write;
    - that IDP-29 and IDP-30 are parked;
    - that using make's own database (`make -pn` in a sandbox) is reconsidered after IDP-23.
  - "Uses the headings": the `##`/`###` headings of 0013 are exactly the template's, in the same order:
    `## Context and problem statement`, `## Decision drivers`, `## Considered options`, `## Decision outcome`,
    `### Consequences`, `## Links`. No other `##`/`###` headings (ASSUMPTION A1). The title line is
    `# 0013. Conformance trust model` (ADR numbering convention), followed by the template's three metadata bullets:
    `- **Status:** Accepted`, `- **Date:** 2026-10-20` (the day the human agreed the decision), `- **Deciders:**
    Suyash Kunte`.
  - Status Accepted (ASSUMPTION A2): the agent writes `Accepted` because the AC requires it. Per ADR-0001 the human
    accepts it by approving the PR; until merge the file is a draft.
  - Where the four points live:
    - the decision and the rule in `## Decision outcome`;
    - "IDP-29 and IDP-30 are parked" and "`make -pn` in a sandbox is reconsidered after IDP-23" in `### Consequences`.
  - The context section also records why (from the ticket, the human's 2026-10-20 agreement and IDP-22 D3):
    - in `platform-ci.yml` the PR's own root `Makefile` and its own copy of the scanner run in the same job, so a
      malicious PR would change them rather than get past them;
    - `examples/` is written by the platform team (IDP-23);
    - the validated `verify` recipe is arbitrary shell anyway;
    - the real protections are the conformance sandbox (IDP-23: minimal environment, process cleanup, no stored
      credentials) and per-tenant, least-privilege AWS roles (iteration 3);
    - reviews should weigh scanner findings accordingly.
  - The decision keeps today's scanner behaviour: existing checks stay and keep failing closed (no code change).
  - Verified by `tests/docs/test_adr_0013.py`: heading sequence equal to the template's (both files parsed, so a
    template change is caught), the exact status line, and required phrases per section (wrapped lines joined,
    whitespace normalised; phrase list in plan.md).
- **AC-2** Given the residual-risk text in `docs/platform/service-contract.md` and `docs/platform/onboarding.md`, then each links ADR-0013 and says in one sentence that validation and conformance are not a security boundary.
  - "Residual-risk text": the `**Residual risk (what the scanner does not model).**` bullet in service-contract.md and
    the `Residual risk, ...` paragraph in onboarding.md (both identified above).
  - Each gets the same one sentence, added at the start of that text (ASSUMPTION A3; wording in plan.md):
    `` `idp validate` and `idp conformance` are a fail-closed, best-effort correctness check, not a security boundary;
    the boundary is the conformance sandbox (IDP-23) and least-privilege roles
    ([ADR-0013](../adr/0013-conformance-trust-model.md)). ``
  - The link target is relative (`../adr/0013-conformance-trust-model.md` from `docs/platform/`) and resolves to the
    new file.
  - In service-contract.md the stale clause "running `make -pn` in a sandbox is an ADR candidate after IDP-23" is
    reworded to "is reconsidered after IDP-23 (ADR-0013)" (Q3). The list of what the scanner does not model is not
    changed.
  - Verified by `tests/docs/test_adr_0013.py`: in each file, the residual-risk text (bullet or paragraph, wrapped lines
    joined) contains a markdown link whose target resolves (from that file's directory) to
    `docs/adr/0013-conformance-trust-model.md`, and contains the phrase "not a security boundary" inside one sentence
    that also names validation and conformance.
- **AC-3** (edge) Given the existing ADRs 0001–0012, then none changes except for added "Related" links, and 0013 is the next free number (no clash).
  - The ticket writes the edge marker after the bold id; it stays outside the bold so `idp spec-trace` parses it.
    Meaning unchanged.
  - Planned change to ADRs 0001-0012: none (Q2). AC-3 allows "Related" links but does not require them, and the
    service-contract doc (which ADR-0010 points to) already links 0013 via AC-2.
  - "Next free number": `docs/adr/` has exactly one file per number, the numbers are contiguous from 0000, and
    `0013-conformance-trust-model.md` is the only 0013 file. Its title line starts with `# 0013.`.
  - "None changes": checked in the implementation task with `git diff --stat origin/main... -- docs/adr/` (only the
    new 0013 file), and visible in the PR diff. Not a permanent test (ASSUMPTION A4, Q1): a test that compares ADRs
    0001-0012 to a baseline would fail every later ticket that legitimately adds implementation notes (as IDP-21,
    IDP-24 and IDP-25 did to ADR-0012).
  - Verified by `tests/docs/test_adr_0013.py` (numbering: unique, contiguous, 0013 present once with a matching title
    number; written so a later 0014 still passes) plus the `git diff --stat` evidence recorded in the PR.

## Edge cases and assumptions
- The ADR text wraps at 120 characters like the other docs. The phrase checks join wrapped lines and normalise
  whitespace (as the ADR-0012 test does), so rewrapping does not break them.
- Markdown in the phrase checks: required phrases are checked against the text with backticks kept (for example
  `` `make -pn` ``). The test strips nothing else.
- A later ADR (0014+) must not break the AC-3 test: it checks uniqueness, contiguity and that 0013 is the trust-model
  file, not that 0013 is the highest number.
- A later edit to the residual-risk text (for example IDP-23 narrowing it) keeps the AC-2 test green as long as the
  link and the sentence stay. The test locates the text by its leading words (`**Residual risk` bullet,
  `Residual risk,` paragraph); if the leading words change, the test fails with a message naming the file.
- IDP-29 and IDP-30 are cited by key plus their Jira title (in the ADR's Links section). The repository has no other
  text about them, and the ADR does not describe their content beyond that (Q4).
- IDP-32 (review triage rule) is a separate ticket and is not mentioned or implemented here (instruction from the
  2026-10-20 agreement).
- ASSUMPTION A1: "uses the headings of the template" means the same `##`/`###` headings in the same order, with no
  extra headings; the title and metadata bullets follow the template's form.
- ASSUMPTION A2: the agent writes `- **Status:** Accepted`; human acceptance is the PR approval (ADR-0001).
- ASSUMPTION A3: the AC-2 sentence goes at the start of each residual-risk text, and the same wording is used in both
  files.
- ASSUMPTION A4: the "unchanged" part of AC-3 is shown by the PR diff and a recorded `git diff --stat`, not by a
  permanent test.
- ASSUMPTION A5: the doc test lives under `tests/docs/` (new package with `__init__.py`), next to `tests/ci/`
  (repository-level checks), not inside `packages/idp-gate/tests/` (it tests no package code).

## Non-functional requirements
- Documentation only: no change under `packages/**/src`, `build-profiles/**`, `examples/**` or
  `tests/conformance/**`. Scanner and conformance behaviour unchanged; every existing test passes unchanged.
- `make verify` green, including `idp spec-trace IDP-31` (one tagged test per AC), ruff on the new test file and
  `idp test-quality-lint` on it (every test asserts; no sleeps).
- No new dependencies (stdlib `re` and `pathlib` only). `pyproject.toml` and `uv.lock` unchanged.
- Protected paths unchanged: root `Makefile`, root `pyproject.toml`, `.github/**`, `.pre-commit-config.yaml`,
  `infra/**`, plugin hooks, `.claude-plugin/**`, `.claude/settings.json`. No human task.
- Every relative link added in the ADR and the two docs resolves to an existing file (checked by hand per the ticket's
  test approach; the AC-2 links also by the test).

## Out of scope
- Changing scanner behaviour.
- Implementing IDP-23.
- The iteration-3 threat model (`docs/architecture/threat-model.md`), which will build on this ADR.
- The review triage rule (IDP-32).
- Commenting on IDP-29 and IDP-30 ("parked per ADR-0013"): done by the human when the ticket was created.
- Changing reviewer agent prompts (`plugins/idp-agentic/agents/**`) to apply the rule (Q5).
- Editing approved specs (`specs/IDP-22/*`, `specs/IDP-28/*`).

## Open questions
- Q1: Should AC-3's "none changes" also be a permanent automated test (for example a `git diff origin/main` check
  that allows only added `Related` lines)? Proposed: no (A4). On main it compares main with itself, and on later
  branches it would block legitimate ADR edits. The PR diff and a `git diff --stat` recorded in the PR are the
  evidence. Alternative: a test that skips when `origin/main` is missing and only runs on this branch (fragile).
- Q2: Add a "Related: ADR-0013" link to any existing ADR? Proposed: none (smallest change; AC-3 allows but does not
  require it). Candidate if wanted: one line `Related: [ADR-0013](0013-conformance-trust-model.md)` at the end of
  ADR-0010 (service contract), whose Make contract the scanner checks.
- Q3: service-contract.md says "running `make -pn` in a sandbox is an ADR candidate after IDP-23". Now that ADR-0013
  records it, reword to "is reconsidered after IDP-23 (ADR-0013)"? Proposed: yes (keeps the doc accurate; one
  clause). Alternative: leave it unchanged (strictly smaller diff, but stale).
- Q4: Should the ADR name what IDP-29 and IDP-30 cover? Proposed: no; cite them as "further scanner-hardening
  tickets" by key. Please supply one-line titles if you want them recorded.
- Q5: Should the reviewer agents (`plugins/idp-agentic/agents/`) be told to weigh scanner findings per ADR-0013?
  Proposed: not here; it belongs with the review triage rule (IDP-32).
- Q6: The rule says "a bypass in a job that holds credentials or runs code it didn't write". Proposed ADR reading:
  a job "runs code it didn't write" when the Makefile or scanner it executes does not come from the same change that
  is being checked (for example a platform job running conformance on a tenant repository, or a tenant pipeline
  running the platform's scanner on tenant code). Today's `platform-ci.yml` job is neither (no credentials, and it
  runs the PR's own scanner on the PR's own files). Please confirm this reading.

## Decisions (orchestrator, pending human approval at PR)
- Q1: no permanent test for AC-3's "none changes"; the PR diff and a recorded `git diff --stat` are the evidence (A4).
- Q2: no "Related" links added to ADRs 0001-0012.
- Q3: reworded; service-contract.md now says `make -pn` in a sandbox "is reconsidered after IDP-23 (ADR-0013)".
- Q4: IDP-29 and IDP-30 are cited by key plus their Jira title, without further description of their content.
- Q5: not here; reviewer agent prompts belong with the review triage rule (IDP-32).
- Q6: the spec's reading of "runs code it didn't write" is used, and the ADR now also defines "holds credentials"
  (repository or organisation secrets, `id-token: write`, a write-scoped `GITHUB_TOKEN`, cloud credentials, or a
  developer or agent workstation environment).

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | tests/docs/test_adr_0013.py::test_adr_0013_uses_template_headings_and_is_accepted, tests/docs/test_adr_0013.py::test_adr_0013_records_decision_rule_parked_tickets_and_make_db |
| AC-2 | tests/docs/test_adr_0013.py::test_residual_risk_text_links_adr_0013_and_states_no_security_boundary |
| AC-3 | tests/docs/test_adr_0013.py::test_adr_numbers_are_unique_and_0013_is_the_trust_model (plus the `git diff --stat origin/main... -- docs/adr/` evidence in the PR) |
