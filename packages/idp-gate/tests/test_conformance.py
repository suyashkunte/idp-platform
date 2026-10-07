"""IDP-19: `idp conformance [DIR]` runs `idp validate` and `make verify` for every example with an `idp.yaml`."""

import importlib
import shutil
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from idp_gate.cli import main

REQUIRED_TARGETS = ("lint", "test", "test-component", "verify", "spec-trace")

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make is not on PATH")


def _conformance() -> ModuleType:
    """Import `idp_gate.conformance` lazily so each test fails on its own while the module does not exist yet."""
    try:
        return importlib.import_module("idp_gate.conformance")
    except ModuleNotFoundError as exc:
        if exc.name != "idp_gate.conformance":
            raise
        pytest.fail("idp_gate.conformance is missing (IDP-19 conformance runner not implemented)")


def _run(argv: list[str]) -> int:
    """Call the CLI and return its exit code, also for argparse errors (SystemExit)."""
    try:
        return main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)


def _doc(name: str, profile: str = "python-uv") -> dict[str, Any]:
    return {
        "apiVersion": "idp.dev/v1",
        "kind": "Service",
        "metadata": {
            "name": name,
            "owner": "platform",
            "tier": 3,
            "tracker": {"kind": "jira", "site": "suyashkunte.atlassian.net", "project": "IDP"},
        },
        "spec": {
            "type": "web-api",
            "build": {"profile": profile},
            "runtime": {"port": 8000, "health": {"live": "/healthz/live", "ready": "/healthz/ready"}},
        },
    }


def _write_example(
    root: Path,
    name: str,
    verify: str = "@echo verified",
    doc: dict[str, Any] | None = None,
) -> Path:
    """`root/name/` with a valid idp.yaml and a Makefile defining every required target (no profile include)."""
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "idp.yaml").write_text(yaml.safe_dump(_doc(name) if doc is None else doc))
    rules = "".join(f"{t}:\n\t@echo {t}\n" for t in REQUIRED_TARGETS if t != "verify")
    (directory / "Makefile").write_text(f".PHONY: {' '.join(REQUIRED_TARGETS)}\nverify:\n\t{verify}\n{rules}")
    return directory


# --- AC-2: discovery, one result line per example, summary and exit codes ----------------------------------------


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_prints_one_line_per_example_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    examples = tmp_path / "examples"
    _write_example(examples, "beta")
    _write_example(examples, "alpha")
    (examples / "notes").mkdir()  # no idp.yaml: ignored
    (examples / "notes" / "README.md").write_text("work in progress\n")
    _write_example(examples, ".hidden", verify="@exit 3")  # dot-directory: skipped even though it would fail
    (examples / "README.md").write_text("not a directory\n")
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    out, err = capsys.readouterr()
    assert out == "PASS examples/alpha\nPASS examples/beta\nconformance: 2 passed, 0 failed\n"
    assert err == ""
    assert code == 0


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_dir_defaults_to_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_example(tmp_path / "examples", "only")
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance"])

    assert capsys.readouterr().out == "PASS examples/only\nconformance: 1 passed, 0 failed\n"
    assert code == 0


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_reports_failing_make_verify_with_output_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_example(tmp_path / "examples", "good")
    _write_example(
        tmp_path / "examples",
        "noisy",
        verify="@for i in $$(seq 1 50); do echo line-$$i; done; exit 3",
    )
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    lines = capsys.readouterr().out.splitlines()
    assert lines[:2] == ["PASS examples/good", "FAIL examples/noisy: make verify exited 2"]
    # The last 40 lines of make's combined output: line-12 .. line-50 (39 lines) plus make's own error line.
    tail = lines[2:-1]
    assert len(tail) == 40
    assert tail[0] == "    line-12"
    assert tail[38] == "    line-50"
    assert tail[39].startswith("    make: *** [")
    assert tail[39].endswith("Error 3")
    assert "    line-11" not in lines
    assert lines[-1] == "conformance: 1 passed, 1 failed"
    assert code == 1


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_reports_make_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conformance = _conformance()
    _write_example(tmp_path / "examples", "slow")
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((list(argv), kwargs))
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 0))

    monkeypatch.setattr(conformance.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "FAIL examples/slow: make verify timed out after 60 s\nconformance: 0 passed, 1 failed\n"
    )
    assert code == 1
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[1:5] == ["--no-print-directory", "-C", "examples/slow", "verify"]
    assert argv[5].startswith("IDP_PROFILE_DIR=")
    assert argv[5].endswith("python-uv")
    assert kwargs["timeout"] == 60
    assert conformance.MAKE_TIMEOUT_S == 60


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_reports_unresolvable_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _write_example(
        tmp_path / "examples", "docker", verify="@touch make-ran", doc=_doc("docker", profile="dockerfile")
    )
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "FAIL examples/docker: profile: 'dockerfile' not found (available: python-uv)\n"
        "conformance: 0 passed, 1 failed\n"
    )
    assert code == 1
    assert not (directory / "make-ran").exists()


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
@pytest.mark.ac("IDP-19:AC-3")
def test_conformance_reports_validate_violations_and_skips_make(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = _doc("bad")
    del doc["metadata"]["owner"]
    directory = _write_example(tmp_path / "examples", "bad", verify="@touch make-ran", doc=doc)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "FAIL examples/bad: idp validate: 1 violation(s)\n"
        "    metadata: 'owner' is a required property\n"
        "conformance: 0 passed, 1 failed\n"
    )
    assert code == 1
    assert not (directory / "make-ran").exists()


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_ignores_inherited_make_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_example(tmp_path / "examples", "failing", verify="@exit 3")
    monkeypatch.setenv("MAKEFLAGS", "n")  # an outer `make -n` would otherwise turn the failing recipe into a no-op
    monkeypatch.setenv("MAKELEVEL", "1")
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    lines = capsys.readouterr().out.splitlines()
    assert lines[:1] == ["FAIL examples/failing: make verify exited 2"]
    assert lines[-1:] == ["conformance: 0 passed, 1 failed"]
    assert code == 1


@pytest.mark.ac("IDP-19:AC-2")
@pytest.mark.parametrize(
    ("setup", "arg", "message"),
    [
        ("missing", "missing", "conformance: 'missing' is not a directory\n"),
        ("file", "examples.txt", "conformance: 'examples.txt' is not a directory\n"),
        ("empty", "examples", "conformance: no examples with idp.yaml in 'examples'\n"),
    ],
    ids=["missing-dir", "file-not-dir", "no-examples"],
)
def test_conformance_refuses_missing_or_empty_examples_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    setup: str,
    arg: str,
    message: str,
) -> None:
    if setup == "file":
        (tmp_path / "examples.txt").write_text("not a directory\n")
    elif setup == "empty":
        (tmp_path / "examples" / "draft").mkdir(parents=True)  # a subdirectory without idp.yaml does not count
        (tmp_path / "examples" / ".hidden").mkdir()
        (tmp_path / "examples" / ".hidden" / "idp.yaml").write_text(yaml.safe_dump(_doc("hidden")))
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", arg])

    out, err = capsys.readouterr()
    assert err == message
    assert out == ""
    assert code == 2


@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_without_make_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_example(tmp_path / "examples", "alpha")
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    out, err = capsys.readouterr()
    assert err == "conformance: make not found on PATH\n"
    assert out == ""
    assert code == 2
