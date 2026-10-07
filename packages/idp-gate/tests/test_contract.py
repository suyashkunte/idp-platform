import copy
import json
import os
import re
import subprocess
from collections.abc import Sequence
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


ALL_TARGETS = (
    "lint",
    "test",
    "test-component",
    "verify",
    "spec-trace",
    "test-smoke",
    "test-api",
    "test-e2e",
    "test-perf",
)


def _write_makefile(directory: Path, targets: Sequence[str] = ALL_TARGETS) -> Path:
    """Plain Makefile with one rule per target (default: required targets plus all four test kinds)."""
    makefile = directory / "Makefile"
    body = "".join(f"{t}:\n\t@echo {t}\n" for t in targets)
    makefile.write_text(f".PHONY: {' '.join(targets)}\n{body}")
    return makefile


def _write_idp(directory: Path, doc: dict[str, Any] | None = None, name: str = "idp.yaml") -> Path:
    path = directory / name
    path.write_text(yaml.safe_dump(_doc_example() if doc is None else doc))
    return path


def _run(argv: list[str]) -> int:
    """Call the CLI and return its exit code, also for argparse errors (SystemExit)."""
    try:
        return main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)


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
    _write_makefile(tmp_path)
    assert main(["validate", str(good)]) == 0
    assert main(["validate", str(bad)]) == 1
    assert "spec.runtime: 'port' is a required property" in capsys.readouterr().out


def test_invalid_yaml_and_missing_file(tmp_path: Path) -> None:
    broken = tmp_path / "idp.yaml"
    broken.write_text("a: [unclosed\n")
    assert "invalid YAML" in str(contract.validate_file(broken)[0])
    assert main(["validate", str(tmp_path / "nope.yaml")]) == 2


def _tests_flags(**flags: bool) -> dict[str, Any]:
    doc = _doc_example()
    tests = doc["spec"]["tests"]
    for kind in ("smoke", "api", "e2e", "perf"):
        tests.pop(kind, None)
    tests.update(flags)
    return doc


# --- IDP-17: Make contract checks and --json ---------------------------------------------------------------------


@pytest.mark.ac("IDP-17:AC-1")
def test_validate_without_argument_uses_cwd_idp_yaml_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 0
    assert capsys.readouterr().out == "idp.yaml: valid (idp-service.v1.json)\n"


@pytest.mark.ac("IDP-17:AC-1")
def test_explicit_file_checks_makefile_beside_it_not_in_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sub = tmp_path / "svc"
    sub.mkdir()
    _write_idp(sub, name="good.yaml")
    _write_makefile(tmp_path)  # a complete Makefile in the cwd must not satisfy svc/good.yaml
    monkeypatch.chdir(tmp_path)
    assert _run(["validate", "svc/good.yaml"]) == 1
    assert capsys.readouterr().out == "svc/good.yaml: Makefile: Makefile not found\n"


@pytest.mark.ac("IDP-17:AC-1")
@pytest.mark.ac("IDP-17:AC-3")
def test_makefile_targets_parses_rules_includes_and_ignores_non_rules(tmp_path: Path) -> None:
    (tmp_path / "common.mk").write_text("test-smoke:\n\t@echo smoke\ninclude Makefile\n")
    (tmp_path / "more.mk").write_text("from-sinclude: ; @true\n")
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "include common.mk\n"
        "-include missing.mk\n"
        "sinclude more.mk $(EXTRA).mk *.mk gone?.mk\n"
        "X = y\n"
        "Y := z\n"
        "Z ::= w\n"
        "Q :::= v\n"
        "W ?= u\n"
        "V += t\n"
        ".PHONY: lint test ghost\n"
        ".DEFAULT: ghost2\n"
        "lint: ## run linters\n"
        "\truff check .\n"
        "test unit-x::\n"
        "test-component:: lint\n"
        "verify: lint test\n"
        "spec-trace: KEY = IDP-1\n"
        "%.o: %.c\n"
        "$(NAME): foo\n"
        "  indented: nope\n"
        "\ttabbed: nope\n"
        "# commented: nope\n"
    )
    scan = contract.makefile_targets(makefile)
    assert scan.violations == ()
    # `spec-trace: KEY = IDP-1` is a target-specific variable, not a rule
    assert scan.targets == {
        "lint",
        "test",
        "unit-x",
        "test-component",
        "verify",
        "test-smoke",
        "from-sinclude",
    }


