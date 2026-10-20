"""IDP-31: ADR-0013 (conformance trust model) and the residual-risk texts that link it."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
TEMPLATE = ADR_DIR / "0000-template.md"
ADR_0013 = ADR_DIR / "0013-conformance-trust-model.md"

_HEADING = re.compile(r"^#{2,3} ")
_LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
_ADR_NAME = re.compile(r"^(\d{4})-.+\.md$")


def _headings(path: Path) -> list[str]:
    """The ``##``/``###`` heading lines of a file, in order."""
    return [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines() if _HEADING.match(line)]


def _flat(text: str) -> str:
    """Join wrapped lines and normalise whitespace."""
    return " ".join(text.split())


def _adr_section(lines: list[str], heading: str) -> str:
    """Flattened text from the single ``heading`` line up to the next ``#`` heading."""
    starts = [i for i, line in enumerate(lines) if line.rstrip() == heading]
    assert len(starts) == 1, f"{ADR_0013.name}: expected exactly one {heading!r} heading, found {len(starts)}"
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("#"):
            break
        body.append(line)
    return _flat("\n".join(body))


def _bullet(rel: str, prefix: str) -> str:
    """Flattened top-level bullet starting with ``prefix`` plus its indented continuation lines."""
    lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    assert len(starts) == 1, f"{rel}: expected exactly one line starting with {prefix!r}, found {len(starts)}"
    body = [lines[starts[0]]]
    for line in lines[starts[0] + 1 :]:
        if not line.startswith((" ", "\t")):
            break
        body.append(line)
    return _flat("\n".join(body))


def _paragraph(rel: str, marker: str) -> str:
    """Flattened blank-line-delimited paragraph that contains ``marker``."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    paragraphs = [_flat(p) for p in re.split(r"\n\s*\n", text)]
    found = [p for p in paragraphs if marker in p]
    assert len(found) == 1, f"{rel}: expected exactly one paragraph containing {marker!r}, found {len(found)}"
    return found[0]


def _missing(text: str, phrases: list[str]) -> list[str]:
    return [p for p in phrases if p not in text]


@pytest.mark.ac("IDP-31:AC-1")
def test_adr_0013_uses_template_headings_and_is_accepted() -> None:
    assert ADR_0013.is_file(), f"{ADR_0013.relative_to(ROOT)} does not exist"
    template_headings = _headings(TEMPLATE)
    assert template_headings == [
        "## Context and problem statement",
        "## Decision drivers",
        "## Considered options",
        "## Decision outcome",
        "### Consequences",
        "## Links",
    ]
    assert _headings(ADR_0013) == template_headings
    lines = ADR_0013.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# 0013. Conformance trust model"
    metadata = [line.rstrip() for line in lines if line.startswith("- **")][:3]
    assert metadata == [
        "- **Status:** Accepted",
        "- **Date:** 2026-10-20",
        "- **Deciders:** Suyash Kunte",
    ]


@pytest.mark.ac("IDP-31:AC-1")
def test_adr_0013_records_decision_rule_parked_tickets_and_make_db() -> None:
    assert ADR_0013.is_file(), f"{ADR_0013.relative_to(ROOT)} does not exist"
    lines = ADR_0013.read_text(encoding="utf-8").splitlines()
    decision = _adr_section(lines, "## Decision outcome")
    consequences = _adr_section(lines, "### Consequences")
    context = _adr_section(lines, "## Context and problem statement")
    assert (
        _missing(
            decision,
            [
                "fail-closed, best-effort correctness check",
                "`idp validate`",
                "conformance",
                "security boundary",
                "IDP-23",
                "least-privilege",
                "only taken on for a regression, or for a bypass in a job that holds credentials or runs code it"
                " didn't write",
            ],
        )
        == []
    )
    assert (
        _missing(
            consequences,
            ["IDP-29 and IDP-30 are parked", "`make -pn` in a sandbox", "reconsidered after IDP-23"],
        )
        == []
    )
    assert (
        _missing(
            context,
            ["IDP-22", "D3", "`platform-ci.yml`", "`examples/`", "arbitrary shell", "weigh scanner findings"],
        )
        == []
    )


def _residual_risk_text(rel: str) -> str:
    if rel == "docs/platform/service-contract.md":
        return _bullet(rel, "- **Residual risk")
    return _paragraph(rel, "Residual risk,")


@pytest.mark.ac("IDP-31:AC-2")
@pytest.mark.parametrize(
    "rel",
    ["docs/platform/service-contract.md", "docs/platform/onboarding.md"],
    ids=["service-contract", "onboarding"],
)
def test_residual_risk_text_links_adr_0013_and_states_no_security_boundary(rel: str) -> None:
    text = _residual_risk_text(rel)
    base = (ROOT / rel).parent
    targets = [t for t in _LINK_TARGET.findall(text) if "0013-" in t]
    assert targets != [], f"{rel}: residual-risk text has no link to ADR-0013"
    resolved = {(base / t.split("#", 1)[0]).resolve() for t in targets}
    assert resolved == {ADR_0013.resolve()}, f"{rel}: ADR-0013 link targets {targets} do not resolve to {ADR_0013}"
    sentences = [
        s for s in text.split(". ") if "not a security boundary" in s and "`idp validate`" in s and "conformance" in s
    ]
    assert len(sentences) >= 1, f"{rel}: no sentence names `idp validate`, conformance and 'not a security boundary'"


@pytest.mark.ac("IDP-31:AC-3")
def test_adr_numbers_are_unique_and_0013_is_the_trust_model() -> None:
    files = sorted(p.name for p in ADR_DIR.glob("*.md"))
    matches = [_ADR_NAME.match(name) for name in files]
    assert [name for name, m in zip(files, matches, strict=True) if m is None] == []
    numbers = [int(m.group(1)) for m in matches if m is not None]
    assert len(numbers) == len(set(numbers)), f"duplicate ADR numbers in {files}"
    assert numbers == list(range(len(numbers))), f"ADR numbers are not contiguous from 0000: {files}"
    assert [name for name in files if name.startswith("0013-")] == ["0013-conformance-trust-model.md"]
    bad_titles = [
        name
        for name in files
        if not (ADR_DIR / name).read_text(encoding="utf-8").splitlines()[0].startswith(f"# {name[:4]}.")
    ]
    assert bad_titles == []
