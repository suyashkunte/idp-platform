"""IDP-18: python-uv build profile, build-profile.v1 schema, discovery and `idp profile show`.

IDP-21: reproducible tool resolution (`--exclude-newer`) and clean, sdist-safe packaging of the profiles.

IDP-24: hashed build constraints for the build backend, a clean `uv build` environment, and no symlink following in
the build hook.
"""

import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest
import yaml

from idp_gate import contract
from idp_gate.cli import main

REPO = Path(__file__).resolve().parents[3]
PROFILE_DIR = REPO / "build-profiles" / "python-uv"
PROFILE_YAML = PROFILE_DIR / "profile.yaml"
DEFAULTS_MK = PROFILE_DIR / "defaults.mk"
AGENT_NOTES = PROFILE_DIR / "agent-notes.md"
GENERATOR_AGENT = REPO / "plugins" / "idp-agentic" / "agents" / "unit-test-generator.md"
PACKAGE_DIR = REPO / "packages" / "idp-gate"
PACKAGE_PYPROJECT = PACKAGE_DIR / "pyproject.toml"
HATCH_BUILD = PACKAGE_DIR / "hatch_build.py"
BUILD_CONSTRAINTS = PACKAGE_DIR / "build-constraints.txt"
UV_LOCK = REPO / "uv.lock"
SCHEMA_FILE = "build-profile.v1.json"

GENERATOR_FRONTMATTER = (
    "---\n"
    "name: unit-test-generator\n"
    "description: Writes FAILING unit and component tests from acceptance criteria before implementation "
    "(test-first). Never edits production code. Use after the spec is approved.\n"
    "tools: Read, Grep, Glob, Write, Edit, Bash\n"
    "model: inherit\n"
    "---\n"
)


def _profiles() -> ModuleType:
    """Import `idp_gate.profiles` lazily so each test fails on its own while the module does not exist yet."""
    try:
        return importlib.import_module("idp_gate.profiles")
    except ModuleNotFoundError as exc:
        if exc.name != "idp_gate.profiles":
            raise
        pytest.fail("idp_gate.profiles is missing (IDP-18 profile validation/discovery not implemented)")


def _run(argv: list[str]) -> int:
    """Call the CLI and return its exit code, also for argparse errors (SystemExit)."""
    try:
        return main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)


def _valid_doc(name: str = "demo") -> dict[str, Any]:
    return {
        "name": name,
        "description": "Demo profile",
        "setup": [{"name": "Sync", "run": "uv sync --frozen"}],
        "defaultTargets": ["sbom", "sca"],
        "coverage": {"format": "cobertura"},
        "sbom": {"tool": "cyclonedx-py", "format": "cyclonedx-json"},
        "sca": {"tool": "pip-audit"},
    }


def _write_profile(root: Path, dirname: str, content: dict[str, Any] | str) -> Path:
    directory = root / dirname
    directory.mkdir(parents=True)
    text = content if isinstance(content, str) else yaml.safe_dump(content, sort_keys=False)
    (directory / "profile.yaml").write_text(text)
    return directory


def _use_roots(monkeypatch: pytest.MonkeyPatch, packaged: Path, checkout: Path) -> ModuleType:
    profiles = _profiles()
    monkeypatch.setattr(profiles, "_PACKAGED_DIR", packaged)
    monkeypatch.setattr(profiles, "_CHECKOUT_DIR", checkout)
    return profiles


def _require(path: Path) -> None:
    if not path.is_file():
        pytest.fail(f"{path.relative_to(REPO)} is missing (IDP-18 not implemented)")


# --- AC-1: build-profile.v1 schema and the python-uv profile -----------------------------------------------------


@pytest.mark.ac("IDP-18:AC-1")
def test_build_profile_schema_ships_in_idp_gate() -> None:
    schema_file = resources.files("idp_gate.schemas").joinpath(SCHEMA_FILE)
    assert schema_file.is_file(), f"idp_gate/schemas/{SCHEMA_FILE} is not shipped in idp-gate"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert sorted(schema["required"]) == ["coverage", "defaultTargets", "description", "name", "sbom", "sca", "setup"]
    assert schema["additionalProperties"] is False
    profiles = _profiles()
    assert profiles.PROFILE_SCHEMA_ID == "build-profile.v1"
    assert profiles.PROFILE_SCHEMA_NAME == SCHEMA_FILE


@pytest.mark.ac("IDP-18:AC-1")
def test_python_uv_profile_validates_against_build_profile_schema() -> None:
    _require(PROFILE_YAML)
    doc = yaml.safe_load(PROFILE_YAML.read_text(encoding="utf-8"))
    assert _profiles().validate_profile_document(doc, "python-uv") == []
    assert doc["name"] == "python-uv"
    assert doc["defaultTargets"] == ["sbom", "sca"]
    assert doc["coverage"] == {"format": "cobertura"}
    assert doc["sbom"] == {"tool": "cyclonedx-py", "format": "cyclonedx-json"}
    assert doc["sca"] == {"tool": "pip-audit"}
    assert list(doc) == ["name", "description", "setup", "defaultTargets", "coverage", "sbom", "sca"]


def _without_name(doc: dict[str, Any]) -> None:
    del doc["name"]


def _with_unknown_key(doc: dict[str, Any]) -> None:
    doc["extra"] = 1


def _with_xml_coverage(doc: dict[str, Any]) -> None:
    doc["coverage"]["format"] = "xml"


def _with_empty_setup(doc: dict[str, Any]) -> None:
    doc["setup"] = []


def _with_duplicate_targets(doc: dict[str, Any]) -> None:
    doc["defaultTargets"] = ["sbom", "sbom"]


def _with_unknown_step_key(doc: dict[str, Any]) -> None:
    doc["setup"][0]["shell"] = "bash"


@pytest.mark.ac("IDP-18:AC-1")
@pytest.mark.parametrize(
    ("mutate", "path", "message"),
    [
        (_without_name, "", "'name' is a required property"),
        (_with_unknown_key, "", "Additional properties are not allowed ('extra' was unexpected)"),
        (_with_xml_coverage, "coverage.format", "'xml' is not one of ['cobertura', 'lcov', 'jacoco']"),
        (_with_empty_setup, "setup", "[] should be non-empty"),
        (_with_duplicate_targets, "defaultTargets", "['sbom', 'sbom'] has non-unique elements"),
        (_with_unknown_step_key, "setup.0", "Additional properties are not allowed ('shell' was unexpected)"),
    ],
    ids=["missing-name", "unknown-key", "coverage-xml", "empty-setup", "duplicate-targets", "unknown-step-key"],
)
def test_invalid_profile_documents_are_rejected(mutate: Any, path: str, message: str) -> None:
    profiles = _profiles()
    doc = _valid_doc()
    assert profiles.validate_profile_document(doc, "demo") == []
    mutate(doc)
    violations = profiles.validate_profile_document(doc, "demo")
    assert [(v.path, v.message) for v in violations] == [(path, message)]


@pytest.mark.ac("IDP-18:AC-1")
def test_bad_profile_name_pattern_is_rejected() -> None:
    violations = _profiles().validate_profile_document(_valid_doc("Python_UV"), "Python_UV")
    assert [v.path for v in violations] == ["name"]
    assert "does not match '^[a-z0-9][a-z0-9-]*$'" in violations[0].message


@pytest.mark.ac("IDP-18:AC-1")
def test_profile_name_must_match_directory() -> None:
    profiles = _profiles()
    violations = profiles.validate_profile_document(_valid_doc("demo"), "renamed")
    assert violations == [contract.Violation("name", "name 'demo' does not match directory 'renamed'")]
    assert str(violations[0]) == "name: name 'demo' does not match directory 'renamed'"
    assert profiles.validate_profile_document(_valid_doc("renamed"), "renamed") == []


@pytest.mark.ac("IDP-18:AC-1")
def test_default_targets_have_recipes_in_defaults_mk() -> None:
    _require(PROFILE_YAML)
    _require(DEFAULTS_MK)
    doc = yaml.safe_load(PROFILE_YAML.read_text(encoding="utf-8"))
    scan = contract.makefile_targets(DEFAULTS_MK)
    assert scan.violations == ()
    assert {"idp-default-sbom", "idp-default-sca"} <= scan.targets
    assert {f"idp-default-{t}" for t in doc["defaultTargets"]} <= scan.targets
    assert "sbom" not in scan.targets  # defaults never define the tenant targets explicitly
    assert "sca" not in scan.targets


# --- AC-2 / AC-3: make-level behaviour of defaults.mk ------------------------------------------------------------


# Inherited make state and profile variables (`?=` reads the environment) must not leak into make-level tests.
_MAKE_ENV_STRIPPED = frozenset(
    {
        "MAKEFLAGS",
        "GNUMAKEFLAGS",
        "MAKELEVEL",
        "MFLAGS",
        "MAKEFILES",
        "REPORTS_DIR",
        "UV",
        "IDP_SBOM_CMD",
        "IDP_SCA_CMD",
        "IDP_CYCLONEDX_SPEC",
        "IDP_PIP_AUDIT_SPEC",
        "IDP_REQUIREMENTS",
        "IDP_EXPORT_CMD",
        "IDP_SBOM_REQUIREMENTS",
        "IDP_SBOM_EXPORT_CMD",
        "IDP_TOOLS_EXCLUDE_NEWER",
    }
)