@pytest.mark.ac("IDP-17:AC-3")
@pytest.mark.parametrize(
    "line",
    [
        "spec-trace: VAR = x",
        "spec-trace: VAR := x",
        "spec-trace: VAR ::= x",
        "spec-trace: VAR ?= x",
        "spec-trace: VAR += x",
        "spec-trace: VAR != echo x",
        "spec-trace: VAR=x",
        "spec-trace: export VAR = x",
        "spec-trace: override VAR := x",
        "spec-trace: export override VAR += x",
    ],
)
def test_target_specific_variable_lines_do_not_define_targets(tmp_path: Path, line: str) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text(f"{line}\nlint: spec-trace-helper\n")
    assert contract.makefile_targets(makefile).targets == {"lint"}


@pytest.mark.ac("IDP-17:AC-3")
def test_define_bodies_are_skipped_including_nested_ones(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "define RECIPE\n"
        "inside-define:\n"
        "endef\n"
        "override define OUTER\n"
        "define INNER\n"
        "inside-nested:\n"
        "endef\n"
        "still-inside-outer:\n"
        "endef\n"
        "export define EXPORTED =\n"
        "inside-export:\n"
        "endef # done\n"
        "after-define:\n"
    )
    assert contract.makefile_targets(makefile).targets == {"after-define"}


