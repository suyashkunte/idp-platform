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


# --- IDP-13: `idp spec-trace --json` -------------------------------------------------------------------------------

COVERED_TESTS = (
    'import pytest\n@pytest.mark.ac("IDP-42:AC-1")\ndef test_a(): ...\n'
    '@pytest.mark.ac("IDP-42:AC-2", "OTHER-1:AC-9")\ndef test_b(): ...\n'
)


@pytest.mark.ac("IDP-13:AC-1")
def test_json_all_covered_prints_object_and_exits_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, COVERED_TESTS)
    test_file = f"{repo}/pkg/tests/test_x.py"

    assert main(["spec-trace", "IDP-42", "--json", "--root", str(repo)]) == 0

    captured = capsys.readouterr()
    expected = (
        '{"ticket": "IDP-42", "ok": true, "required": ["IDP-42:AC-1", "IDP-42:AC-2"], "missing": [], "unknown": [], '
        f'"tests": {{"IDP-42:AC-1": ["{test_file}::test_a"], "IDP-42:AC-2": ["{test_file}::test_b"]}}}}\n'
    )
    assert captured.out == expected
    assert captured.err == ""


@pytest.mark.ac("IDP-13:AC-1")
def test_json_flag_before_ticket_is_accepted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, COVERED_TESTS)

    assert main(["spec-trace", "--json", "IDP-42", "--root", str(repo)]) == 0

    out = capsys.readouterr().out
    assert out.startswith('{"ticket": "IDP-42", "ok": true, ')
    assert out.count("\n") == 1


@pytest.mark.ac("IDP-13:AC-1")
def test_to_dict_returns_keys_in_spec_order(tmp_path: Path) -> None:
    repo = _repo(tmp_path, COVERED_TESTS)
    report = spec_trace.trace("IDP-42", repo)

    data = spec_trace.to_dict(report)

    assert list(data) == ["ticket", "ok", "required", "missing", "unknown", "tests"]
    assert data["ticket"] == "IDP-42"
    assert data["ok"] is True
    assert data["required"] == ["IDP-42:AC-1", "IDP-42:AC-2"]
    assert data["tests"] == {
        "IDP-42:AC-1": [f"{repo}/pkg/tests/test_x.py::test_a"],
        "IDP-42:AC-2": [f"{repo}/pkg/tests/test_x.py::test_b"],
    }


@pytest.mark.ac("IDP-13:AC-1")
def test_json_output_is_sorted_and_deterministic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Citations deliberately out of order, duplicated (two decorators on one test) and spread over two files.
    repo = _repo(
        tmp_path,
        'import pytest\n@pytest.mark.ac("IDP-42:AC-2")\ndef test_z(): ...\n'
        '@pytest.mark.ac("IDP-42:AC-1")\n@pytest.mark.ac("IDP-42:AC-1")\ndef test_m(): ...\n'
        '@pytest.mark.ac("IDP-42:AC-1")\ndef test_b(): ...\n',
    )
    (repo / "pkg" / "tests" / "test_a.py").write_text(
        'import pytest\n@pytest.mark.ac("IDP-42:AC-1")\ndef test_y(): ...\n'
        '@pytest.mark.ac("IDP-42:AC-9")\ndef test_q(): ...\n'
    )
    x = f"{repo}/pkg/tests/test_x.py"
    a = f"{repo}/pkg/tests/test_a.py"

    assert main(["spec-trace", "IDP-42", "--root", str(repo), "--json"]) == 1
    first = capsys.readouterr().out
    assert main(["spec-trace", "IDP-42", "--root", str(repo), "--json"]) == 1
    second = capsys.readouterr().out

    expected = (
        '{"ticket": "IDP-42", "ok": false, "required": ["IDP-42:AC-1", "IDP-42:AC-2"], "missing": [], '
        '"unknown": ["IDP-42:AC-9"], "tests": {'
        f'"IDP-42:AC-1": ["{a}::test_y", "{x}::test_b", "{x}::test_m"], '
        f'"IDP-42:AC-2": ["{x}::test_z"], '
        f'"IDP-42:AC-9": ["{a}::test_q"]}}}}\n'
    )
    assert first == expected
    assert second == first


@pytest.mark.ac("IDP-13:AC-2")
def test_json_uncovered_ac_listed_in_missing_and_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, 'import pytest\n@pytest.mark.ac("IDP-42:AC-1")\ndef test_a(): ...\n')
    test_file = f"{repo}/pkg/tests/test_x.py"

    assert main(["spec-trace", "IDP-42", "--json", "--root", str(repo)]) == 1

    captured = capsys.readouterr()
    expected = (
        '{"ticket": "IDP-42", "ok": false, "required": ["IDP-42:AC-1", "IDP-42:AC-2"], '
        '"missing": ["IDP-42:AC-2"], "unknown": [], '
        f'"tests": {{"IDP-42:AC-1": ["{test_file}::test_a"], "IDP-42:AC-2": []}}}}\n'
    )
    assert captured.out == expected
    assert captured.err == ""


@pytest.mark.ac("IDP-13:AC-2")
def test_json_spec_without_acs_is_not_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "specs" / "IDP-1").mkdir(parents=True)
    (tmp_path / "specs" / "IDP-1" / "spec.md").write_text("# no criteria here\n")

    assert main(["spec-trace", "IDP-1", "--json", "--root", str(tmp_path)]) == 1

    assert capsys.readouterr().out == (
        '{"ticket": "IDP-1", "ok": false, "required": [], "missing": [], "unknown": [], "tests": {}}\n'
    )


@pytest.mark.ac("IDP-13:AC-3")
def test_json_missing_spec_prints_error_object_and_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["spec-trace", "IDP-404", "--json", "--root", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert captured.out == (
        f'{{"ticket": "IDP-404", "ok": false, "error": "spec not found: {tmp_path}/specs/IDP-404/spec.md"}}\n'
    )
    assert captured.err == ""


@pytest.mark.ac("IDP-13:AC-4")
def test_without_json_flag_output_is_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, 'import pytest\n@pytest.mark.ac("IDP-42:AC-1")\ndef test_a(): ...\n')

    assert main(["spec-trace", "IDP-42", "--root", str(repo)]) == 1

    captured = capsys.readouterr()
    assert captured.out == (
        "spec-trace IDP-42: 2 AC(s)\n"
        f"  OK      IDP-42:AC-1  <- {repo}/pkg/tests/test_x.py::test_a\n"
        "  MISSING IDP-42:AC-2\n"
    )
    assert captured.err == ""


@pytest.mark.ac("IDP-13:AC-4")
def test_without_json_flag_missing_spec_still_reports_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["spec-trace", "IDP-404", "--root", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"spec-trace: spec not found: {tmp_path}/specs/IDP-404/spec.md\n"
