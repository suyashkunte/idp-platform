from pathlib import Path

import pytest

from idp_gate import spec_trace
from idp_gate.cli import main

SPEC = """# IDP-42 spec
## Requirements
- **AC-1** first criterion
- **AC-2** second criterion
"""


def _repo(tmp_path: Path, tests: str) -> Path:
    (tmp_path / "specs" / "IDP-42").mkdir(parents=True)
    (tmp_path / "specs" / "IDP-42" / "spec.md").write_text(SPEC)
    (tmp_path / "pkg" / "tests").mkdir(parents=True)
    (tmp_path / "pkg" / "tests" / "test_x.py").write_text(tests)
    return tmp_path


@pytest.mark.ac("IDP-8:AC-1")
def test_all_acs_covered_passes(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        'import pytest\n@pytest.mark.ac("IDP-42:AC-1")\ndef test_a(): ...\n'
        '@pytest.mark.ac("IDP-42:AC-2", "OTHER-1:AC-9")\ndef test_b(): ...\n',
    )
    report = spec_trace.trace("IDP-42", repo)
    assert report.ok
    assert report.missing == []
    assert report.found["IDP-42:AC-1"] == [f"{repo / 'pkg/tests/test_x.py'}::test_a"]


@pytest.mark.ac("IDP-8:AC-1")
def test_missing_ac_is_reported_and_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, 'import pytest\n@pytest.mark.ac("IDP-42:AC-1")\ndef test_a(): ...\n')
    assert main(["spec-trace", "IDP-42", "--root", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "MISSING IDP-42:AC-2" in out
    assert "OK      IDP-42:AC-1" in out


@pytest.mark.ac("IDP-8:AC-1")
def test_unknown_ac_cited_by_test_fails(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        'import pytest\n@pytest.mark.ac("IDP-42:AC-1")\n@pytest.mark.ac("IDP-42:AC-2")\ndef test_a(): ...\n'
        '@pytest.mark.ac("IDP-42:AC-7")\nclass TestX: ...\n',
    )
    report = spec_trace.trace("IDP-42", repo)
    assert report.unknown == ["IDP-42:AC-7"]
    assert not report.ok


@pytest.mark.ac("IDP-8:AC-1")
def test_spec_without_acs_is_not_ok(tmp_path: Path) -> None:
    (tmp_path / "specs" / "IDP-1").mkdir(parents=True)
    (tmp_path / "specs" / "IDP-1" / "spec.md").write_text("# no criteria here\n")
    report = spec_trace.trace("IDP-1", tmp_path)
    assert not report.ok
    assert "NO ACCEPTANCE CRITERIA" in spec_trace.render(report)


def test_missing_spec_returns_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["spec-trace", "IDP-404", "--root", str(tmp_path)]) == 1
    assert "spec not found" in capsys.readouterr().err
