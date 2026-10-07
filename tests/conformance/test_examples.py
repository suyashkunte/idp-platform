"""IDP-19: examples/minimal-service fixture, `idp conformance` over examples/ and root `make conformance`."""

import ast
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
import yaml

from idp_gate import contract
from idp_gate.cli import main

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
EXAMPLE = EXAMPLES / "minimal-service"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MAKE_ENV_STRIPPED = ("MAKEFLAGS", "GNUMAKEFLAGS", "MAKELEVEL", "MFLAGS", "MAKEFILES")

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make is not on PATH")


def _run(argv: list[str]) -> int:
    """Call the CLI and return its exit code, also for argparse errors (SystemExit)."""
    try:
        return main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)


def _require_example() -> None:
    if not (EXAMPLE / "idp.yaml").is_file():
        pytest.fail("examples/minimal-service/idp.yaml is missing (IDP-19 example not implemented)")


def _make_env() -> dict[str, str]:
    """The current environment without inherited make state (an outer `make -n/-k/-j` must not leak in)."""
    return {k: v for k, v in os.environ.items() if k not in MAKE_ENV_STRIPPED}


def _make(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "--no-print-directory", "-C", str(EXAMPLE), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_make_env(),
    )


def _copy_into(examples: Path, source: Path, name: str) -> None:
    shutil.copytree(source, examples / name, ignore=shutil.ignore_patterns("__pycache__"))


# --- AC-1: the minimal-service example ---------------------------------------------------------------------------


@pytest.mark.ac("IDP-19:AC-1")
def test_minimal_service_has_app_contract_makefile_and_unit_test() -> None:
    _require_example()
    for name in ("app.py", "idp.yaml", "Makefile", "README.md", "tests/__init__.py", "tests/test_app.py"):
        assert (EXAMPLE / name).is_file(), f"examples/minimal-service/{name} is missing"

    makefile_lines = (EXAMPLE / "Makefile").read_text(encoding="utf-8").splitlines()
    assert "IDP_PROFILE_DIR ?= ../../build-profiles/python-uv" in makefile_lines
    assert "include $(IDP_PROFILE_DIR)/defaults.mk" in makefile_lines
    scan = contract.makefile_targets(EXAMPLE / "Makefile")
    assert scan.violations == ()
    assert {"lint", "test", "test-component", "verify", "spec-trace"} <= scan.targets

    doc = yaml.safe_load((EXAMPLE / "idp.yaml").read_text(encoding="utf-8"))
    assert doc["metadata"]["name"] == "minimal-service"
    assert doc["spec"]["build"]["profile"] == "python-uv"
    assert doc["spec"]["runtime"]["port"] == 8000
    assert doc["spec"]["runtime"]["health"] == {
        "live": "/healthz/live",
        "ready": "/healthz/ready",
        "startup": "/healthz/startup",
    }
    assert True not in (doc["spec"].get("tests") or {}).values()


