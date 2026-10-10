"""IDP-19: `idp conformance [DIR]` runs `idp validate` and `make verify` for every example with an `idp.yaml`."""

import ast
import importlib
import inspect
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest
import yaml

from idp_gate import contract, profiles
from idp_gate.cli import main

REQUIRED_TARGETS = ("lint", "test", "test-component", "verify", "spec-trace")
STRIPPED_MAKE_VARS = ("MAKEFLAGS", "GNUMAKEFLAGS", "MAKELEVEL", "MFLAGS", "MAKEFILES")

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
    timeouts: list[float | None] = []
    killed: list[tuple[int, int]] = []

    class FakePopen:
        pid = 424242
        returncode = -9

        def __init__(self, argv: list[str], **kwargs: Any) -> None:
            calls.append((list(argv), kwargs))

        def communicate(self, timeout: float | None = None) -> tuple[str, None]:
            timeouts.append(timeout)
            if len(timeouts) == 1:
                raise subprocess.TimeoutExpired("make", timeout or 0)
            return "", None

    monkeypatch.setattr(conformance.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(conformance.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    for name in STRIPPED_MAKE_VARS:
        monkeypatch.setenv(name, "x")
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "FAIL examples/slow: make verify timed out after 60 s\nconformance: 0 passed, 1 failed\n"
    )
    assert code == 1
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[1:8] == [
        "--no-print-directory",
        "-C",
        "examples/slow",
        "-f",
        "Makefile",
        "--assume-old=Makefile",
        "verify",
    ]
    assert argv[8].startswith("IDP_PROFILE_DIR=")
    assert argv[8].endswith("python-uv")
    assert kwargs["start_new_session"] is True
    assert [name for name in STRIPPED_MAKE_VARS if name in kwargs["env"]] == []
    assert timeouts == [60, None]
    assert killed == [(FakePopen.pid, signal.SIGKILL)]
    assert conformance.MAKE_TIMEOUT_S == 60


def _wait_until_gone(pid: int, deadline_s: float = 5.0) -> bool:
    """Poll (bounded) until `pid` no longer exists; a killed child may briefly linger until it is reaped."""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.01)
    return False


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_timeout_kills_recipe_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conformance = _conformance()
    # The child does not hold make's output pipe, so only a process-group kill (not killing make alone) stops it.
    verify = "@echo $$$$ > child.pid; exec sleep 30 >/dev/null 2>&1"
    directory = _write_example(tmp_path / "examples", "hang", verify=verify)
    monkeypatch.setattr(conformance, "MAKE_TIMEOUT_S", 1)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "FAIL examples/hang: make verify timed out after 1 s"
    assert lines[-1] == "conformance: 0 passed, 1 failed"
    assert code == 1
    pid = int((directory / "child.pid").read_text())
    assert _wait_until_gone(pid), f"recipe child {pid} survived the timeout"


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_conformance_reports_non_utf8_output_as_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_example(tmp_path / "examples", "binary", verify="@printf 'bad-\\377\\n'; exit 1")
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "FAIL examples/binary: make verify exited 2"
    assert "    bad-\ufffd" in lines
    assert lines[-1] == "conformance: 0 passed, 1 failed"
    assert code == 1


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


# --- IDP-22 ------------------------------------------------------------------------------------------------------


def _fake_make_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An executable `make` stub as the only thing on PATH (for tests that fake Popen and never run make)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make = bin_dir / "make"
    make.write_text("#!/bin/sh\nexit 0\n")
    make.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    return make


class _RecordingPopen:
    """Fake Popen: records argv/kwargs in `calls` and exits 0 without running anything."""

    calls: ClassVar[list[tuple[list[str], dict[str, Any]]]] = []
    pid = 434343
    returncode = 0

    def __init__(self, argv: list[str], **kwargs: Any) -> None:
        type(self).calls.append((list(argv), kwargs))

    def communicate(self, timeout: float | None = None) -> tuple[str, None]:
        return "", None


def _recording_popen(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], dict[str, Any]]]:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(_RecordingPopen, "calls", calls)
    monkeypatch.setattr(_conformance().subprocess, "Popen", _RecordingPopen)
    return calls


