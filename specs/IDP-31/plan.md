# IDP-31: plan

## Approach
Smallest design: one new ADR, one sentence (with a link) in each of the two residual-risk texts, one CHANGELOG line,
and one small doc-structure test file so `idp spec-trace IDP-31` (run by `make verify`) finds a test per AC. No code
change, no change to ADRs 0001-0012, no protected path, no human task.

1. **Doc test first** (`tests/docs/test_adr_0013.py`, new package `tests/docs/__init__.py`). Stdlib only (`re`,
   `pathlib`), `ROOT = Path(__file__).resolve().parents[2]` as in `tests/ci/test_workflow_runners.py`. Helpers:
   - `_headings(path)`: the `##`/`###` heading lines of a file, in order.
   - `_flat(text)`: `" ".join(text.split())`, so wrapped lines and indentation do not matter.
   - `_section(lines, start_prefix)`: the lines from the first line starting with `start_prefix` up to the next
     heading (for the ADR) or the next blank line / next top-level bullet (for the docs); fails with a message naming
     the file when the start is not found exactly once.
   Tests (each tagged with `@pytest.mark.ac("IDP-31:AC-n")`):
   - `test_adr_0013_uses_template_headings_and_is_accepted` (AC-1): `_headings(0013) == _headings(0000-template)`
     and the list is non-empty; line 1 starts with `# 0013. `; the metadata lines are exactly
     `- **Status:** Accepted`, `- **Date:** 2026-10-20`, `- **Deciders:** Suyash Kunte`.
   - `test_adr_0013_records_decision_rule_parked_tickets_and_make_db` (AC-1): phrase checks on the flattened sections:
     - `## Decision outcome` (up to `### Consequences`): "fail-closed, best-effort correctness check", "`idp
       validate`", "conformance", "security boundary", "IDP-23", "least-privilege";
       the rule: "only taken on for a regression, or for a bypass in a job that holds credentials or runs code it
       didn't write";
     - `### Consequences`: "IDP-29 and IDP-30 are parked", "`make -pn` in a sandbox", "reconsidered after IDP-23";
     - `## Context and problem statement`: "IDP-22", "D3", "`platform-ci.yml`", "`examples/`", "arbitrary shell",
       "weigh scanner findings".
     One assertion per section, comparing the list of missing phrases with `[]`, so a failure names every missing
     phrase.
   - `test_residual_risk_text_links_adr_0013_and_states_no_security_boundary` (AC-2), parametrized over
     `("docs/platform/service-contract.md", "- **Residual risk")` and
     `("docs/platform/onboarding.md", "Residual risk,")`:
     - locate the text: the bullet (start line plus its indented continuation lines) or the paragraph (up to the next
       blank line);
     - every markdown link target in it matching `0013-` resolves, from the file's directory, to
       `ROOT / "docs/adr/0013-conformance-trust-model.md"`, and there is at least one;
     - split the flattened text into sentences on `. ` and require one sentence containing all of "not a security
       boundary", "`idp validate`" and "conformance".
   - `test_adr_numbers_are_unique_and_0013_is_the_trust_model` (AC-3): the 4-digit prefixes of `docs/adr/*.md` are
     unique and equal `range(0, len(files))` (contiguous from 0000; a later 0014 still passes); the 0013 file name is
     `0013-conformance-trust-model.md`; for every file, line 1 starts with `# <prefix>.` (the existing ADRs all do).
   Red first: all four fail before the docs exist (missing file / missing link).