@needs_make
@pytest.mark.ac("IDP-19:AC-1")
def test_minimal_service_passes_idp_validate_and_make_verify(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_example()
    monkeypatch.chdir(EXAMPLE)

    code = _run(["validate"])

    assert capsys.readouterr().out == "idp.yaml: valid (idp-service.v1.json)\n"
    assert code == 0
    result = _make("verify")  # by hand: relies on the Makefile's relative IDP_PROFILE_DIR default
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.ac("IDP-19:AC-1")
def test_minimal_service_uses_only_stdlib() -> None:
    _require_example()
    sources = sorted(p for p in EXAMPLE.rglob("*.py") if "__pycache__" not in p.parts)
    names = [p.relative_to(EXAMPLE).as_posix() for p in sources]
    assert "app.py" in names
    assert "tests/test_app.py" in names
    third_party: list[str] = []
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                top = module.split(".")[0]
                if top not in sys.stdlib_module_names and top not in {"app", "tests"}:
                    third_party.append(f"{path.relative_to(EXAMPLE)}: {module}")
    assert third_party == []


@pytest.mark.ac("IDP-19:AC-1")
def test_minimal_service_is_not_a_workspace_member_or_coverage_source() -> None:
    _require_example()
    assert not (EXAMPLE / "pyproject.toml").exists()
    assert not (EXAMPLE / "uv.lock").exists()
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["uv"]["workspace"]["members"] == ["packages/*"]
    assert pyproject["tool"]["coverage"]["run"]["source"] == ["packages"]
    assert pyproject["tool"]["pytest"]["ini_options"]["testpaths"] == ["packages", "tests"]


@needs_make
@pytest.mark.ac("IDP-19:AC-1")
def test_minimal_service_verify_needs_no_network() -> None:
    _require_example()

    result = _make("-n", "verify")

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "-m compileall -q app.py tests" in out
    assert "-m unittest discover -s tests -t ." in out
    for forbidden in ("idp-default-", "uv ", "pip-audit", "cyclonedx"):
        assert forbidden not in out, f"make -n verify mentions {forbidden!r}"


# --- AC-2: idp conformance over the platform's examples/ ---------------------------------------------------------


@needs_make
@pytest.mark.ac("IDP-19:AC-2")
def test_platform_examples_pass_conformance_within_60_seconds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_example()
    monkeypatch.chdir(ROOT)
    for name in MAKE_ENV_STRIPPED:  # pytest may itself run under `make verify`
        monkeypatch.delenv(name, raising=False)

    start = time.monotonic()
    code = _run(["conformance", "examples"])
    elapsed = time.monotonic() - start

    lines = capsys.readouterr().out.splitlines()
    assert "PASS examples/minimal-service" in lines
    assert [line for line in lines if line.startswith("FAIL")] == []
    assert re.fullmatch(r"conformance: [1-9][0-9]* passed, 0 failed", lines[-1]), lines
    assert code == 0
    assert elapsed < 60


# --- AC-3: negative fixtures make conformance fail and name the example -------------------------------------------


@needs_make
@pytest.mark.ac("IDP-19:AC-3")
def test_conformance_fails_and_names_example_with_unknown_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_example()
    examples = tmp_path / "examples"
    _copy_into(examples, EXAMPLE, "minimal-service")
    _copy_into(examples, FIXTURES / "unknown-field", "unknown-field")
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "PASS examples/minimal-service\n"
        "FAIL examples/unknown-field: idp validate: 1 violation(s)\n"
        "    spec: 'bogusField' does not match any of the regexes: '^x-'\n"
        "conformance: 1 passed, 1 failed\n"
    )
    assert code == 1


@needs_make
@pytest.mark.ac("IDP-19:AC-3")
def test_conformance_fails_and_names_example_missing_required_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_example()
    examples = tmp_path / "examples"
    _copy_into(examples, EXAMPLE, "minimal-service")
    _copy_into(examples, FIXTURES / "missing-target", "missing-target")
    monkeypatch.chdir(tmp_path)

    code = _run(["conformance", "examples"])

    assert capsys.readouterr().out == (
        "PASS examples/minimal-service\n"
        "FAIL examples/missing-target: idp validate: 1 violation(s)\n"
        "    Makefile: missing required target 'verify'\n"
        "conformance: 1 passed, 1 failed\n"
    )
    assert code == 1


# --- AC-4: root `make verify` runs `make conformance` (fails until a human pastes the plan.md snippet) -------------


@pytest.mark.ac("IDP-19:AC-4")
def test_root_make_verify_runs_conformance() -> None:
    makefile = ROOT / "Makefile"
    scan = contract.makefile_targets(makefile)
    assert "conformance" in scan.targets, "root Makefile has no 'conformance' target"

    lines = makefile.read_text(encoding="utf-8").splitlines()
    phony = [line for line in lines if line.startswith(".PHONY:")]
    assert any("conformance" in line.split() for line in phony), "'conformance' is not in .PHONY"
    verify = [line for line in lines if line.startswith("verify:")]
    assert len(verify) == 1
    prerequisites = verify[0].split("##", 1)[0].split(":", 1)[1].split()
    assert "conformance" in prerequisites, f"verify prerequisites are {prerequisites}"
    assert "\t$(UV) run idp conformance examples" in lines