def _make(
    directory: Path, *args: str, stub: bool = True, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run make in `directory` with the python-uv profile; tool commands are stubbed unless `stub` is False."""
    if shutil.which("make") is None:
        pytest.skip("make is not installed")
    _require(DEFAULTS_MK)
    env = {k: v for k, v in os.environ.items() if k not in _MAKE_ENV_STRIPPED} | (env_extra or {})
    argv = ["make", "--no-print-directory", "-C", str(directory), *args, f"IDP_PROFILE_DIR={PROFILE_DIR}"]
    if stub:
        argv += ["IDP_SBOM_CMD=echo default-sbom", "IDP_SCA_CMD=echo default-sca"]
    return subprocess.run(argv, capture_output=True, text=True, env=env, timeout=60, check=False)


def _tenant(directory: Path, rules: str, include_first: bool = True) -> None:
    include = "include $(IDP_PROFILE_DIR)/defaults.mk\n"
    (directory / "Makefile").write_text(include + rules if include_first else rules + include)


@pytest.mark.ac("IDP-18:AC-2")
def test_make_sbom_and_sca_run_profile_defaults(tmp_path: Path) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    sbom = _make(tmp_path, "sbom")
    assert (sbom.returncode, sbom.stderr) == (0, "")
    assert sbom.stdout.splitlines()[-1] == "default-sbom"
    assert "default-sca" not in sbom.stdout
    assert (tmp_path / "reports").is_dir()
    sca = _make(tmp_path, "sca")
    assert (sca.returncode, sca.stderr) == (0, "")
    assert sca.stdout.splitlines()[-1] == "default-sca"
    assert "default-sbom" not in sca.stdout


@pytest.mark.ac("IDP-18:AC-2")
def test_default_runs_even_if_a_file_named_like_the_target_exists(tmp_path: Path) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    (tmp_path / "sbom").write_text("not a target\n")
    result = _make(tmp_path, "sbom")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout.splitlines()[-1] == "default-sbom"


@pytest.mark.ac("IDP-18:AC-2")
def test_unknown_target_still_fails_with_no_rule(tmp_path: Path) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    result = _make(tmp_path, "lnt")
    assert result.returncode == 2
    assert "No rule to make target" in result.stderr
    assert "lnt" in result.stderr


@pytest.mark.ac("IDP-18:AC-2")
@pytest.mark.parametrize(("target", "variable"), [("sbom", "IDP_SBOM_CMD"), ("sca", "IDP_SCA_CMD")])
def test_empty_default_command_fails_closed(tmp_path: Path, target: str, variable: str) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    result = _make(tmp_path, target, f"{variable}=", stub=False)
    assert result.returncode == 2
    assert f"{variable} is empty: set it or define your own {target} target" in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "reports").exists()


@pytest.mark.ac("IDP-18:AC-2")
@pytest.mark.parametrize(("target", "variable"), [("sbom", "IDP_SBOM_CMD"), ("sca", "IDP_SCA_CMD")])
def test_failing_default_command_fails_the_target(tmp_path: Path, target: str, variable: str) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    result = _make(tmp_path, target, f"{variable}=false", stub=False)
    assert result.returncode == 2
    assert f"idp-default-{target}] Error 1" in result.stderr  # make 3.81: [t]; make 4.x: [file:line: t]


@pytest.mark.ac("IDP-18:AC-2")
def test_default_commands_use_profile_tools_in_dry_run(tmp_path: Path) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    export = (
        "/nonexistent/uv export --quiet --locked --all-packages --no-emit-project --no-emit-workspace "
        "--format requirements-txt --output-file reports/requirements.locked.txt"
    )
    sca = _make(tmp_path, "-n", "sca", "UV=/nonexistent/uv", stub=False)
    assert (sca.returncode, sca.stderr) == (0, "")
    assert (
        f"{export} && /nonexistent/uv tool run --exclude-newer '2026-10-06T00:00:00Z' --from pip-audit==2.10.1 "
        "pip-audit --disable-pip "
        "--requirement reports/requirements.locked.txt --format json --output reports/sca.json"
    ) in sca.stdout.splitlines()
    sbom_export = (
        "/nonexistent/uv export --quiet --locked --all-packages --no-dev --no-emit-project --no-emit-workspace "
        "--format requirements-txt --output-file reports/requirements.sbom.txt"
    )
    sbom = _make(tmp_path, "-n", "sbom", "UV=/nonexistent/uv", stub=False)
    assert (sbom.returncode, sbom.stderr) == (0, "")
    assert (
        f"{sbom_export} && /nonexistent/uv tool run --exclude-newer '2026-10-06T00:00:00Z' "
        "--from cyclonedx-bom==7.5.0 cyclonedx-py requirements "
        "--output-format JSON --output-file reports/sbom.cdx.json reports/requirements.sbom.txt"
    ) in sbom.stdout.splitlines()
    # The SBOM describes what ships (runtime deps only); SCA audits every group, dev tools included.
    assert " --no-dev " in sbom.stdout
    assert "--no-dev" not in sca.stdout
    assert not (tmp_path / "reports").exists()  # dry run executes nothing


@pytest.mark.ac("IDP-18:AC-2")
def test_tool_pins_are_overridable(tmp_path: Path) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    sca = _make(tmp_path, "-n", "sca", "IDP_PIP_AUDIT_SPEC=pip-audit==9.9.9", stub=False)
    assert (sca.returncode, sca.stderr) == (0, "")
    # IDP-21: the --exclude-newer option now sits between `tool run` and `--from`.
    assert "uv tool run --exclude-newer '2026-10-06T00:00:00Z' --from pip-audit==9.9.9 pip-audit " in sca.stdout
    assert "pip-audit==2.10.1" not in sca.stdout
    sbom = _make(tmp_path, "-n", "sbom", "IDP_CYCLONEDX_SPEC=cyclonedx-bom==9.9.9", stub=False)
    assert (sbom.returncode, sbom.stderr) == (0, "")
    assert (
        "uv tool run --exclude-newer '2026-10-06T00:00:00Z' --from cyclonedx-bom==9.9.9 cyclonedx-py requirements "
    ) in sbom.stdout
    assert "cyclonedx-bom==7.5.0" not in sbom.stdout


# --- IDP-21 AC-1 / AC-4: reproducible tool resolution with --exclude-newer ----------------------------------------


_SCA_TOOL_RUN = "/nonexistent/uv tool run --exclude-newer '{date}' --from pip-audit==2.10.1 pip-audit "
_SBOM_TOOL_RUN = (
    "/nonexistent/uv tool run --exclude-newer '{date}' --from cyclonedx-bom==7.5.0 cyclonedx-py requirements "
)
_EXCLUDE_NEWER_EMPTY = "IDP_TOOLS_EXCLUDE_NEWER is empty: set it to a fixed date"
_EXCLUDE_NEWER_MALFORMED = "IDP_TOOLS_EXCLUDE_NEWER must be a single value without spaces or single quotes"


def _tool_run_line(result: subprocess.CompletedProcess[str], target: str) -> str:
    """The single dry-run line that runs the pinned tool for `target` (export and tool run share one line)."""
    lines = [line for line in result.stdout.splitlines() if " tool run " in line]
    assert len(lines) == 1, f"expected one `uv tool run` line for {target}, got: {result.stdout!r}"
    return lines[0]


@pytest.mark.ac("IDP-21:AC-1")
@pytest.mark.parametrize(
    ("target", "tool_run", "export_start"),
    [
        ("sca", _SCA_TOOL_RUN, "/nonexistent/uv export --quiet --locked --all-packages --no-emit-project "),
        ("sbom", _SBOM_TOOL_RUN, "/nonexistent/uv export --quiet --locked --all-packages --no-dev --no-emit-project "),
    ],
    ids=["sca", "sbom"],
)
def test_tool_runs_pass_exclude_newer_in_dry_run(tmp_path: Path, target: str, tool_run: str, export_start: str) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    result = _make(tmp_path, "-n", target, "UV=/nonexistent/uv", stub=False)
    assert (result.returncode, result.stderr) == (0, "")
    line = _tool_run_line(result, target)
    export, _, tool = line.partition(" && ")
    assert export.startswith(export_start)
    assert "--exclude-newer" not in export  # uv export reads uv.lock and resolves nothing
    assert tool.startswith(tool_run.format(date="2026-10-06T00:00:00Z"))  # option before --from and the command
    assert line.count("--exclude-newer") == 1
    assert not (tmp_path / "reports").exists()


@pytest.mark.ac("IDP-21:AC-1")
def test_exclude_newer_default_is_fixed_and_conditional(tmp_path: Path) -> None:
    _require(DEFAULTS_MK)
    lines = DEFAULTS_MK.read_text(encoding="utf-8").splitlines()
    assignments = [line for line in lines if line.startswith("IDP_TOOLS_EXCLUDE_NEWER")]
    assert assignments == ["IDP_TOOLS_EXCLUDE_NEWER ?= 2026-10-06T00:00:00Z"]  # literal UTC instant, set with ?=
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    from_env = _make(
        tmp_path,
        "-n",
        "sca",
        "UV=/nonexistent/uv",
        stub=False,
        env_extra={"IDP_TOOLS_EXCLUDE_NEWER": "2027-02-03T04:05:06Z"},
    )
    assert (from_env.returncode, from_env.stderr) == (0, "")
    assert _SCA_TOOL_RUN.format(date="2027-02-03T04:05:06Z") in _tool_run_line(from_env, "sca")
    assert "2026-10-06T00:00:00Z" not in from_env.stdout
    tenant_dir = tmp_path / "tenant-assignment"
    tenant_dir.mkdir()
    (tenant_dir / "Makefile").write_text(
        "IDP_TOOLS_EXCLUDE_NEWER = 2028-01-01T00:00:00Z\n"
        "include $(IDP_PROFILE_DIR)/defaults.mk\n"
        "build:\n\t@echo tenant-build\n"
    )
    from_makefile = _make(tenant_dir, "-n", "sbom", "UV=/nonexistent/uv", stub=False)
    assert (from_makefile.returncode, from_makefile.stderr) == (0, "")
    assert _SBOM_TOOL_RUN.format(date="2028-01-01T00:00:00Z") in _tool_run_line(from_makefile, "sbom")
    assert "2026-10-06T00:00:00Z" not in from_makefile.stdout


@pytest.mark.ac("IDP-21:AC-1")
def test_exclude_newer_is_overridable(tmp_path: Path) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    override = "IDP_TOOLS_EXCLUDE_NEWER=2030-01-01T00:00:00Z"
    sca = _make(tmp_path, "-n", "sca", "UV=/nonexistent/uv", override, stub=False)
    assert (sca.returncode, sca.stderr) == (0, "")
    assert _SCA_TOOL_RUN.format(date="2030-01-01T00:00:00Z") in _tool_run_line(sca, "sca")
    assert "2026-10-06T00:00:00Z" not in sca.stdout
    sbom = _make(tmp_path, "-n", "sbom", "UV=/nonexistent/uv", override, stub=False)
    assert (sbom.returncode, sbom.stderr) == (0, "")
    assert _SBOM_TOOL_RUN.format(date="2030-01-01T00:00:00Z") in _tool_run_line(sbom, "sbom")
    assert "2026-10-06T00:00:00Z" not in sbom.stdout


@pytest.mark.ac("IDP-21:AC-4")
@pytest.mark.parametrize("target", ["sbom", "sca"])
@pytest.mark.parametrize(
    ("args", "env_extra"),
    [(("IDP_TOOLS_EXCLUDE_NEWER=",), {}), ((), {"IDP_TOOLS_EXCLUDE_NEWER": "   "})],
    ids=["empty", "whitespace"],
)
@pytest.mark.parametrize("stub", [True, False], ids=["stubbed-cmd", "default-cmd"])
def test_empty_exclude_newer_fails_closed(
    tmp_path: Path, target: str, args: tuple[str, ...], env_extra: dict[str, str], stub: bool
) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    # UV points nowhere, so even without the guard no real tool can run.
    result = _make(tmp_path, target, "UV=/nonexistent/uv", *args, stub=stub, env_extra=env_extra)
    assert result.returncode == 2
    assert _EXCLUDE_NEWER_EMPTY in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "reports").exists()
    dry_run = _make(tmp_path, "-n", target, "UV=/nonexistent/uv", *args, stub=stub, env_extra=env_extra)
    assert dry_run.returncode == 2  # make expands recipes under -n too
    assert _EXCLUDE_NEWER_EMPTY in dry_run.stderr
    assert dry_run.stdout == ""


@pytest.mark.ac("IDP-21:AC-4")
@pytest.mark.parametrize("target", ["sbom", "sca"])
@pytest.mark.parametrize(
    "value",
    ["2026-10-06T00:00:00Z --index-url https://evil/simple", "x';touch pwned;'"],
    ids=["multi-word", "single-quote"],
)
@pytest.mark.parametrize("stub", [True, False], ids=["stubbed-cmd", "default-cmd"])
def test_malformed_exclude_newer_fails_closed(tmp_path: Path, target: str, value: str, stub: bool) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    override = f"IDP_TOOLS_EXCLUDE_NEWER={value}"
    result = _make(tmp_path, target, "UV=/nonexistent/uv", override, stub=stub)
    assert result.returncode == 2
    assert _EXCLUDE_NEWER_MALFORMED in result.stderr
    assert _EXCLUDE_NEWER_EMPTY not in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "reports").exists()
    assert not (tmp_path / "pwned").exists()  # nothing reached the shell
    dry_run = _make(tmp_path, "-n", target, "UV=/nonexistent/uv", override, stub=stub)
    assert dry_run.returncode == 2  # make expands recipes under -n too
    assert _EXCLUDE_NEWER_MALFORMED in dry_run.stderr
    assert dry_run.stdout == ""


@pytest.mark.ac("IDP-21:AC-4")
def test_empty_exclude_newer_is_not_checked_at_parse_time(tmp_path: Path) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    build = _make(tmp_path, "build", "IDP_TOOLS_EXCLUDE_NEWER=")
    assert (build.returncode, build.stdout, build.stderr) == (0, "tenant-build\n", "")
    default_goal = _make(tmp_path, "IDP_TOOLS_EXCLUDE_NEWER=")
    assert (default_goal.returncode, default_goal.stdout, default_goal.stderr) == (0, "tenant-build\n", "")
    # The check lives in the sca recipe: only running it fails.
    sca = _make(tmp_path, "sca", "IDP_TOOLS_EXCLUDE_NEWER=")
    assert sca.returncode == 2
    assert _EXCLUDE_NEWER_EMPTY in sca.stderr


@pytest.mark.ac("IDP-18:AC-2")
@pytest.mark.parametrize("include_first", [True, False], ids=["include-first", "include-last"])
def test_defaults_mk_keeps_tenant_default_goal(tmp_path: Path, include_first: bool) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\nother:\n\t@echo tenant-other\n", include_first)
    result = _make(tmp_path)
    assert (result.returncode, result.stdout, result.stderr) == (0, "tenant-build\n", "")


@pytest.mark.ac("IDP-18:AC-2")
def test_defaults_mk_needs_no_commands_at_parse_time(tmp_path: Path) -> None:
    _require(DEFAULTS_MK)
    text = DEFAULTS_MK.read_text(encoding="utf-8")
    assert "$(shell" not in text
    assert "${shell" not in text
    assert "!=" not in text
    _tenant(tmp_path, "build:\n\t@echo tenant-build\n")
    result = _make(tmp_path, "-n", "sbom", "UV=/nonexistent/uv", stub=False)
    assert (result.returncode, result.stderr) == (0, "")


@pytest.mark.ac("IDP-18:AC-2")
def test_recursive_make_with_bare_export_still_gets_defaults(tmp_path: Path) -> None:
    _tenant(tmp_path, "export\nbuild:\n\t@echo tenant-build\nouter:\n\t@$(MAKE) --no-print-directory sca\n")
    result = _make(tmp_path, "outer")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout.splitlines()[-1] == "default-sca"


@pytest.mark.ac("IDP-18:AC-3")
def test_including_defaults_twice_gives_no_warnings(tmp_path: Path) -> None:
    include = "include $(IDP_PROFILE_DIR)/defaults.mk\n"
    (tmp_path / "Makefile").write_text(include + "build:\n\t@echo tenant-build\n" + include)
    sca = _make(tmp_path, "sca")
    assert (sca.returncode, sca.stderr) == (0, "")
    assert sca.stdout.splitlines() == ["echo default-sca", "default-sca"]  # the default recipe runs once
    default = _make(tmp_path)
    assert (default.returncode, default.stdout, default.stderr) == (0, "tenant-build\n", "")


@pytest.mark.ac("IDP-18:AC-3")
@pytest.mark.parametrize("include_first", [True, False], ids=["include-first", "include-last"])
def test_tenant_target_overrides_default_without_warnings(tmp_path: Path, include_first: bool) -> None:
    _tenant(tmp_path, "build:\n\t@echo tenant-build\nsca:\n\t@echo tenant-sca\n", include_first)
    sca = _make(tmp_path, "sca")
    assert "overriding recipe" not in sca.stderr
    assert "ignoring old recipe" not in sca.stderr
    assert (sca.returncode, sca.stdout, sca.stderr) == (0, "tenant-sca\n", "")
    sbom = _make(tmp_path, "sbom")
    assert (sbom.returncode, sbom.stderr) == (0, "")
    assert sbom.stdout.splitlines()[-1] == "default-sbom"


# --- AC-4: idp profile show and discovery ------------------------------------------------------------------------


DEMO_YAML = (
    "name: demo\n"
    "description: Demo profile\n"
    "setup:\n"
    "- name: Sync\n"
    "  run: uv sync --frozen\n"
    "defaultTargets:\n"
    "- sbom\n"
    "- sca\n"
    "coverage:\n"
    "  format: cobertura\n"
    "sbom:\n"
    "  tool: cyclonedx-py\n"
    "  format: cyclonedx-json\n"
    "sca:\n"
    "  tool: pip-audit\n"
)


@pytest.mark.ac("IDP-18:AC-4")
def test_profile_show_prints_yaml_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path.resolve() / "packaged"
    demo = _write_profile(root, "demo", DEMO_YAML)
    _use_roots(monkeypatch, root, tmp_path.resolve() / "missing")
    assert _run(["profile", "show", "demo"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == DEMO_YAML + f"dir: {demo}\n"


@pytest.mark.ac("IDP-18:AC-4")
def test_profile_show_python_uv_from_workspace(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["profile", "show", "python-uv"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    shown = yaml.safe_load(captured.out)
    assert list(shown) == ["name", "description", "setup", "defaultTargets", "coverage", "sbom", "sca", "dir"]
    assert shown["name"] == "python-uv"
    assert shown["defaultTargets"] == ["sbom", "sca"]
    assert shown["dir"] == str(PROFILE_DIR)


@pytest.mark.ac("IDP-18:AC-4")
def test_profile_show_json_prints_one_json_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path.resolve() / "packaged"
    demo = _write_profile(root, "demo", DEMO_YAML)
    _use_roots(monkeypatch, root, tmp_path.resolve() / "missing")
    assert _run(["profile", "show", "demo", "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        '{"name": "demo", "description": "Demo profile", "setup": [{"name": "Sync", "run": "uv sync --frozen"}], '
        '"defaultTargets": ["sbom", "sca"], "coverage": {"format": "cobertura"}, '
        '"sbom": {"tool": "cyclonedx-py", "format": "cyclonedx-json"}, "sca": {"tool": "pip-audit"}, '
        f'"dir": "{demo}"}}\n'
    )


@pytest.mark.ac("IDP-18:AC-4")
def test_profiles_resolve_from_checkout_in_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profiles = _profiles()
    assert profiles.profiles_root() == REPO / "build-profiles"  # editable workspace install: no packaged copy
    checkout = tmp_path.resolve() / "checkout"
    demo = _write_profile(checkout, "demo", DEMO_YAML)
    (checkout / "no-profile-yaml").mkdir()
    _use_roots(monkeypatch, tmp_path.resolve() / "missing", checkout)
    assert profiles.profiles_root() == checkout
    assert profiles.available(checkout) == ["demo"]
    resolved = profiles.resolve("demo")
    assert resolved["dir"] == str(demo)
    assert resolved["description"] == "Demo profile"
    with pytest.raises(profiles.ProfileError) as excinfo:
        profiles.resolve("no-profile-yaml")
    assert excinfo.value.lines == ["'no-profile-yaml' not found (available: demo)"]


@pytest.mark.ac("IDP-18:AC-4")
def test_packaged_profiles_take_precedence_over_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packaged, checkout = tmp_path.resolve() / "packaged", tmp_path.resolve() / "checkout"
    packaged_demo = _write_profile(packaged, "demo", DEMO_YAML.replace("Demo profile", "packaged copy"))
    _write_profile(checkout, "demo", DEMO_YAML.replace("Demo profile", "checkout copy"))
    _write_profile(checkout, "only-checkout", _valid_doc("only-checkout"))
    profiles = _use_roots(monkeypatch, packaged, checkout)
    assert profiles.profiles_root() == packaged
    resolved = profiles.resolve("demo")
    assert resolved["description"] == "packaged copy"
    assert resolved["dir"] == str(packaged_demo)
    with pytest.raises(profiles.ProfileError) as excinfo:  # roots are not merged
        profiles.resolve("only-checkout")
    assert excinfo.value.lines == ["'only-checkout' not found (available: demo)"]


@pytest.mark.ac("IDP-18:AC-4")
def test_checkout_candidate_absent_in_shallow_layout() -> None:
    profiles = _profiles()
    assert profiles._checkout_dir(Path("/app/idp_gate/profiles.py")) is None  # pip install --target /app


@pytest.mark.ac("IDP-18:AC-4")
def test_checkout_candidate_requires_this_repo_source_tree(tmp_path: Path) -> None:
    profiles = _profiles()
    module = tmp_path / "packages" / "idp-gate" / "src" / "idp_gate" / "profiles.py"
    (tmp_path / "build-profiles").mkdir()
    assert profiles._checkout_dir(module) is None  # unrelated build-profiles/ four levels up is ignored
    (tmp_path / "packages" / "idp-gate").mkdir(parents=True)
    (tmp_path / "packages" / "idp-gate" / "pyproject.toml").write_text("[project]\n")
    assert profiles._checkout_dir(module) == tmp_path / "build-profiles"
    venv_module = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages" / "idp_gate" / "profiles.py"
    assert profiles._checkout_dir(venv_module) is None


@pytest.mark.ac("IDP-18:AC-5")
def test_no_checkout_candidate_lists_only_real_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    profiles = _profiles()
    packaged = tmp_path.resolve() / "no-packaged"
    monkeypatch.setattr(profiles, "_PACKAGED_DIR", packaged)
    monkeypatch.setattr(profiles, "_CHECKOUT_DIR", None)
    assert _run(["profile", "show", "python-uv"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"profile show: no build profiles found (looked in: {packaged})\n"


@pytest.mark.ac("IDP-18:AC-4")
@pytest.mark.ac("IDP-21:AC-2")
def test_hatch_config_packages_profiles_through_build_hook() -> None:
    assert HATCH_BUILD.is_file(), "packages/idp-gate/hatch_build.py is missing (IDP-21 build hook not implemented)"
    config = tomllib.loads(PACKAGE_PYPROJECT.read_text(encoding="utf-8"))
    build = config.get("tool", {}).get("hatch", {}).get("build", {})
    assert build.get("hooks", {}).get("custom") in ({}, {"path": "hatch_build.py"})
    wheel = build.get("targets", {}).get("wheel", {})
    assert "force-include" not in wheel  # a static mapping can neither filter nor work from the sdist
    assert wheel.get("packages") == ["src/idp_gate"]
    assert config["project"]["dependencies"] == ["pyyaml>=6.0", "jsonschema>=4.23"]
    assert "hatchling>=1.25" in config.get("dependency-groups", {}).get("dev", [])


# --- IDP-21: build hook unit tests (hatch_build.py loaded from its file at test time) ------------------------------


def _hatch_build() -> ModuleType:
    """Load `packages/idp-gate/hatch_build.py` lazily, so a missing hook fails each test instead of collection."""
    if not HATCH_BUILD.is_file():
        pytest.fail("packages/idp-gate/hatch_build.py is missing (IDP-21 build hook not implemented)")
    spec = importlib.util.spec_from_file_location("idp_gate_hatch_build", HATCH_BUILD)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        if exc.name is None or not exc.name.startswith("hatchling"):
            raise
        pytest.fail("hatchling is not importable: add it to idp-gate's dev dependency group (IDP-21 plan)")
    return module


def _files(root: Path, relpaths: list[str]) -> None:
    for rel in relpaths:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {rel}\n")


@pytest.mark.ac("IDP-21:AC-2")
def test_profile_file_selection_applies_allow_list(tmp_path: Path) -> None:
    hook = _hatch_build()
    source = tmp_path / "build-profiles"
    _files(
        source,
        [
            "python-uv/profile.yaml",
            "python-uv/defaults.mk",
            "python-uv/agent-notes.md",
            "python-uv/sub/extra.md",
            "python-uv/notes.txt",
            "python-uv/.env",
            "python-uv/.hidden.md",
            "python-uv/sub/notes.txt",
            "python-uv/__pycache__/x.pyc",
            "python-uv/.cache/cached.yaml",
            ".git/config.mk",
            "README",
        ],
    )
    (source / "python-uv" / "dir.md").mkdir()  # a directory with an allowed suffix is not a file
    (source / "python-uv" / "link.md").symlink_to(source / "python-uv" / "agent-notes.md")
    assert hook.select_profile_files(source) == [
        Path("python-uv/agent-notes.md"),
        Path("python-uv/defaults.mk"),
        Path("python-uv/profile.yaml"),
        Path("python-uv/sub/extra.md"),
    ]


@pytest.mark.ac("IDP-21:AC-3")
def test_profile_file_selection_prefers_sdist_copy(tmp_path: Path) -> None:
    hook = _hatch_build()
    project = tmp_path / "packages" / "idp-gate"
    _files(tmp_path / "build-profiles", ["python-uv/profile.yaml"])  # the checkout: two levels above the project
    _files(project / "build-profiles", ["python-uv/profile.yaml"])  # the copy inside an unpacked sdist
    assert hook.profiles_source(project) == project / "build-profiles"
    shutil.rmtree(project / "build-profiles")
    assert hook.profiles_source(project) == tmp_path / "build-profiles"


@pytest.mark.ac("IDP-21:AC-3")
def test_profile_file_selection_fails_without_profiles(tmp_path: Path) -> None:
    hook = _hatch_build()
    project = tmp_path / "packages" / "idp-gate"
    project.mkdir(parents=True)
    with pytest.raises(RuntimeError) as excinfo:
        hook.profiles_source(project)
    message = str(excinfo.value)
    assert message.startswith("idp-gate build: build profiles not found (looked in: ")
    assert str(project / "build-profiles") in message
    assert str(tmp_path / "build-profiles") in message
    source = tmp_path / "build-profiles"
    _files(source, ["python-uv/defaults.mk", "python-uv/agent-notes.md", "python-uv/notes.txt", ".x/profile.yaml"])
    # nothing selected is a profile.yaml: fail closed, no profile-less wheel
    with pytest.raises(RuntimeError, match=r"no \*/profile\.yaml selected"):
        hook.select_profile_files(source)


@pytest.mark.ac("IDP-21:AC-3")
def test_profile_source_in_unpacked_sdist_never_falls_back_to_parent(tmp_path: Path) -> None:
    hook = _hatch_build()
    project = tmp_path / "packages" / "idp-gate"
    _files(tmp_path / "build-profiles", ["python-uv/profile.yaml"])  # outside the sdist: must be ignored
    _files(project, ["PKG-INFO"])  # marks an unpacked sdist without its own build-profiles/
    with pytest.raises(RuntimeError) as excinfo:
        hook.profiles_source(project)
    assert str(excinfo.value) == f"idp-gate build: build profiles not found (looked in: {project / 'build-profiles'})"


def _build_hook(module: ModuleType, root: Path, target_name: str) -> Any:
    """A real `ProfilesBuildHook` (hatchling's constructor only stores its arguments)."""
    return module.ProfilesBuildHook(str(root), {}, None, None, str(root / "dist"), target_name)


@pytest.mark.ac("IDP-21:AC-2")
@pytest.mark.parametrize(("target_name", "prefix"), [("wheel", "idp_gate/build_profiles"), ("sdist", "build-profiles")])
def test_build_hook_maps_profiles_per_target(tmp_path: Path, target_name: str, prefix: str) -> None:
    hook = _hatch_build()
    project = tmp_path / "packages" / "idp-gate"
    project.mkdir(parents=True)
    source = tmp_path / "build-profiles"
    _files(source, ["python-uv/profile.yaml", "python-uv/defaults.mk", "python-uv/notes.txt"])
    build_data: dict[str, Any] = {"force_include": {}}
    _build_hook(hook, project, target_name).initialize("standard", build_data)
    assert build_data == {
        "force_include": {
            str(source / "python-uv/defaults.mk"): f"{prefix}/python-uv/defaults.mk",
            str(source / "python-uv/profile.yaml"): f"{prefix}/python-uv/profile.yaml",
        }
    }


@pytest.mark.ac("IDP-21:AC-2")
def test_build_hook_fails_closed_on_unsupported_target(tmp_path: Path) -> None:
    hook = _hatch_build()
    project = tmp_path / "packages" / "idp-gate"
    project.mkdir(parents=True)
    _files(tmp_path / "build-profiles", ["python-uv/profile.yaml"])
    build_data: dict[str, Any] = {"force_include": {}}
    with pytest.raises(RuntimeError) as excinfo:
        _build_hook(hook, project, "binary").initialize("standard", build_data)
    assert str(excinfo.value) == "idp-gate build: unsupported build target binary"
    assert build_data == {"force_include": {}}


# --- IDP-24 AC-3 / AC-4: the build hook never follows symlinked directories ----------------------------------------


@pytest.mark.ac("IDP-24:AC-3")
def test_profile_file_selection_does_not_follow_symlinked_directories(tmp_path: Path) -> None:
    hook = _hatch_build()
    source = tmp_path / "build-profiles"
    _files(source, ["python-uv/profile.yaml", "python-uv/defaults.mk", "python-uv/sub/.keep"])
    outside = tmp_path / "outside"
    _files(outside, ["x.md", "nested/y.yaml"])
    (source / "python-uv" / "linked").symlink_to(outside, target_is_directory=True)
    (source / "python-uv" / "sub" / "linked").symlink_to(outside, target_is_directory=True)
    (source / "python-uv" / "alias").symlink_to(Path("..") / "python-uv", target_is_directory=True)
    assert (source / "python-uv" / "linked" / "x.md").is_file()  # the link resolves: only the walk may skip it
    assert hook.select_profile_files(source) == [Path("python-uv/defaults.mk"), Path("python-uv/profile.yaml")]


@pytest.mark.ac("IDP-24:AC-4")
def test_profiles_source_accepts_checkout_behind_symlinked_ancestor(tmp_path: Path) -> None:
    """Only the candidate itself must not be a symlink; a symlinked ancestor (macOS /tmp, spec A7) is fine."""
    hook = _hatch_build()
    real = tmp_path / "real"
    _files(real / "build-profiles", ["python-uv/profile.yaml"])
    (real / "packages" / "idp-gate").mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert hook.profiles_source(alias / "packages" / "idp-gate") == alias / "build-profiles"


_SYMLINK_MESSAGE = "idp-gate build: build profiles source is a symlink, refusing to follow it: "


def _symlinked_profiles_source(tmp_path: Path, layout: str, dangling: bool) -> tuple[Path, Path]:
    """`(project root, the symlinked build-profiles candidate)` for one IDP-24 AC-4 layout.

    - `checkout`: the checkout's `<root>/../../build-profiles` is a symlink, no sdist copy.
    - `sdist`: an unpacked sdist (`PKG-INFO`) whose `<root>/build-profiles` is a symlink.
    - `checkout-with-real-parent`: `<root>/build-profiles` is a symlink while the checkout's real
      `<root>/../../build-profiles` exists; the hook must not fall back to it.
    """
    project = tmp_path / "packages" / "idp-gate"
    project.mkdir(parents=True)
    target = tmp_path / "elsewhere" / "profiles"
    if not dangling:
        _files(target, ["python-uv/profile.yaml", "python-uv/defaults.mk"])
    link = tmp_path / "build-profiles" if layout == "checkout" else project / "build-profiles"
    if layout == "sdist":
        _files(project, ["PKG-INFO"])
    if layout == "checkout-with-real-parent":
        _files(tmp_path / "build-profiles", ["python-uv/profile.yaml"])
    link.symlink_to(target, target_is_directory=True)
    return project, link


@pytest.mark.ac("IDP-24:AC-4")
@pytest.mark.parametrize("dangling", [False, True], ids=["to-profiles-dir", "dangling"])
@pytest.mark.parametrize("layout", ["checkout", "sdist", "checkout-with-real-parent"])
def test_profiles_source_fails_closed_on_symlinked_source(tmp_path: Path, layout: str, dangling: bool) -> None:
    hook = _hatch_build()
    project, link = _symlinked_profiles_source(tmp_path, layout, dangling)
    with pytest.raises(RuntimeError) as excinfo:
        hook.profiles_source(project)
    assert str(excinfo.value) == f"{_SYMLINK_MESSAGE}{link}"


@pytest.mark.ac("IDP-24:AC-4")
@pytest.mark.parametrize("target_name", ["wheel", "sdist"])
def test_build_hook_fails_closed_on_symlinked_profiles_source(tmp_path: Path, target_name: str) -> None:
    hook = _hatch_build()
    project, link = _symlinked_profiles_source(tmp_path, "checkout", dangling=False)
    build_data: dict[str, Any] = {"force_include": {}}
    with pytest.raises(RuntimeError) as excinfo:
        _build_hook(hook, project, target_name).initialize("standard", build_data)
    assert str(excinfo.value) == f"{_SYMLINK_MESSAGE}{link}"
    assert build_data == {"force_include": {}}


# --- Session builds: one direct wheel, one sdist -> wheel, both from a temporary copy with stray files -------------


_PROFILE_FILES = ("python-uv/agent-notes.md", "python-uv/defaults.mk", "python-uv/profile.yaml")
_STRAY_FILES = ("python-uv/notes.txt", "python-uv/.env", "python-uv/.hidden.md", "python-uv/sub/notes.txt")
_PACKAGE_STRAY_FILES = ("creds.yaml", "notes.txt")  # untracked files next to pyproject.toml must not ship
_SDIST_TOP_LEVEL = frozenset({"PKG-INFO", "pyproject.toml", "hatch_build.py", "src", "tests", "build-profiles"})
_IGNORE_BYTECODE = shutil.ignore_patterns("__pycache__", "*.pyc")


# IDP-24 AC-2: location-only uv variables that may reach `uv build`; every other UV_*/PIP_* variable is stripped.
_UV_ENV_KEEP = frozenset({"UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR"})
# IDP-24 AC-2 (spec A5): the session builds run with these in their base environment; they must never reach uv.
_POLLUTED_ENV = {
    "UV_INDEX_URL": "http://127.0.0.1:9/simple",
    "UV_NO_BUILD_ISOLATION": "1",
    "PIP_INDEX_URL": "http://127.0.0.1:9/simple",
}


@dataclass(frozen=True)
class _Build:
    """Outcome of one `uv build`; tests assert on it so a failed build is a test failure, not a fixture error.

    `env_names` and `base_env_names` hold variable NAMES only (never values), so no secret reaches test output.
    """

    out_dir: Path
    returncode: int
    stderr: str
    argv: tuple[str, ...]
    env_names: frozenset[str]
    base_env_names: frozenset[str]


def _uv_build_env(base: dict[str, str]) -> dict[str, str]:
    """The environment passed to `uv build`: `base` without UV_*/PIP_* variables, except the `_UV_ENV_KEEP` names."""
    return {k: v for k, v in base.items() if k in _UV_ENV_KEEP or not k.startswith(("UV_", "PIP_"))}


def _uv_build_argv(tree: Path, out_dir: Path, *flags: str) -> list[str]:
    """The `uv build` command line used by both session builds."""
    return [
        "uv",
        "build",
        *flags,
        "--offline",
        "--no-config",
        "--build-constraint",
        str(BUILD_CONSTRAINTS),
        "--require-hashes",
        "--out-dir",
        str(out_dir),
        str(tree / "packages" / "idp-gate"),
    ]


def _uv_build(tree: Path, out_dir: Path, *flags: str) -> _Build:
    base = dict(os.environ) | _POLLUTED_ENV  # IDP-24 spec A5: polluted on purpose, stripped by _uv_build_env
    env = _uv_build_env(base)
    argv = _uv_build_argv(tree, out_dir, *flags)
    result = subprocess.run(
        argv,
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return _Build(out_dir, result.returncode, result.stderr, tuple(argv), frozenset(env), frozenset(base))


@pytest.fixture(scope="session")
def profile_build_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A temporary copy of the idp-gate build tree with stray files in the python-uv profile and the package dir."""
    if shutil.which("uv") is None:
        pytest.skip("uv is not installed")
    tree = tmp_path_factory.mktemp("profile-build-tree")
    package = tree / "packages" / "idp-gate"
    package.mkdir(parents=True)
    shutil.copy2(PACKAGE_PYPROJECT, package / "pyproject.toml")
    shutil.copy2(HATCH_BUILD, package / "hatch_build.py")
    shutil.copytree(PACKAGE_DIR / "src", package / "src", ignore=_IGNORE_BYTECODE)
    shutil.copytree(REPO / "build-profiles", tree / "build-profiles", ignore=_IGNORE_BYTECODE)
    _files(tree / "build-profiles", list(_STRAY_FILES))
    _files(package, list(_PACKAGE_STRAY_FILES))
    (tree / "build-profiles" / "python-uv" / "link.md").symlink_to(
        tree / "build-profiles" / "python-uv" / "agent-notes.md"
    )
    return tree


@pytest.fixture(scope="session")
def built_wheel(profile_build_tree: Path, tmp_path_factory: pytest.TempPathFactory) -> _Build:
    """The direct wheel (`uv build --wheel`), built once per session."""
    return _uv_build(profile_build_tree, tmp_path_factory.mktemp("direct"), "--wheel")


@pytest.fixture(scope="session")
def sdist_built_wheel(profile_build_tree: Path, tmp_path_factory: pytest.TempPathFactory) -> _Build:
    """`uv build` (sdist, then the wheel built from that sdist), built once per session."""
    return _uv_build(profile_build_tree, tmp_path_factory.mktemp("sdist"))


def _members(archive: Path, prefix: str) -> dict[str, bytes]:
    """`{path below prefix: bytes}` of the regular files under `prefix` in a wheel or sdist."""
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as zf:
            return {n[len(prefix) :]: zf.read(n) for n in zf.namelist() if n.startswith(prefix) and not n.endswith("/")}
    found: dict[str, bytes] = {}
    with tarfile.open(archive) as tf:
        for info in tf.getmembers():
            if info.name.startswith(prefix) and info.isfile():
                extracted = tf.extractfile(info)
                assert extracted is not None
                found[info.name[len(prefix) :]] = extracted.read()
    return found


def _repo_profile_files() -> dict[str, bytes]:
    return {rel: (REPO / "build-profiles" / rel).read_bytes() for rel in _PROFILE_FILES}


def _profile_show_from_wheel(wheel: Path, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Unzip `wheel` into a site dir and run `profile show python-uv --json` from it in an isolated interpreter."""
    site = tmp_path.resolve() / "site"
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            target = site / name
            assert target.resolve().is_relative_to(site)  # no path traversal out of the site dir
            if not name.endswith("/"):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import idp_gate; from idp_gate.cli import main; "
        "print(idp_gate.__file__, file=sys.stderr); raise SystemExit(main(['profile', 'show', 'python-uv', '--json']))"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(site)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result, site


@pytest.mark.ac("IDP-18:AC-4")
def test_built_wheel_contains_build_profiles(built_wheel: _Build) -> None:
    assert built_wheel.returncode == 0, built_wheel.stderr
    wheel = built_wheel.out_dir / "idp_gate-0.1.0-py3-none-any.whl"
    assert wheel.is_file()
    names = set(zipfile.ZipFile(wheel).namelist())
    expected = {
        "idp_gate/build_profiles/python-uv/profile.yaml",
        "idp_gate/build_profiles/python-uv/defaults.mk",
        "idp_gate/build_profiles/python-uv/agent-notes.md",
        "idp_gate/schemas/build-profile.v1.json",
    }
    assert sorted(expected - names) == []


@pytest.mark.ac("IDP-18:AC-4")
def test_installed_wheel_resolves_packaged_python_uv(built_wheel: _Build, tmp_path: Path) -> None:
    assert built_wheel.returncode == 0, built_wheel.stderr
    result, site = _profile_show_from_wheel(built_wheel.out_dir / "idp_gate-0.1.0-py3-none-any.whl", tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == f"{site / 'idp_gate' / '__init__.py'}\n"  # the wheel copy, not the editable install
    shown = json.loads(result.stdout)
    assert shown["name"] == "python-uv"
    assert shown["dir"] == str(site / "idp_gate" / "build_profiles" / "python-uv")


@pytest.mark.ac("IDP-21:AC-2")
def test_wheel_build_profiles_contain_only_allowed_files(built_wheel: _Build) -> None:
    assert built_wheel.returncode == 0, built_wheel.stderr
    members = _members(built_wheel.out_dir / "idp_gate-0.1.0-py3-none-any.whl", "idp_gate/build_profiles/")
    assert sorted(members) == ["python-uv/agent-notes.md", "python-uv/defaults.mk", "python-uv/profile.yaml"]
    assert members == _repo_profile_files()


@pytest.mark.ac("IDP-21:AC-2")
def test_sdist_build_profiles_contain_only_allowed_files(sdist_built_wheel: _Build) -> None:
    sdist = sdist_built_wheel.out_dir / "idp_gate-0.1.0.tar.gz"
    assert sdist.is_file(), sdist_built_wheel.stderr  # the sdist step runs before the wheel-from-sdist step
    members = _members(sdist, "idp_gate-0.1.0/build-profiles/")
    assert sorted(members) == ["python-uv/agent-notes.md", "python-uv/defaults.mk", "python-uv/profile.yaml"]
    assert members == _repo_profile_files()


@pytest.mark.ac("IDP-21:AC-2")
def test_sdist_contains_only_allow_listed_paths(sdist_built_wheel: _Build) -> None:
    sdist = sdist_built_wheel.out_dir / "idp_gate-0.1.0.tar.gz"
    assert sdist.is_file(), sdist_built_wheel.stderr
    members = sorted(_members(sdist, "idp_gate-0.1.0/"))
    assert "pyproject.toml" in members
    assert "src/idp_gate/cli.py" in members
    strays = [m for m in members if m.split("/", 1)[0] not in _SDIST_TOP_LEVEL]
    assert strays == []  # creds.yaml and notes.txt next to pyproject.toml stay out


@pytest.mark.ac("IDP-21:AC-3")
def test_sdist_built_wheel_has_same_build_profiles_as_direct_wheel(
    built_wheel: _Build, sdist_built_wheel: _Build
) -> None:
    assert built_wheel.returncode == 0, built_wheel.stderr
    assert sdist_built_wheel.returncode == 0, sdist_built_wheel.stderr
    direct = _members(built_wheel.out_dir / "idp_gate-0.1.0-py3-none-any.whl", "idp_gate/build_profiles/")
    from_sdist = _members(sdist_built_wheel.out_dir / "idp_gate-0.1.0-py3-none-any.whl", "idp_gate/build_profiles/")
    assert sorted(from_sdist) == ["python-uv/agent-notes.md", "python-uv/defaults.mk", "python-uv/profile.yaml"]
    assert from_sdist == direct
    assert from_sdist == _repo_profile_files()


@pytest.mark.ac("IDP-21:AC-3")
def test_profile_show_works_from_sdist_built_wheel(sdist_built_wheel: _Build, tmp_path: Path) -> None:
    assert sdist_built_wheel.returncode == 0, sdist_built_wheel.stderr
    result, site = _profile_show_from_wheel(sdist_built_wheel.out_dir / "idp_gate-0.1.0-py3-none-any.whl", tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == f"{site / 'idp_gate' / '__init__.py'}\n"
    assert '"name": "python-uv"' in result.stdout
    shown = json.loads(result.stdout)
    assert shown["dir"] == str(site / "idp_gate" / "build_profiles" / "python-uv")


# --- IDP-24 AC-1 / AC-2: locked, hash-checked build backend and a clean `uv build` environment ---------------------


_REGENERATE_CONSTRAINTS = (
    "uv export --frozen --package idp-gate --only-group dev --no-emit-project "
    "--output-file packages/idp-gate/build-constraints.txt"
)
_Pins = dict[str, tuple[str, frozenset[str]]]


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _locked_closure(root: str = "hatchling") -> _Pins:
    """`{name: (version, {"sha256:..."})}` for `root` and its transitive dependencies, as recorded in uv.lock."""
    packages: dict[str, list[dict[str, Any]]] = {}
    for package in tomllib.loads(UV_LOCK.read_text())["package"]:
        packages.setdefault(_normalize(package["name"]), []).append(package)
    closure: _Pins = {}
    pending = [_normalize(root)]
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        entries = packages.get(name, [])
        assert len(entries) == 1, f"uv.lock must lock exactly one {name}, found {len(entries)}"
        entry = entries[0]
        artifacts = [entry["sdist"]] if "sdist" in entry else []
        artifacts += entry.get("wheels", [])
        closure[name] = (entry["version"], frozenset(a["hash"] for a in artifacts))
        pending += [_normalize(dep["name"]) for dep in entry.get("dependencies", [])]
    return closure


def _parse_constraints(text: str) -> tuple[_Pins, list[str]]:
    """`{name: (version, {"sha256:..."})}` parsed from build-constraints.txt text (continuations joined, markers
    ignored), plus a problem for each line that is not an exact `==` pin or repeats a name."""
    pins: _Pins = {}
    problems: list[str] = []
    for line in text.replace("\\\n", " ").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement, *options = line.split()
        name, sep, version = requirement.partition("==")
        if sep != "==":
            problems.append(f"{requirement!r} {_NOT_EXACT}")
            continue
        if _normalize(name) in pins:
            problems.append(f"duplicate entry for {_normalize(name)}")
            continue
        hashes = frozenset(o.removeprefix("--hash=") for o in options if o.startswith("--hash="))
        pins[_normalize(name)] = (version.split(";", 1)[0], hashes)
    return pins, problems


def _constraints() -> _Pins:
    """`{name: (version, {"sha256:..."})}` parsed from build-constraints.txt (continuations joined, markers ignored)."""
    pins, problems = _parse_constraints(BUILD_CONSTRAINTS.read_text())
    assert problems == [], f"build-constraints.txt: {'; '.join(problems)}"
    return pins


def _wheel_generator(build: _Build) -> list[str]:
    with zipfile.ZipFile(build.out_dir / "idp_gate-0.1.0-py3-none-any.whl") as zf:
        lines = zf.read("idp_gate-0.1.0.dist-info/WHEEL").decode().splitlines()
    return [line for line in lines if line.startswith("Generator:")]


def _stray_uv_pip_names(names: frozenset[str]) -> list[str]:
    return sorted(n for n in names if n.startswith(("UV_", "PIP_")) and n not in _UV_ENV_KEEP)


@pytest.mark.ac("IDP-24:AC-1")
def test_build_constraints_pin_locked_build_backend_with_hashes() -> None:
    assert BUILD_CONSTRAINTS.is_file(), (
        f"packages/idp-gate/build-constraints.txt is missing (IDP-24 AC-1); generate it with: {_REGENERATE_CONSTRAINTS}"
    )
    locked = _locked_closure()
    assert "hatchling" in locked
    assert all(hashes for _, hashes in locked.values())
    drift = f"build-constraints.txt drifted from uv.lock; regenerate: {_REGENERATE_CONSTRAINTS}"
    assert _constraints() == locked, drift


@pytest.mark.ac("IDP-24:AC-1")
def test_session_builds_use_hashed_build_constraints(built_wheel: _Build, sdist_built_wheel: _Build) -> None:
    for build in (built_wheel, sdist_built_wheel):
        argv = list(build.argv)
        assert "--build-constraint" in argv, f"uv build ran without --build-constraint: {argv}"
        assert argv[argv.index("--build-constraint") + 1] == str(BUILD_CONSTRAINTS)
        assert "--require-hashes" in argv, f"uv build ran without --require-hashes: {argv}"
        assert "--offline" in argv
        assert "--no-config" in argv, f"uv build ran without --no-config: {argv}"


@pytest.mark.ac("IDP-24:AC-1")
def test_session_wheels_are_built_by_locked_hatchling(built_wheel: _Build, sdist_built_wheel: _Build) -> None:
    locked_version = _locked_closure()["hatchling"][0]
    for build in (built_wheel, sdist_built_wheel):
        assert build.returncode == 0, build.stderr
        assert _wheel_generator(build) == [f"Generator: hatchling {locked_version}"]


@pytest.mark.ac("IDP-24:AC-2")
def test_uv_build_env_strips_uv_and_pip_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    stripped = {
        "UV_INDEX_URL": "http://127.0.0.1:9/simple",
        "UV_NO_BUILD_ISOLATION": "1",
        "PIP_INDEX_URL": "http://127.0.0.1:9/simple",
        "UV_EXTRA_INDEX_URL": "http://127.0.0.1:9/extra",
        "UV_EXCLUDE_NEWER": "2020-01-01T00:00:00Z",
        "PIP_CONSTRAINT": "/nonexistent/constraints.txt",
    }
    for name in [n for n in os.environ if n.startswith(("UV_", "PIP_"))]:  # e.g. set by `uv run`
        monkeypatch.delenv(name)
    for name, value in stripped.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("UV_CACHE_DIR", "/nonexistent/uv-cache")
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", "/nonexistent/uv-python")
    monkeypatch.setenv("IDP24_UNRELATED", "kept")
    base = dict(os.environ)
    env = _uv_build_env(base)
    assert sorted(set(stripped) & set(env)) == []
    assert env["UV_CACHE_DIR"] == "/nonexistent/uv-cache"
    assert env["UV_PYTHON_INSTALL_DIR"] == "/nonexistent/uv-python"
    assert env["IDP24_UNRELATED"] == "kept"
    assert env["PATH"] == os.environ["PATH"]
    # expected result derived from the names this test set, not from _uv_build_env's predicate
    clean = {k: v for k, v in base.items() if k not in stripped}
    polluted_env = _uv_build_env(base | _POLLUTED_ENV)
    # compare by name only, so a failing assertion never prints environment values
    assert sorted(n for n in env.keys() | clean.keys() if env.get(n) != clean.get(n)) == []
    assert sorted(n for n in polluted_env.keys() | clean.keys() if polluted_env.get(n) != clean.get(n)) == []


@pytest.mark.ac("IDP-24:AC-2")
def test_session_builds_ran_without_uv_and_pip_variables(built_wheel: _Build, sdist_built_wheel: _Build) -> None:
    for build in (built_wheel, sdist_built_wheel):
        assert build.returncode == 0, build.stderr
        assert sorted(set(_POLLUTED_ENV) - build.base_env_names) == [], "session builds must start from _POLLUTED_ENV"
        assert _stray_uv_pip_names(build.env_names) == []


# --- IDP-25: uv sync builds of idp-gate use the locked build backend via [tool.uv] build-constraint-dependencies ----


_ROOT_PYPROJECT = REPO / "pyproject.toml"
_ADR_0012 = REPO / "docs" / "adr" / "0012-build-profiles.md"


def _root_build_constraints(pyproject_text: str) -> object | None:
    """The root `[tool.uv] build-constraint-dependencies` value as written (None if the key is absent)."""
    value: object | None = (
        tomllib.loads(pyproject_text).get("tool", {}).get("uv", {}).get("build-constraint-dependencies")
    )
    return value


_FILE_STALE = "packages/idp-gate/build-constraints.txt is out of date with uv.lock"
_ROOT_STALE = "root pyproject.toml [tool.uv] build-constraint-dependencies is out of date with uv.lock"
_ROOT_ABSENT = "root pyproject.toml has no [tool.uv] build-constraint-dependencies"
_ROOT_REMEDY = "a human must set it (protected path) to:"
_LOCK_STALE = "uv.lock is out of date with pyproject.toml build-constraint-dependencies; run: uv lock"
_BUMP_HINT = "uv lock --upgrade-package hatchling"
_NOT_EXACT = "is not an exact '==' pin"

_HATCHLING_HASH = "sha256:" + "a" * 64
_HATCHLING_HASH_NEW = "sha256:" + "c" * 64
_PACKAGING_HASH = "sha256:" + "b" * 64
# a small, fixed synthetic closure; the real uv.lock is only read by test_build_constraint_sources_agree
_LOCKED: _Pins = {
    "hatchling": ("1.32.4", frozenset({_HATCHLING_HASH})),
    "packaging": ("26.3", frozenset({_PACKAGING_HASH})),
}
_LOCKED_BUMPED: _Pins = {
    "hatchling": ("1.33.0", frozenset({_HATCHLING_HASH_NEW})),
    "packaging": ("26.3", frozenset({_PACKAGING_HASH})),
}
_FILE = (
    "# This file was autogenerated by uv via the following command:\n"
    "#    uv export --frozen --package idp-gate --only-group dev --no-emit-project --output-file x\n"
    f"hatchling==1.32.4 \\\n    --hash={_HATCHLING_HASH}\n"
    f"packaging==26.3 \\\n    --hash={_PACKAGING_HASH}\n"
    "    # via hatchling\n"
)
_ROOT = ["hatchling==1.32.4", "packaging==26.3"]
_RECORDED = [{"name": "hatchling", "specifier": "==1.32.4"}, {"name": "packaging", "specifier": "==26.3"}]

_EXACT_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.+!_-]*)$")  # no markers/extras/ranges
_ROOT_SOURCE = "root pyproject.toml"


def _parse_exact_pins(entries: object, source: str) -> tuple[dict[str, str], list[str]]:
    """`{name: version}` from a list of `name==version` strings, plus a problem for every entry that is not one."""
    if not isinstance(entries, list):
        return {}, [f"{source}: expected a list of strings, got {type(entries).__name__}"]
    pins: dict[str, str] = {}
    problems: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            problems.append(f"{source}: entry {entry!r} is not a string")
            continue
        match = _EXACT_PIN.match(entry.strip())
        if match is None:
            problems.append(f"{entry!r} {_NOT_EXACT}")
            continue
        name = _normalize(match.group(1))
        if name in pins:
            problems.append(f"{source}: duplicate entry for {name}")
            continue
        pins[name] = match.group(2)
    return pins, problems


def _compare(reference: dict[str, str], actual: dict[str, str], reference_name: str = "uv.lock") -> list[str]:
    """Differences of `actual` from `reference`: missing and extra pins and differing versions, sorted by name."""
    differences: list[str] = []
    for name in sorted(reference.keys() | actual.keys()):
        if name not in actual:
            differences.append(f"missing {name}=={reference[name]}")
        elif name not in reference:
            differences.append(f"extra {name}=={actual[name]}")
        elif actual[name] != reference[name]:
            differences.append(f"{name}: {actual[name]}, {reference_name} has {reference[name]}")
    return differences


def _file_drift(locked: _Pins, constraints_text: str) -> list[str]:
    pins, problems = _parse_constraints(constraints_text)
    differences = problems + _compare({n: v for n, (v, _) in locked.items()}, {n: v for n, (v, _) in pins.items()})
    differences += [
        f"{name}: hashes differ from uv.lock"
        for name in sorted(locked.keys() & pins.keys())
        if locked[name][0] == pins[name][0] and locked[name][1] != pins[name][1]
    ]
    if not differences:
        return []
    return [f"{_FILE_STALE}: {'; '.join(differences)}; regenerate: {_REGENERATE_CONSTRAINTS}"]


def _root_drift(versions: dict[str, str], root_entries: object | None) -> tuple[dict[str, str] | None, list[str]]:
    """Root pins when they are well formed (else None), and the root list's problems with the human remedy."""
    expected = ", ".join(f'"{name}=={version}"' for name, version in sorted(versions.items()))
    remedy = f"{_ROOT_REMEDY} [{expected}], then run: uv lock"
    if root_entries is None:
        return None, [f"{_ROOT_ABSENT}; {remedy}"]
    pins, problems = _parse_exact_pins(root_entries, _ROOT_SOURCE)
    differences = problems + _compare(versions, pins)
    if not differences:
        return pins, []
    return (None if problems else pins), [f"{_ROOT_STALE}: {'; '.join(differences)}; {remedy}"]


def _lock_record_drift(root_pins: dict[str, str], lock_recorded: object) -> list[str]:
    """Compare uv.lock `[manifest] build-constraints` (`[{name, specifier}]`) with the root list."""
    entries = lock_recorded
    if isinstance(lock_recorded, list):
        entries = [
            f"{e['name']}{e['specifier']}"
            if isinstance(e, dict) and isinstance(e.get("name"), str) and isinstance(e.get("specifier"), str)
            else e
            for e in lock_recorded
        ]
    pins, problems = _parse_exact_pins(entries, "uv.lock [manifest] build-constraints")
    differences = problems + _compare(root_pins, pins, reference_name="pyproject.toml")
    return [f"{_LOCK_STALE} ({'; '.join(differences)})"] if differences else []


def _build_constraint_drift(
    locked: _Pins, constraints_text: str, root_entries: object | None, lock_recorded: object | None = None
) -> list[str]:
    """Problems where build-constraints.txt, the root build-constraint-dependencies list or uv.lock's record of it
    disagree with the hatchling closure locked in uv.lock (the reference); each names the stale source and its fix."""
    versions = {name: version for name, (version, _) in locked.items()}
    problems = _file_drift(locked, constraints_text)
    root_pins, root_problems = _root_drift(versions, root_entries)
    problems += root_problems
    if lock_recorded is not None and root_pins is not None:
        problems += _lock_record_drift(root_pins, lock_recorded)
    if problems:
        problems.append(f"To bump hatchling on purpose: {_BUMP_HINT}, then update both derived sources as above.")
    return problems


@dataclass(frozen=True)
class _DriftCase:
    locked: _Pins
    constraints_text: str
    root_entries: object | None
    lock_recorded: object | None
    expected: tuple[str, ...]  # substrings the joined problems must contain; () means "no problems"
    absent: tuple[str, ...] = ()  # substrings that must not appear (sources that are not stale)


_DRIFT_CASES = {
    "all-agree": _DriftCase(_LOCKED, _FILE, _ROOT, _RECORDED, ()),
    "all-agree-root-order-and-case-irrelevant": _DriftCase(
        _LOCKED, _FILE, ["Packaging==26.3", "hatchling==1.32.4"], None, ()
    ),
    "root-bumped-only": _DriftCase(
        _LOCKED,
        _FILE,
        ["hatchling==1.33.0", "packaging==26.3"],
        None,
        (
            _ROOT_STALE,
            "hatchling: 1.33.0, uv.lock has 1.32.4",
            _ROOT_REMEDY,
            "hatchling==1.32.4",
            "packaging==26.3",
            "then run: uv lock",
            _BUMP_HINT,
        ),
        (_FILE_STALE, _LOCK_STALE),
    ),
    "file-bumped-only": _DriftCase(
        _LOCKED,
        _FILE.replace("hatchling==1.32.4", "hatchling==1.33.0"),
        _ROOT,
        _RECORDED,
        (_FILE_STALE, "hatchling: 1.33.0, uv.lock has 1.32.4", _REGENERATE_CONSTRAINTS, _BUMP_HINT),
        (_ROOT_STALE, _ROOT_ABSENT, _LOCK_STALE),
    ),
    "lock-bumped-only": _DriftCase(
        _LOCKED_BUMPED,
        _FILE,
        _ROOT,
        None,
        (
            _FILE_STALE,
            _REGENERATE_CONSTRAINTS,
            _ROOT_STALE,
            "hatchling: 1.32.4, uv.lock has 1.33.0",
            _ROOT_REMEDY,
            "hatchling==1.33.0",
            "then run: uv lock",
            _BUMP_HINT,
        ),
        (_LOCK_STALE,),
    ),
    "root-missing-package": _DriftCase(
        _LOCKED,
        _FILE,
        ["hatchling==1.32.4"],
        None,
        (_ROOT_STALE, "missing packaging==26.3", _BUMP_HINT),
        (_FILE_STALE,),
    ),
    "root-extra-package": _DriftCase(
        _LOCKED,
        _FILE,
        [*_ROOT, "setuptools==80.0"],
        None,
        (_ROOT_STALE, "extra setuptools==80.0", _BUMP_HINT),
        (_FILE_STALE,),
    ),
    "file-missing-package": _DriftCase(
        _LOCKED,
        f"hatchling==1.32.4 \\\n    --hash={_HATCHLING_HASH}\n",
        _ROOT,
        None,
        (_FILE_STALE, "missing packaging==26.3", _REGENERATE_CONSTRAINTS, _BUMP_HINT),
        (_ROOT_STALE,),
    ),
    "file-extra-package": _DriftCase(
        _LOCKED,
        _FILE + f"setuptools==80.0 \\\n    --hash=sha256:{'d' * 64}\n",
        _ROOT,
        None,
        (_FILE_STALE, "extra setuptools==80.0", _REGENERATE_CONSTRAINTS, _BUMP_HINT),
        (_ROOT_STALE,),
    ),
    "root-range": _DriftCase(
        _LOCKED,
        _FILE,
        ["hatchling>=1.25", "packaging==26.3"],
        None,
        (_ROOT_STALE, "hatchling>=1.25", _NOT_EXACT, _ROOT_REMEDY, _BUMP_HINT),
        (_FILE_STALE,),
    ),
    "root-compatible-release": _DriftCase(
        _LOCKED, _FILE, ["hatchling~=1.32", "packaging==26.3"], None, (_ROOT_STALE, "hatchling~=1.32", _NOT_EXACT)
    ),
    "root-wildcard": _DriftCase(
        _LOCKED, _FILE, ["hatchling==1.32.*", "packaging==26.3"], None, (_ROOT_STALE, "hatchling==1.32.*", _NOT_EXACT)
    ),
    "root-arbitrary-equality": _DriftCase(
        _LOCKED, _FILE, ["hatchling===1.32.4", "packaging==26.3"], None, (_ROOT_STALE, "hatchling===1.32.4", _NOT_EXACT)
    ),
    "root-marker": _DriftCase(
        _LOCKED,
        _FILE,
        ["hatchling==1.32.4; python_version >= '3.12'", "packaging==26.3"],
        None,
        (_ROOT_STALE, "hatchling==1.32.4; python_version >= '3.12'", _NOT_EXACT),
    ),
    "root-extra": _DriftCase(
        _LOCKED,
        _FILE,
        ["hatchling[cli]==1.32.4", "packaging==26.3"],
        None,
        (_ROOT_STALE, "hatchling[cli]==1.32.4", _NOT_EXACT),
    ),
    "root-second-specifier": _DriftCase(
        _LOCKED,
        _FILE,
        ["hatchling==1.32.4,<2", "packaging==26.3"],
        None,
        (_ROOT_STALE, "hatchling==1.32.4,<2", _NOT_EXACT),
    ),
    "root-problems-all-reported": _DriftCase(
        _LOCKED,
        _FILE,
        ["hatchling>=1.25"],
        None,
        (_ROOT_STALE, "hatchling>=1.25", _NOT_EXACT, "missing packaging==26.3", _BUMP_HINT),
    ),
    "file-range": _DriftCase(
        _LOCKED,
        _FILE.replace("hatchling==1.32.4", "hatchling>=1.25"),
        _ROOT,
        None,
        (_FILE_STALE, "hatchling>=1.25", _NOT_EXACT, _REGENERATE_CONSTRAINTS, _BUMP_HINT),
        (_ROOT_STALE,),
    ),
    "file-marker-ignored": _DriftCase(
        _LOCKED,
        _FILE.replace("hatchling==1.32.4", "hatchling==1.32.4 ; python_full_version >= '3.12'"),
        _ROOT,
        None,
        (),
    ),
    "root-duplicate": _DriftCase(
        _LOCKED,
        _FILE,
        [*_ROOT, "Hatchling==1.32.4"],
        None,
        (_ROOT_STALE, "duplicate", "hatchling", _ROOT_REMEDY, _BUMP_HINT),
        (_FILE_STALE,),
    ),
    "root-key-absent": _DriftCase(
        _LOCKED,
        _FILE,
        None,
        None,
        (_ROOT_ABSENT, _ROOT_REMEDY, "hatchling==1.32.4", "packaging==26.3", "then run: uv lock", _BUMP_HINT),
        (_FILE_STALE,),
    ),
    "root-not-a-list": _DriftCase(
        _LOCKED,
        _FILE,
        "hatchling==1.32.4",
        None,
        ("root pyproject.toml", "build-constraint-dependencies", _ROOT_REMEDY, "then run: uv lock", _BUMP_HINT),
        (_FILE_STALE,),
    ),
    "root-entry-not-a-string": _DriftCase(
        _LOCKED,
        _FILE,
        [*_ROOT, 42],
        None,
        ("root pyproject.toml", "build-constraint-dependencies", _ROOT_REMEDY, _BUMP_HINT),
        (_FILE_STALE,),
    ),
    "file-hash-differs": _DriftCase(
        _LOCKED,
        _FILE.replace(_HATCHLING_HASH, _HATCHLING_HASH_NEW),
        _ROOT,
        None,
        (_FILE_STALE, "hatchling", _REGENERATE_CONSTRAINTS, _BUMP_HINT),
        (_ROOT_STALE,),
    ),
    "lock-record-missing-package": _DriftCase(
        _LOCKED, _FILE, _ROOT, _RECORDED[:1], (_LOCK_STALE, "packaging", _BUMP_HINT), (_FILE_STALE, _ROOT_STALE)
    ),
    "lock-record-extra-package": _DriftCase(
        _LOCKED,
        _FILE,
        _ROOT,
        [*_RECORDED, {"name": "setuptools", "specifier": "==80.0"}],
        (_LOCK_STALE, "setuptools", _BUMP_HINT),
        (_FILE_STALE, _ROOT_STALE),
    ),
    "lock-record-specifier-differs": _DriftCase(
        _LOCKED,
        _FILE,
        _ROOT,
        [{"name": "hatchling", "specifier": "==1.32.3"}, _RECORDED[1]],
        (_LOCK_STALE, "1.32.3", "1.32.4", _BUMP_HINT),
        (_FILE_STALE, _ROOT_STALE),
    ),
    "lock-record-empty": _DriftCase(
        _LOCKED, _FILE, _ROOT, [], (_LOCK_STALE, "hatchling", "packaging", _BUMP_HINT), (_FILE_STALE, _ROOT_STALE)
    ),
}


@pytest.mark.ac("IDP-25:AC-3")
@pytest.mark.parametrize("case", list(_DRIFT_CASES.values()), ids=list(_DRIFT_CASES))
def test_build_constraint_drift_names_stale_source_and_remedy(case: _DriftCase) -> None:
    drift = _build_constraint_drift
    problems = drift(case.locked, case.constraints_text, case.root_entries, case.lock_recorded)
    assert isinstance(problems, list)
    if not case.expected:
        assert problems == []
        return
    report = "\n".join(problems)
    assert [s for s in case.expected if s not in report] == [], report
    assert [s for s in case.absent if s in report] == [], report


@pytest.mark.ac("IDP-25:AC-1")
def test_root_build_constraint_dependencies_pin_build_constraints_file() -> None:
    root_entries = _root_build_constraints(_ROOT_PYPROJECT.read_text())
    assert isinstance(root_entries, list), (
        "root pyproject.toml has no [tool.uv] build-constraint-dependencies list (IDP-25 AC-1, human edit H1)"
    )
    pins, problems = _parse_exact_pins(root_entries, "root pyproject.toml")
    assert problems == []
    assert len(root_entries) == len(pins), f"duplicate entries in build-constraint-dependencies: {root_entries}"
    assert "hatchling" in pins
    assert pins == {name: version for name, (version, _) in _constraints().items()}


@pytest.mark.ac("IDP-25:AC-1")
@pytest.mark.ac("IDP-25:AC-3")
def test_build_constraint_sources_agree() -> None:
    root_entries = _root_build_constraints(_ROOT_PYPROJECT.read_text())
    lock_recorded = tomllib.loads(UV_LOCK.read_text()).get("manifest", {}).get("build-constraints")
    drift = _build_constraint_drift
    problems = drift(_locked_closure(), BUILD_CONSTRAINTS.read_text(), root_entries, lock_recorded)
    assert problems == [], "\n".join(problems)


@pytest.mark.ac("IDP-25:AC-2")
def test_installed_idp_gate_was_built_by_locked_hatchling() -> None:
    dist = importlib.metadata.distribution("idp-gate")
    direct_url = dist.read_text("direct_url.json")
    setup_hint = "the installed idp-gate is not the editable workspace install; run: make setup"
    assert direct_url is not None, setup_hint
    origin = json.loads(direct_url)
    assert origin.get("dir_info") == {"editable": True}, setup_hint
    url = urlparse(str(origin.get("url", "")))
    assert url.scheme == "file", setup_hint
    assert Path(url2pathname(url.path)).resolve() == PACKAGE_DIR.resolve(), setup_hint
    wheel = dist.read_text("WHEEL")
    assert wheel is not None, setup_hint
    generators = [line for line in wheel.splitlines() if line.startswith("Generator:")]
    assert generators == [f"Generator: hatchling {_locked_closure()['hatchling'][0]}"]


@pytest.mark.ac("IDP-25:AC-4")
def test_adr_0012_known_gaps_state_sync_build_limit() -> None:
    lines = _ADR_0012.read_text().splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("### Known gaps")]
    assert len(starts) == 1, f"ADR-0012 must have exactly one '### Known gaps' heading, found {len(starts)}"
    section: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("#"):
            break
        section.append(line)
    known_gaps = " ".join(" ".join(section).split())  # join wrapped lines so phrases match across line breaks
    assert "still build idp-gate with an unconstrained" not in known_gaps
    assert "build-constraint-dependencies" in known_gaps
    assert "pin versions but not hashes" in known_gaps


# --- AC-5: exit 2 with the profile name and the reason ------------------------------------------------------------


@pytest.mark.ac("IDP-18:AC-5")
@pytest.mark.parametrize("flags", [[], ["--json"]], ids=["yaml", "json"])
def test_profile_show_unknown_name_exits_2_with_name_and_reason(
    flags: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["profile", "show", "nope", *flags]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "profile show: 'nope' not found (available: python-uv)\n"


@pytest.mark.ac("IDP-18:AC-5")
@pytest.mark.parametrize("flags", [[], ["--json"]], ids=["yaml", "json"])
def test_profile_show_schema_violation_exits_2_with_name_and_reason(
    flags: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path.resolve() / "packaged"
    _write_profile(root, "broken", DEMO_YAML.replace("name: demo", "name: broken").replace("cobertura", "xml"))
    _write_profile(root, "renamed", DEMO_YAML)
    _use_roots(monkeypatch, root, tmp_path.resolve() / "missing")
    assert _run(["profile", "show", "broken", *flags]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "profile show: 'broken' is invalid (build-profile.v1): "
        "coverage.format: 'xml' is not one of ['cobertura', 'lcov', 'jacoco']\n"
    )
    assert _run(["profile", "show", "renamed", *flags]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "profile show: 'renamed' is invalid (build-profile.v1): name: name 'demo' does not match directory 'renamed'\n"
    )


@pytest.mark.ac("IDP-18:AC-5")
def test_profile_show_invalid_yaml_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path.resolve() / "packaged"
    _write_profile(root, "bad-yaml", "name: [unclosed\n")
    _use_roots(monkeypatch, root, tmp_path.resolve() / "missing")
    assert _run(["profile", "show", "bad-yaml", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("profile show: 'bad-yaml' is invalid (build-profile.v1): <root>: invalid YAML: ")


@pytest.mark.ac("IDP-18:AC-5")
def test_profile_show_unreadable_profile_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path.resolve() / "packaged"
    (_write_profile(root, "latin", "") / "profile.yaml").write_bytes(b"name: caf\xe9\n")
    _write_profile(root, "locked", DEMO_YAML.replace("name: demo", "name: locked"))
    _use_roots(monkeypatch, root, tmp_path.resolve() / "missing")
    assert _run(["profile", "show", "latin"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("profile show: cannot read 'latin': 'utf-8' codec can't decode byte 0xe9")
    assert captured.err.count("\n") == 1

    def refuse(path: Path) -> Any:
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(contract, "_load_yaml", refuse)
    assert _run(["profile", "show", "locked", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"profile show: cannot read 'locked': [Errno 13] Permission denied: '{root / 'locked' / 'profile.yaml'}'\n"
    )


@pytest.mark.ac("IDP-18:AC-5")
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("../x", "profile show: invalid profile name '../x'\n"),
        ("a/b", "profile show: invalid profile name 'a/b'\n"),
        ("Python-UV", "profile show: invalid profile name 'Python-UV'\n"),
        ("-x", "profile show: invalid profile name '-x'\n"),
    ],
    ids=["dotdot", "slash", "uppercase", "leading-dash"],
)
def test_profile_show_refuses_path_like_names(
    name: str, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Both roots are missing: a name checked after discovery would report "no build profiles found" instead.
    _use_roots(monkeypatch, tmp_path.resolve() / "no-packaged", tmp_path.resolve() / "no-checkout")
    assert _run(["profile", "show", "--", name] if name.startswith("-") else ["profile", "show", name]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == expected


@pytest.mark.ac("IDP-18:AC-5")
def test_profile_show_without_profiles_root_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    packaged, checkout = tmp_path.resolve() / "no-packaged", tmp_path.resolve() / "no-checkout"
    _use_roots(monkeypatch, packaged, checkout)
    assert _run(["profile", "show", "python-uv"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("profile show: no build profiles found (looked in: ")
    assert captured.err.count("\n") == 1
    assert str(packaged) in captured.err
    assert str(checkout) in captured.err


# --- AC-6: agent notes ---------------------------------------------------------------------------------------------


@pytest.mark.ac("IDP-18:AC-6")
def test_python_uv_agent_notes_document_idioms_tagging_and_fixtures() -> None:
    _require(AGENT_NOTES)
    text = AGENT_NOTES.read_text(encoding="utf-8")
    headings = [line.strip().lower() for line in text.splitlines() if line.startswith("## ")]
    assert headings[:3] == ["## pytest idioms", "## ac tagging", "## fixture conventions"]
    assert "ac:<KEY>:AC-n" in text
    assert '@pytest.mark.ac("<KEY>:AC-n")' in text
    assert "idp spec-trace" in text
    assert "tmp_path" in text
    assert "monkeypatch" in text


@pytest.mark.ac("IDP-18:AC-6")
def test_unit_test_generator_references_agent_notes() -> None:
    text = GENERATOR_AGENT.read_text(encoding="utf-8")
    assert text.startswith(GENERATOR_FRONTMATTER)  # frontmatter unchanged
    body = text[len(GENERATOR_FRONTMATTER) :]
    assert "build-profiles/python-uv/agent-notes.md" in body
    assert "idp profile show" in body
