import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from idp_gate import contract
from idp_gate.cli import main

DOC = Path(__file__).resolve().parents[3] / "docs" / "platform" / "service-contract.md"


def _doc_example() -> dict[str, Any]:
    """The StudyTimer example in the public docs is the contract's reference document."""
    match = re.search(r"```yaml\n(.*?)```", DOC.read_text(), re.DOTALL)
    assert match, "no yaml example in service-contract.md"
    data: dict[str, Any] = yaml.safe_load(match.group(1))
    return data


@pytest.mark.ac("IDP-9:AC-1")
@pytest.mark.ac("IDP-8:AC-5")
def test_documented_example_is_valid() -> None:
    assert contract.validate_document(_doc_example()) == []


@pytest.mark.ac("IDP-9:AC-2")
def test_unknown_fields_rejected_but_x_extensions_allowed() -> None:
    doc = _doc_example()
    doc["spec"]["runtme"] = {}
    doc["spec"]["x-team-notes"] = "allowed"
    messages = [str(v) for v in contract.validate_document(doc)]
    assert len(messages) == 1
    assert "spec:" in messages[0]
    assert "'runtme' does not match any of the regexes: '^x-'" in messages[0]


@pytest.mark.ac("IDP-9:AC-3")
@pytest.mark.parametrize(
    ("field", "value"),
    [("name", "Study_Timer"), ("name", "-bad"), ("tier", 0), ("tier", 4)],
)
def test_metadata_name_and_tier_rules(field: str, value: Any) -> None:
    doc = copy.deepcopy(_doc_example())
    doc["metadata"][field] = value
    violations = contract.validate_document(doc)
    assert [v.path for v in violations] == [f"metadata.{field}"]


@pytest.mark.ac("IDP-9:AC-4")
def test_unknown_build_profile_lists_allowed_values() -> None:
    doc = _doc_example()
    doc["spec"]["build"]["profile"] = "maven"
    [violation] = contract.validate_document(doc)
    assert violation.path == "spec.build.profile"
    assert "python-uv" in violation.message
    assert "dockerfile" in violation.message


@pytest.mark.ac("IDP-8:AC-5")
def test_cli_validate_reports_violation_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good, bad = tmp_path / "good.yaml", tmp_path / "bad.yaml"
    good.write_text(yaml.safe_dump(_doc_example()))
    broken = _doc_example()
    del broken["spec"]["runtime"]["port"]
    bad.write_text(yaml.safe_dump(broken))
    assert main(["validate", str(good)]) == 0
    assert main(["validate", str(bad)]) == 1
    assert "spec.runtime: 'port' is a required property" in capsys.readouterr().out


def test_invalid_yaml_and_missing_file(tmp_path: Path) -> None:
    broken = tmp_path / "idp.yaml"
    broken.write_text("a: [unclosed\n")
    assert "invalid YAML" in str(contract.validate_file(broken)[0])
    assert main(["validate", str(tmp_path / "nope.yaml")]) == 2
