"""IDP-18: python-uv build profile, build-profile.v1 schema, discovery and `idp profile show`."""

import importlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any

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
PACKAGE_PYPROJECT = REPO / "packages" / "idp-gate" / "pyproject.toml"
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
    }
)


def _make(directory: Path, *args: str, stub: bool = True) -> subprocess.CompletedProcess[str]:
    """Run make in `directory` with the python-uv profile; tool commands are stubbed unless `stub` is False."""
    if shutil.which("make") is None:
        pytest.skip("make is not installed")
    _require(DEFAULTS_MK)
    env = {k: v for k, v in os.environ.items() if k not in _MAKE_ENV_STRIPPED}
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
        f"{export} && /nonexistent/uv tool run --from pip-audit==2.10.1 pip-audit --disable-pip "
        "--requirement reports/requirements.locked.txt --format json --output reports/sca.json"
    ) in sca.stdout.splitlines()
    sbom_export = (
        "/nonexistent/uv export --quiet --locked --all-packages --no-dev --no-emit-project --no-emit-workspace "
        "--format requirements-txt --output-file reports/requirements.sbom.txt"
    )
    sbom = _make(tmp_path, "-n", "sbom", "UV=/nonexistent/uv", stub=False)
    assert (sbom.returncode, sbom.stderr) == (0, "")
    assert (
        f"{sbom_export} && /nonexistent/uv tool run --from cyclonedx-bom==7.5.0 cyclonedx-py requirements "
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
    assert "uv tool run --from pip-audit==9.9.9 pip-audit " in sca.stdout
    assert "pip-audit==2.10.1" not in sca.stdout
    sbom = _make(tmp_path, "-n", "sbom", "IDP_CYCLONEDX_SPEC=cyclonedx-bom==9.9.9", stub=False)
    assert (sbom.returncode, sbom.stderr) == (0, "")
    assert "uv tool run --from cyclonedx-bom==9.9.9 cyclonedx-py requirements " in sbom.stdout
    assert "cyclonedx-bom==7.5.0" not in sbom.stdout


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
def test_wheel_config_force_includes_build_profiles() -> None:
    config = tomllib.loads(PACKAGE_PYPROJECT.read_text(encoding="utf-8"))
    wheel = config.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {})
    assert wheel.get("force-include") == {"../../build-profiles": "idp_gate/build_profiles"}
    assert config["project"]["dependencies"] == ["pyyaml>=6.0", "jsonschema>=4.23"]


@pytest.mark.ac("IDP-18:AC-4")
def test_built_wheel_contains_build_profiles(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv is not installed")
    result = subprocess.run(
        ["uv", "build", "--wheel", "--offline", "--out-dir", str(tmp_path), "packages/idp-gate"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    [wheel] = sorted(tmp_path.glob("idp_gate-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    expected = {
        "idp_gate/build_profiles/python-uv/profile.yaml",
        "idp_gate/build_profiles/python-uv/defaults.mk",
        "idp_gate/build_profiles/python-uv/agent-notes.md",
        "idp_gate/schemas/build-profile.v1.json",
    }
    assert sorted(expected - names) == []


@pytest.mark.ac("IDP-18:AC-4")
def test_installed_wheel_resolves_packaged_python_uv(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv is not installed")
    dist = tmp_path / "dist"
    build = subprocess.run(
        ["uv", "build", "--wheel", "--offline", "--out-dir", str(dist), "packages/idp-gate"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    [wheel] = sorted(dist.glob("idp_gate-*.whl"))
    site = tmp_path.resolve() / "site"
    zipfile.ZipFile(wheel).extractall(site)
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
    assert result.returncode == 0, result.stderr
    assert result.stderr == f"{site / 'idp_gate' / '__init__.py'}\n"  # the wheel copy, not the editable install
    shown = json.loads(result.stdout)
    assert shown["name"] == "python-uv"
    assert shown["dir"] == str(site / "idp_gate" / "build_profiles" / "python-uv")


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