2. **ADR** `docs/adr/0013-conformance-trust-model.md`, following the template exactly (title, three metadata
   bullets, the six headings). Planned content:
   - `## Context and problem statement`: IDP-22 and IDP-28 hardened the static Makefile scanner over four review
     rounds; each found another disagreement with GNU make, and IDP-29/IDP-30 would continue. IDP-22 D3 already said
     `idp validate` is not a security boundary for tenant content. Why: in `platform-ci.yml` a PR's own root
     `Makefile` and its own copy of the scanner run in the same job (`contents: read`, no stored credentials), so a
     malicious PR would change them rather than get past them; `examples/` is written by the platform team (IDP-23);
     the validated `verify` recipe is arbitrary shell anyway. The real protections are the conformance sandbox
     (IDP-23: minimal environment, process cleanup, no stored credentials) and per-tenant, least-privilege AWS roles
     (iteration 3). Agreed with the human on 2026-10-20; recorded so that reviews and tickets weigh scanner findings
     accordingly.
   - `## Decision drivers`: a static model of make cannot match make exactly (each round found more); cost of each
     round versus the risk it removes; where an attacker actually is in each job; consistent weighting of review
     findings; keep the fast, fail-closed feedback for honest mistakes.
   - `## Considered options`: (1) keep treating the scanner as a security boundary and keep hardening it (IDP-29,
     IDP-30 and more); (2) treat it as a fail-closed, best-effort correctness check and put the boundary in the
     sandbox and roles (chosen); (3) replace the static scan with make's own database (`make -pn`) now (rejected
     for now: make evaluates `$(shell ...)` and `!=` at parse time, so this runs tenant code and needs the IDP-23
     sandbox first); (4) remove the scanner (rejected: loses fast, specific feedback on contract mistakes).
   - `## Decision outcome`: option 2. "`idp validate` and the conformance scan are a fail-closed, best-effort
     correctness check, not a security boundary. The security boundary is the conformance sandbox (IDP-23) plus
     least-privilege roles." The rule, verbatim from the ticket: new scanner-hardening work is only taken on for a
     regression, or for a bypass in a job that holds credentials or runs code it didn't write. Existing checks stay
     and keep failing closed; this ADR changes no behaviour. Reading of "runs code it didn't write" per spec Q6.
   - `### Consequences`: IDP-29 and IDP-30 are parked. Using make's own database (`make -pn` in a sandbox) is
     reconsidered after IDP-23. Scanner findings in reviews are weighed as correctness findings unless the rule
     applies. The residual-risk lists in the service contract and onboarding docs stay as documentation of known
     gaps, not as a backlog. The iteration-3 threat model builds on this ADR. Negative: a bypass found in a
     credential-free job stays open until it matters under the rule; if a job starts to hold credentials or run
     code it did not write (for example tenant conformance with deploy roles), the rule makes those bypasses in
     scope again.
   - `## Links`: [IDP-22 spec](../../specs/IDP-22/spec.md) (decision D3), [IDP-28 spec](../../specs/IDP-28/spec.md),
     [service contract: How `idp validate` checks it](../platform/service-contract.md#how-idp-validate-checks-it),
     [Onboarding: Reference example](../platform/onboarding.md#reference-example),
     [`platform-ci.yml`](../../.github/workflows/platform-ci.yml), [ADR-0010](0010-service-contract.md),
     [ADR-0012](0012-build-profiles.md); tickets IDP-23, IDP-29, IDP-30 by key (no tracker URLs in the repository).
3. **Docs** (AC-2). The same sentence in both files, at the start of the residual-risk text:
   `` `idp validate` and `idp conformance` are a fail-closed, best-effort correctness check, not a security boundary;
   the boundary is the conformance sandbox (IDP-23) and least-privilege roles
   ([ADR-0013](../adr/0013-conformance-trust-model.md)). ``
   - service-contract.md: inserted right after `**Residual risk (what the scanner does not model).**`; the clause
     "running `make -pn` in a sandbox is an ADR candidate after IDP-23" becomes "running `make -pn` in a sandbox is
     reconsidered after IDP-23" (Q3). Nested list unchanged.
   - onboarding.md: inserted before "Residual risk, now narrowed to ..." as the paragraph's first sentence.
4. **CHANGELOG**: one line under `[Unreleased]` / `### Added`:
   `- IDP-31: ADR-0013 conformance trust model: \`idp validate\` and the conformance scan are a fail-closed,
   best-effort correctness check, not a security boundary (that is the IDP-23 sandbox plus least-privilege roles);
   scanner hardening only for regressions or bypasses in jobs that hold credentials or run code they didn't write;
   IDP-29/IDP-30 parked. The service contract and onboarding residual-risk texts link it.`

## Changes
| File | Change |
|------|--------|
| `tests/docs/__init__.py` | new, empty (package, like `tests/ci/`) |
| `tests/docs/test_adr_0013.py` | new: four tests tagged `IDP-31:AC-1`..`AC-3` |
| `docs/adr/0013-conformance-trust-model.md` | new ADR, template headings, status Accepted |
| `docs/platform/service-contract.md` | residual-risk bullet: one sentence with the ADR-0013 link; `make -pn` clause reworded |
| `docs/platform/onboarding.md` | residual-risk paragraph: the same sentence with the link |
| `CHANGELOG.md` | one IDP-31 line under `[Unreleased]` / `### Added` |
| `docs/adr/0001`-`0012` | unchanged (Q2) |

## Interfaces and data
None. No CLI, schema, config or API change. The doc test reads repository files only.

## Telemetry
None (documentation only).

## Risks, rollout and rollback
- Risk: the doc test is brittle against later rewording. Mitigation: phrases are few and checked on flattened text;
  failures list the missing phrases and the file. Future tickets that reword these texts update the test with them.
- Risk: the AC-2 locator (leading words of the residual-risk text) changes in a later ticket. The test then fails with
  a clear "not found" message naming the file, rather than passing silently.
- Risk: the ADR is read as a licence to ignore all scanner findings. Mitigation: the decision states that existing
  checks stay fail-closed and that regressions are always fixed; the rule names when bypasses are in scope.
- Rollout: merge with the PR; the human's PR approval is the ADR acceptance (ADR-0001).
- Rollback: revert the commit(s). A later change of the decision needs a new ADR that supersedes 0013 (ADR-0001).