@pytest.mark.ac("IDP-22:AC-2")
def test_make_verify_is_invoked_with_f_makefile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_example(tmp_path / "examples", "okay")
    make = _fake_make_on_path(tmp_path, monkeypatch)
    calls = _recording_popen(monkeypatch)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == "PASS examples/okay\nconformance: 1 passed, 0 failed\n"
    assert code == 0
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:8] == [
        str(make),
        "--no-print-directory",
        "-C",
        "examples/okay",
        "-f",
        "Makefile",
        "--assume-old=Makefile",
        "verify",
    ]
    assert len(argv) == 9
    assert argv[8].startswith("IDP_PROFILE_DIR=")
    assert argv[8].endswith("python-uv")
    assert kwargs["start_new_session"] is True


def _case_sensitive(directory: Path) -> bool:
    """True if `directory` is on a case-sensitive filesystem (Linux CI), False on case-insensitive APFS (macOS)."""
    probe = directory / "probe"
    probe.write_text("")
    sensitive = not (directory / "PROBE").exists()
    probe.unlink()
    return sensitive


@needs_make
@pytest.mark.ac("IDP-22:AC-2")
def test_make_verify_ignores_gnumakefile_and_makefile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conformance = _conformance()
    directory = _write_example(tmp_path / "examples", "shadowed", verify="@exit 3")
    (directory / "GNUmakefile").write_text("verify:\n\t@true\n")
    if _case_sensitive(directory):  # `makefile` would be the same file as `Makefile` on APFS
        (directory / "makefile").write_text("verify:\n\t@true\n")
    for name in STRIPPED_MAKE_VARS:
        monkeypatch.delenv(name, raising=False)
    make = shutil.which("make")
    assert make is not None

    result = conformance._run_make_verify(directory, make, str(tmp_path), ["--assume-old=Makefile"])

    assert result.ok is False
    assert result.reason == "make verify exited 2"


@needs_make
@pytest.mark.ac("IDP-22:AC-3")
def test_conformance_fails_symlinked_example_without_running_make(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    examples = tmp_path / "examples"
    _write_example(examples, "real")
    outside = _write_example(tmp_path / "outside", "svc", verify="@touch make-ran", doc=_doc("linked"))
    (examples / "linked").symlink_to(outside)
    (examples / "alias").symlink_to("real")  # relative link to an example inside DIR: still refused
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "FAIL examples/alias: outside examples directory\n"
        "FAIL examples/linked: outside examples directory\n"
        "PASS examples/real\n"
        "conformance: 1 passed, 2 failed\n"
    )
    assert code == 1
    assert not (outside / "make-ran").exists()


@pytest.mark.ac("IDP-22:AC-3")
@pytest.mark.parametrize(
    "mode", ["elsewhere", "unresolvable", "missing"], ids=["resolves-outside", "resolve-raises", "resolve-oserror"]
)
def test_conformance_fails_example_resolving_outside_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    _write_example(tmp_path / "examples", "odd", verify="@touch make-ran")
    elsewhere = tmp_path / "elsewhere" / "odd"
    elsewhere.mkdir(parents=True)
    original = Path.resolve

    def fake_resolve(self: Path, strict: bool = False) -> Path:
        if strict and self.name == "odd" and self.parent.name == "examples":
            if mode == "unresolvable":
                raise RuntimeError("Symlink loop")
            if mode == "missing":  # removed between listing and checking
                raise FileNotFoundError(2, "No such file or directory", str(self))
            return elsewhere
        return original(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    _fake_make_on_path(tmp_path, monkeypatch)
    calls = _recording_popen(monkeypatch)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "FAIL examples/odd: outside examples directory\nconformance: 0 passed, 1 failed\n"
    )
    assert code == 1
    assert calls == []


@needs_make
@pytest.mark.ac("IDP-22:AC-3")
def test_conformance_accepts_real_examples_under_symlinked_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_example(tmp_path / "examples", "real")
    (tmp_path / "linkdir").symlink_to("examples")
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "linkdir"])

    assert capsys.readouterr().out == "PASS linkdir/real\nconformance: 1 passed, 0 failed\n"
    assert code == 0