@pytest.mark.ac("IDP-17:AC-3")
def test_escaped_hash_does_not_start_a_comment(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text("lint\\#1 lint: \\# not-a-comment\n# hidden:\nverify: # comment: ghost\n")
    assert contract.makefile_targets(makefile).targets == {"lint#1", "lint", "verify"}


@pytest.mark.ac("IDP-17:AC-3")
def test_variable_named_define_does_not_start_a_define_block(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text("define := 1\nlint:\ndefine += 2\nexport define ?= 3\ndefine = 4\nverify:\n")
    assert contract.makefile_targets(makefile).targets == {"lint", "verify"}


@pytest.mark.ac("IDP-17:AC-3")
def test_rule_colon_edge_cases(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "a::=b\nc:::=d\ne := f\ng:=h\n::i\n=j: k\nl=m: n\ndbl::\nsgl:deps\nsp  :  deps\nlast:\nend::x\n"
    )
    assert contract.makefile_targets(makefile).targets == {"dbl", "sgl", "sp", "last", "end"}


@pytest.mark.ac("IDP-17:AC-3")
def test_long_lines_without_colon_are_parsed_in_linear_time(tmp_path: Path) -> None:
    # A backtracking rule regex is quadratic here (hours for 200k chars); the scan must finish promptly.
    makefile = tmp_path / "Makefile"
    padding = " " * 200_000
    makefile.write_text(f"a{padding}x\nb{padding}x = y\nlint:\nc{padding}d: e\n")
    assert contract.makefile_targets(makefile).targets == {"lint", "c", "d"}


def _make_messages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Run `idp validate --json` in `tmp_path`; assert one JSON object and exit 1; return the Makefile messages."""
    monkeypatch.chdir(tmp_path)
    assert _run(["validate", "--json"]) == 1
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    return [v["message"] for v in json.loads(out)["violations"] if v["path"] == "Makefile"]


@pytest.mark.ac("IDP-17:AC-6")
@pytest.mark.parametrize("word", ["/etc/passwd", "../outside.mk", "sub/../../outside.mk"])
def test_include_outside_service_directory_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], word: str
) -> None:
    svc = tmp_path / "svc"
    svc.mkdir()
    (tmp_path / "outside.mk").write_text("SECRET-TARGET-CONTENT:\n")
    _write_idp(svc)
    _write_makefile(svc)
    with (svc / "Makefile").open("a") as fh:
        fh.write(f"-include {word}\n")
    messages = _make_messages(svc, monkeypatch, capsys)
    assert messages == [f"include {word!r} is outside the service directory"]


@pytest.mark.ac("IDP-17:AC-6")
def test_symlinked_include_outside_service_directory_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    svc = tmp_path / "svc"
    svc.mkdir()
    (tmp_path / "outside.mk").write_text("SECRET-TARGET-CONTENT:\n")
    (svc / "link.mk").symlink_to(tmp_path / "outside.mk")
    _write_idp(svc)
    _write_makefile(svc)
    with (svc / "Makefile").open("a") as fh:
        fh.write("include link.mk\n")
    assert _make_messages(svc, monkeypatch, capsys) == ["include 'link.mk' is outside the service directory"]


@pytest.mark.ac("IDP-17:AC-6")
def test_makefile_symlinked_outside_service_directory_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    svc = tmp_path / "svc"
    svc.mkdir()
    _write_makefile(tmp_path)
    (svc / "Makefile").symlink_to(tmp_path / "Makefile")
    _write_idp(svc)
    assert _make_messages(svc, monkeypatch, capsys) == ["Makefile resolves outside the service directory"]


@pytest.mark.ac("IDP-17:AC-6")
def test_oversized_makefile_or_include_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    (tmp_path / "big.mk").write_text("#" * contract.MAX_MAKEFILE_BYTES + "\n")
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write("include big.mk\n")
    assert _make_messages(tmp_path, monkeypatch, capsys) == ["'big.mk' exceeds 1 MiB"]
    (tmp_path / "Makefile").write_text("#" * (contract.MAX_MAKEFILE_BYTES + 1))
    assert _make_messages(tmp_path, monkeypatch, capsys) == ["'Makefile' exceeds 1 MiB"]
    (tmp_path / "Makefile").write_text("lint:\n" + "#" * (contract.MAX_MAKEFILE_BYTES - 6))  # exactly at the cap
    assert contract.makefile_targets(tmp_path / "Makefile").violations == ()


@pytest.mark.ac("IDP-17:AC-6")
def test_too_many_included_files_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    names = [f"inc{i}.mk" for i in range(contract.MAX_MAKEFILES)]  # Makefile + 64 includes = 65 files
    for name in names:
        (tmp_path / name).write_text("")
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write(f"include {' '.join(names)}\n")
    assert _make_messages(tmp_path, monkeypatch, capsys) == ["too many included files (limit 64)"]
    (tmp_path / names[-1]).unlink()  # exactly 64 files is fine
    assert contract.makefile_targets(tmp_path / "Makefile").violations == ()


@pytest.mark.ac("IDP-17:AC-6")
def test_unreadable_files_are_violations_not_tracebacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    (tmp_path / "latin1.mk").write_bytes(b"caf\xe9:\n")
    (tmp_path / "loop.mk").symlink_to(tmp_path / "loop.mk")
    (tmp_path / "adir.mk").mkdir()
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write("include latin1.mk\ninclude loop.mk\ninclude adir.mk\n")
    assert _make_messages(tmp_path, monkeypatch, capsys) == [  # scan (line) order
        "cannot read 'latin1.mk'",
        "cannot read 'loop.mk'",
        "cannot read 'adir.mk'",
    ]
    (tmp_path / "Makefile").write_bytes(b"lint:\n\xff\n")
    assert _make_messages(tmp_path, monkeypatch, capsys) == ["cannot read 'Makefile'"]


@pytest.mark.ac("IDP-17:AC-6")
@pytest.mark.ac("IDP-17:AC-4")
def test_nul_byte_in_include_word_is_a_violation_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write("include a\x00b.mk\n")
    assert _make_messages(tmp_path, monkeypatch, capsys) == ["cannot read 'a\\x00b.mk'"]


@pytest.mark.ac("IDP-17:AC-6")
def test_repeated_include_words_are_reported_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write("include" + " /x" * 5000 + "\n" + "include" + " /x" * 5000 + "\n")
    assert _make_messages(tmp_path, monkeypatch, capsys) == ["include '/x' is outside the service directory"]


@pytest.mark.ac("IDP-17:AC-6")
def test_include_problems_are_capped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    limit = contract.MAX_INCLUDE_PROBLEMS
    words = [f"/x{i}" for i in range(500)]  # below MAX_INCLUDE_WORDS, far above the problem cap
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write(f"include {' '.join(words)}\n")
    expected = [f"include {w!r} is outside the service directory" for w in words[:limit]]
    assert _make_messages(tmp_path, monkeypatch, capsys) == [*expected, f"too many include problems (limit {limit})"]
    _write_makefile(tmp_path)
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write(f"include {' '.join(words[:limit])}\n")  # exactly at the cap: no extra message
    assert _make_messages(tmp_path, monkeypatch, capsys) == expected


@pytest.mark.ac("IDP-17:AC-6")
def test_too_many_include_words_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    words = [f"missing{i}.mk" for i in range(contract.MAX_INCLUDE_WORDS + 1)]  # not on disk: otherwise skipped
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write(f"-include {' '.join(words)}\n")
    assert _make_messages(tmp_path, monkeypatch, capsys) == ["too many include words (limit 1024)"]
    _write_makefile(tmp_path)
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write(f"-include {' '.join(words[:-1])} ./missing0.mk\n")  # 1024 distinct words (./ normalised) is fine
    assert contract.makefile_targets(tmp_path / "Makefile").violations == ()


@pytest.mark.ac("IDP-17:AC-6")
def test_long_include_word_is_truncated_in_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    word = "/" + "a" * 5000
    with (tmp_path / "Makefile").open("a") as fh:
        fh.write(f"include {word}\n")
    shown = repr(word)[: contract.MAX_SHOWN_WORD] + "…"
    assert _make_messages(tmp_path, monkeypatch, capsys) == [f"include {shown} is outside the service directory"]


@pytest.mark.ac("IDP-17:AC-2")
def test_enabled_test_kind_without_target_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path, _tests_flags(smoke=True, api=True, e2e=True, perf=True))
    _write_makefile(tmp_path, ("lint", "test", "test-component", "verify", "spec-trace", "test-api"))
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == (
        "idp.yaml: Makefile: missing target 'test-smoke' (required because spec.tests.smoke is true)\n"
        "idp.yaml: Makefile: missing target 'test-e2e' (required because spec.tests.e2e is true)\n"
        "idp.yaml: Makefile: missing target 'test-perf' (required because spec.tests.perf is true)\n"
    )


@pytest.mark.ac("IDP-17:AC-2")
def test_disabled_test_kind_does_not_require_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # smoke enabled, api/perf explicitly false, e2e absent: only test-smoke is required
    _write_idp(tmp_path, _tests_flags(smoke=True, api=False, perf=False))
    _write_makefile(tmp_path, ("lint", "test", "test-component", "verify", "spec-trace"))
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == (
        "idp.yaml: Makefile: missing target 'test-smoke' (required because spec.tests.smoke is true)\n"
    )
    _write_makefile(tmp_path, ("lint", "test", "test-component", "verify", "spec-trace", "test-smoke"))
    assert _run(["validate"]) == 0
    assert capsys.readouterr().out == "idp.yaml: valid (idp-service.v1.json)\n"


@pytest.mark.ac("IDP-17:AC-2")
@pytest.mark.parametrize("tests_value", [{"smoke": "true"}, ["smoke", "api"]])
def test_non_boolean_or_non_mapping_tests_only_give_schema_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tests_value: Any
) -> None:
    doc = _doc_example()
    doc["spec"]["tests"] = tests_value
    _write_idp(tmp_path, doc)
    _write_makefile(tmp_path, ("lint", "test", "test-component", "verify", "spec-trace"))
    monkeypatch.chdir(tmp_path)
    assert _run(["validate", "--json"]) == 1
    violations = json.loads(capsys.readouterr().out)["violations"]
    assert violations
    assert all(v["path"].startswith("spec.tests") for v in violations)
    assert not any("test-smoke" in v["message"] or "test-api" in v["message"] for v in violations)


@pytest.mark.ac("IDP-17:AC-3")
def test_every_missing_required_target_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path, ("verify", "format", "verify-fast"))
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == (
        "idp.yaml: Makefile: missing required target 'lint'\n"
        "idp.yaml: Makefile: missing required target 'test'\n"
        "idp.yaml: Makefile: missing required target 'test-component'\n"
        "idp.yaml: Makefile: missing required target 'spec-trace'\n"
        "idp.yaml: Makefile: missing target 'test-smoke' (required because spec.tests.smoke is true)\n"
        "idp.yaml: Makefile: missing target 'test-api' (required because spec.tests.api is true)\n"
        "idp.yaml: Makefile: missing target 'test-e2e' (required because spec.tests.e2e is true)\n"
        "idp.yaml: Makefile: missing target 'test-perf' (required because spec.tests.perf is true)\n"
    )


@pytest.mark.ac("IDP-17:AC-3")
def test_phony_only_and_pattern_rules_do_not_define_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path, _tests_flags())
    (tmp_path / "Makefile").write_text(
        ".PHONY: lint test test-component verify spec-trace\n"
        "test%:\n\t@echo pattern\n"
        "verify := yes\n"
        "spec-trace = no\n"
        "\tlint: recipe-line\n"
        "# test-component: commented out\n"
    )
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == (
        "idp.yaml: Makefile: missing required target 'lint'\n"
        "idp.yaml: Makefile: missing required target 'test'\n"
        "idp.yaml: Makefile: missing required target 'test-component'\n"
        "idp.yaml: Makefile: missing required target 'verify'\n"
        "idp.yaml: Makefile: missing required target 'spec-trace'\n"
    )


@pytest.mark.ac("IDP-17:AC-3")
def test_make_checks_run_with_schema_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = _doc_example()
    del broken["spec"]["runtime"]["port"]
    _write_idp(tmp_path, broken)
    _write_makefile(tmp_path, tuple(t for t in ALL_TARGETS if t != "test-component"))
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == (
        "idp.yaml: spec.runtime: 'port' is a required property\n"
        "idp.yaml: Makefile: missing required target 'test-component'\n"
    )


@pytest.mark.ac("IDP-17:AC-3")
def test_target_detection_never_runs_make(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a subprocess was started")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(os, "system", _forbidden)
    _write_idp(tmp_path)
    makefile = _write_makefile(tmp_path, tuple(t for t in ALL_TARGETS if t != "lint"))
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == "idp.yaml: Makefile: missing required target 'lint'\n"
    assert "lint" not in contract.makefile_targets(makefile).targets
    assert "verify" in contract.makefile_targets(makefile).targets


@pytest.mark.ac("IDP-17:AC-4")
def test_json_valid_output_and_exit_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(["validate", "--json"]) == 0
    out = capsys.readouterr().out
    assert out == '{"file": "idp.yaml", "valid": true, "schema": "idp-service.v1", "violations": []}\n'
    payload = json.loads(out)
    assert list(payload) == ["file", "valid", "schema", "violations"]
    assert payload == {"file": "idp.yaml", "valid": True, "schema": "idp-service.v1", "violations": []}


@pytest.mark.ac("IDP-17:AC-4")
def test_json_invalid_output_lists_violations_and_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = _doc_example()
    del broken["spec"]["runtime"]["port"]
    _write_idp(tmp_path, broken)
    _write_makefile(tmp_path, tuple(t for t in ALL_TARGETS if t != "test-component"))
    monkeypatch.chdir(tmp_path)
    assert _run(["validate", "--json"]) == 1
    first = capsys.readouterr().out
    assert first.count("\n") == 1
    assert first.endswith("}\n")
    payload = json.loads(first)
    assert list(payload) == ["file", "valid", "schema", "violations"]
    assert [list(v) for v in payload["violations"]] == [["path", "message"], ["path", "message"]]
    assert payload == {
        "file": "idp.yaml",
        "valid": False,
        "schema": "idp-service.v1",
        "violations": [
            {"path": "spec.runtime", "message": "'port' is a required property"},
            {"path": "Makefile", "message": "missing required target 'test-component'"},
        ],
    }
    assert _run(["validate", "--json"]) == 1
    assert capsys.readouterr().out == first  # deterministic, byte-identical


@pytest.mark.ac("IDP-17:AC-4")
@pytest.mark.ac("IDP-17:AC-5")
def test_json_missing_file_exits_2_with_empty_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_makefile(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(["validate", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "validate: idp.yaml not found\n"
    assert _run(["validate", "--json", "--no-such-flag"]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.ac("IDP-17:AC-5")
def test_no_idp_yaml_in_cwd_exits_2_with_not_found_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_makefile(tmp_path)
    (tmp_path / "service.yaml").write_text(yaml.safe_dump(_doc_example()))  # wrong name: not discovered
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "idp.yaml not found" in captured.err


@pytest.mark.ac("IDP-17:AC-6")
def test_missing_makefile_is_single_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == "idp.yaml: Makefile: Makefile not found\n"
    assert _run(["validate", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["violations"] == [{"path": "Makefile", "message": "Makefile not found"}]


@pytest.mark.ac("IDP-17:AC-6")
def test_gnumakefile_is_not_recognised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    (tmp_path / "GNUmakefile").write_text("".join(f"{t}:\n" for t in ALL_TARGETS))
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == "idp.yaml: Makefile: Makefile not found\n"


@pytest.mark.ac("IDP-17:AC-6")
def test_missing_makefile_reported_alongside_schema_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = _doc_example()
    del broken["spec"]["runtime"]["port"]
    _write_idp(tmp_path, broken)
    monkeypatch.chdir(tmp_path)
    assert _run(["validate"]) == 1
    assert capsys.readouterr().out == (
        "idp.yaml: spec.runtime: 'port' is a required property\nidp.yaml: Makefile: Makefile not found\n"
    )
    (tmp_path / "idp.yaml").write_text("a: [unclosed\n")  # unparseable YAML: Make checks are skipped
    assert _run(["validate"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("idp.yaml: <root>: invalid YAML: ")
    assert "Makefile" not in out