@pytest.mark.ac("IDP-22:AC-4")
def test_check_example_parses_idp_yaml_once_for_validation_and_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conformance = _conformance()
    _write_example(tmp_path / "examples", "okay")
    parsed: list[str] = []
    resolved: list[str] = []
    original_load = contract._load_yaml
    original_resolve = profiles.resolve

    def counting_load(path: Path) -> tuple[Any, list[contract.Violation]]:
        parsed.append(str(path))
        return original_load(path)

    def recording_resolve(name: str) -> Any:
        resolved.append(name)
        return original_resolve(name)

    def stub_make(directory: Path, make: str, profile_dir: str, assume_old: list[str]) -> Any:
        return conformance.Result(directory, ok=True)

    monkeypatch.setattr(contract, "_load_yaml", counting_load)
    monkeypatch.setattr(profiles, "resolve", recording_resolve)
    monkeypatch.setattr(conformance, "_run_make_verify", stub_make)
    _fake_make_on_path(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == "PASS examples/okay\nconformance: 1 passed, 0 failed\n"
    assert code == 0
    assert [p for p in parsed if p.endswith("idp.yaml")] == ["examples/okay/idp.yaml"]
    assert resolved == ["python-uv"]


def _private_contract_names(source: str) -> list[str]:
    """Names starting with `_` that `source` takes from the contract module: `contract._x`,
    `from idp_gate.contract import _x` and `from .contract import _x` (sorted)."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "contract":
            names.append(node.attr)
        elif isinstance(node, ast.ImportFrom) and (
            (node.module == "idp_gate.contract" and node.level == 0) or (node.module == "contract" and node.level >= 1)
        ):
            names.extend(alias.name for alias in node.names)
    return sorted(name for name in names if name.startswith("_"))


SYNTHETIC_PRIVATE_USES = (
    "from idp_gate import contract\n"
    "from idp_gate.contract import _absolute, load_service\n"
    "from .contract import _relative\n"
    "from ..contract import _parent\n"
    "doc = contract._attribute(path)\n"
    "public = contract.load_service(path)\n"
)


@pytest.mark.ac("IDP-22:AC-4")
def test_conformance_module_uses_no_private_contract_members() -> None:
    source_file = inspect.getsourcefile(_conformance())
    assert source_file is not None

    private = _private_contract_names(Path(source_file).read_text(encoding="utf-8"))

    assert private == []
    # The check itself sees every form (it would be red on such a module).
    assert _private_contract_names(SYNTHETIC_PRIVATE_USES) == ["_absolute", "_attribute", "_parent", "_relative"]


# --- IDP-22 AC-5: make runs with --assume-old for Makefile and every literal include word -------------------------


def _append_to_makefile(directory: Path, text: str) -> None:
    makefile = directory / "Makefile"
    makefile.write_text(makefile.read_text() + text)


@pytest.mark.ac("IDP-22:AC-5")
def test_make_verify_pins_makefile_and_include_words_with_assume_old(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _write_example(tmp_path / "examples", "pinned")
    _append_to_makefile(directory, "include common.mk\n-include ./gen.mk -x.mk\n")
    (directory / "common.mk").write_text("COMMON := 1\n")
    make = _fake_make_on_path(tmp_path, monkeypatch)
    calls = _recording_popen(monkeypatch)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == "PASS examples/pinned\nconformance: 1 passed, 0 failed\n"
    assert code == 0
    assert len(calls) == 1
    argv, _ = calls[0]
    assert argv[:12] == [
        str(make),
        "--no-print-directory",
        "-C",
        "examples/pinned",
        "-f",
        "Makefile",
        "--assume-old=Makefile",
        "--assume-old=common.mk",
        "--assume-old=./gen.mk",
        "--assume-old=gen.mk",
        "--assume-old=-x.mk",
        "verify",
    ]
    assert len(argv) == 13
    assert argv[12].startswith("IDP_PROFILE_DIR=")


@pytest.mark.ac("IDP-22:AC-5")
def test_conformance_fails_when_include_words_exceed_make_argument_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conformance = _conformance()
    bulky = _write_example(tmp_path / "examples", "bulky")
    _append_to_makefile(bulky, "include common.mk\n")
    (bulky / "common.mk").write_text("COMMON := 1\n")
    _write_example(tmp_path / "examples", "plain")
    # 40 bytes: `--assume-old=Makefile` (21) fits, plus `--assume-old=common.mk` (22) does not.
    monkeypatch.setattr(conformance, "MAX_ASSUME_OLD_BYTES", 40, raising=False)
    _fake_make_on_path(tmp_path, monkeypatch)
    calls = _recording_popen(monkeypatch)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "FAIL examples/bulky: include words exceed the make argument limit\n"
        "PASS examples/plain\n"
        "conformance: 1 passed, 1 failed\n"
    )
    assert code == 1
    assert [argv[3] for argv, _ in calls] == ["examples/plain"]


@pytest.mark.ac("IDP-22:AC-5")
def test_conformance_fails_when_makefile_changes_between_scans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_example(tmp_path / "examples", "changed")
    original = contract.makefile_targets
    scans: list[Path] = []

    def changing_scan(makefile: Path) -> contract.MakefileScan:
        scans.append(makefile)
        if len(scans) == 1:  # the validation scan sees the committed files
            return original(makefile)
        return contract.MakefileScan(frozenset(), (contract.Violation("Makefile", "cannot read 'common.mk'"),))

    monkeypatch.setattr(contract, "makefile_targets", changing_scan)
    _fake_make_on_path(tmp_path, monkeypatch)
    calls = _recording_popen(monkeypatch)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "FAIL examples/changed: idp validate: 1 violation(s)\n"
        "    Makefile: cannot read 'common.mk'\n"
        "conformance: 0 passed, 1 failed\n"
    )
    assert code == 1
    assert len(scans) == 2
    assert calls == []


OLD_MTIME = 1_600_000_000  # validated files
NEW_MTIME = 1_700_000_000  # sources that would remake them (explicit timestamps: no sleeps)
EVIL_MAKEFILE = "verify:\n\t@touch evil-ran\n"
EVIL_INCLUDE = "EVIL := $(shell touch evil-ran)\n"


@needs_make
@pytest.mark.ac("IDP-22:AC-5")
@pytest.mark.parametrize(
    ("name", "rules", "files"),
    [
        ("self-remake", "Makefile: evil.txt\n\tcp evil.txt Makefile\n", {"evil.txt": EVIL_MAKEFILE}),
        ("generated-include", "-include gen.mk\ngen.mk:\n\techo '$$(shell touch evil-ran)' > gen.mk\n", {}),
        (
            "stale-include",
            "include common.mk\ncommon.mk: common.src\n\tcp common.src common.mk\n",
            {"common.mk": "COMMON := 1\n", "common.src": EVIL_INCLUDE},
        ),
        ("dot-slash", "-include ./gen.mk\n./gen.mk:\n\techo '$$(shell touch evil-ran)' > gen.mk\n", {}),
    ],
    ids=["self-remake", "generated-include", "stale-include", "dot-slash"],
)
def test_make_cannot_remake_validated_makefiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
    rules: str,
    files: dict[str, str],
) -> None:
    directory = _write_example(tmp_path / "examples", name, verify="@touch validated-ran")
    _append_to_makefile(directory, rules)
    for file_name, content in files.items():
        (directory / file_name).write_text(content)
    os.utime(directory / "Makefile", (OLD_MTIME, OLD_MTIME))
    for file_name in files:
        mtime = OLD_MTIME if file_name.endswith(".mk") else NEW_MTIME
        os.utime(directory / file_name, (mtime, mtime))
    validated = {p.name: p.read_bytes() for p in (directory / "Makefile", directory / "common.mk") if p.exists()}
    for var in STRIPPED_MAKE_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == f"PASS examples/{name}\nconformance: 1 passed, 0 failed\n"
    assert code == 0
    assert (directory / "validated-ran").exists()
    assert not (directory / "evil-ran").exists()
    assert {file_name: (directory / file_name).read_bytes() for file_name in validated} == validated
    assert not (directory / "gen.mk").exists()


# --- IDP-22 AC-6: an unreadable idp.yaml fails that example and the run continues ---------------------------------


@pytest.mark.ac("IDP-22:AC-6")
def test_conformance_reports_unreadable_idp_yaml_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conformance = _conformance()
    alpha = _write_example(tmp_path / "examples", "alpha")
    (alpha / "idp.yaml").write_bytes(b"name: caf\xe9\n")
    _write_example(tmp_path / "examples", "bravo")
    ran: list[str] = []

    def stub_make(directory: Path, *args: Any) -> Any:
        ran.append(str(directory))
        return conformance.Result(directory, ok=True)

    monkeypatch.setattr(conformance, "_run_make_verify", stub_make)
    _fake_make_on_path(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    out, err = capsys.readouterr()
    assert out == (
        "FAIL examples/alpha: idp validate: 1 violation(s)\n"
        "    <root>: cannot read: not valid UTF-8 (invalid continuation byte at byte 9)\n"
        "PASS examples/bravo\n"
        "conformance: 1 passed, 1 failed\n"
    )
    assert err == ""
    assert code == 1
    assert ran == ["examples/bravo"]
