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
    # IDP-28 amendment 1: accepted define forms only; the nested `define INNER` case moved to the AC-10 test and the
    # `export define EXPORTED =` case to the AC-12 test (both are violations now).
    makefile.write_text(
        "define RECIPE\ninside-define:\nendef\noverride define OUTER\ninside-override:\nendef # done\nafter-define:\n"
    )
    scan = contract.makefile_targets(makefile)
    assert scan.targets == {"after-define"}
    assert scan.violations == ()


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
    # IDP-28 NFR (amendment 1): 100 000 `override ` words before `x` must not make the define-line match quadratic.
    # Its own file: together with the lines above it would exceed the 1 MiB cap.
    makefile.write_text("override " * 100_000 + "x\nlint:\n")
    assert contract.makefile_targets(makefile).targets == {"lint"}


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
    # IDP-28 AC-11: a NUL anywhere in a scanned file is a character violation (was `cannot read 'a\x00b.mk'`).
    assert _make_messages(tmp_path, monkeypatch, capsys) == [
        "'Makefile' contains a control or space character make reads differently (U+0000);"
        " use only spaces, tabs and LF or CRLF line endings"
    ]


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
        # 1024 distinct spellings is fine; a repeated spelling is not counted again (IDP-22 AC-5 caps spellings)
        fh.write(f"-include {' '.join(words[:-1])} missing0.mk\n")
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


# --- IDP-22: a GNUmakefile/makefile beside Makefile would be read by GNU make instead ----------------------------

EXTRA_MAKEFILE = "GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it"


def _case_sensitive(directory: Path) -> bool:
    """True if `directory` is on a case-sensitive filesystem (Linux CI), False on case-insensitive APFS (macOS)."""
    probe = directory / "probe"
    probe.write_text("")
    sensitive = not (directory / "PROBE").exists()
    probe.unlink()
    return sensitive


@pytest.mark.ac("IDP-22:AC-1")
@pytest.mark.parametrize("name", ["GNUmakefile", "makefile"], ids=["gnumakefile", "lowercase-makefile"])
def test_extra_gnumakefile_or_makefile_beside_valid_makefile_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    _write_idp(tmp_path)
    makefile = _write_makefile(tmp_path)
    if name == "GNUmakefile" or _case_sensitive(tmp_path):
        (tmp_path / name).write_text(makefile.read_text())
    else:
        # `Makefile` and `makefile` cannot both exist: store the valid file lowercase (it still opens as Makefile).
        makefile.rename(tmp_path / name)
    monkeypatch.chdir(tmp_path)

    code = _run(["validate"])

    assert capsys.readouterr().out == f"idp.yaml: {name}: {EXTRA_MAKEFILE}\n"
    assert code == 1


@pytest.mark.ac("IDP-22:AC-1")
def test_extra_makefile_names_match_case_insensitively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    (tmp_path / "GnuMakefile").mkdir()  # entry type does not matter: a directory is reported too
    for harmless in ("Makefile.bak", "GNUmakefile.orig", "common.mk"):
        (tmp_path / harmless).write_text("verify:\n\t@true\n")
    expected = ["GnuMakefile"]
    if _case_sensitive(tmp_path):  # spellings that would collide with Makefile/GnuMakefile on APFS
        (tmp_path / "gnumakefile").write_text("verify:\n\t@true\n")
        (tmp_path / "MAKEFILE").write_text("verify:\n\t@true\n")
        (tmp_path / "makefile").symlink_to(tmp_path / "missing.mk")  # dangling symlink
        expected = ["GnuMakefile", "MAKEFILE", "gnumakefile", "makefile"]
    monkeypatch.chdir(tmp_path)

    code = _run(["validate", "--json"])

    violations = json.loads(capsys.readouterr().out)["violations"]
    assert violations == [{"path": name, "message": EXTRA_MAKEFILE} for name in expected]
    assert code == 1


@pytest.mark.ac("IDP-22:AC-1")
def test_extra_makefile_names_are_compared_as_listed_on_every_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    makefile = _write_makefile(tmp_path)
    original = os.listdir
    listed = ["common.mk", "Makefile", "MakeFile", "Makefile.bak", "MAKEFILE"]

    def fake_listdir(path: Any = ".") -> list[str]:
        if Path(path).resolve() == tmp_path.resolve():
            return list(listed)
        return original(path)

    monkeypatch.setattr("idp_gate.contract.os.listdir", fake_listdir)

    violations = contract.check_make_contract(_doc_example(), makefile)

    assert violations == [
        contract.Violation("MAKEFILE", EXTRA_MAKEFILE),
        contract.Violation("MakeFile", EXTRA_MAKEFILE),
    ]


@pytest.mark.ac("IDP-22:AC-1")
def test_extra_makefile_check_fails_closed_when_directory_cannot_be_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path)
    original = os.listdir

    def fake_listdir(path: Any = ".") -> list[str]:
        if Path(path).resolve() == tmp_path.resolve():
            raise PermissionError(13, "Permission denied", str(path))
        return original(path)

    monkeypatch.setattr("idp_gate.contract.os.listdir", fake_listdir)
    monkeypatch.chdir(tmp_path)

    code = _run(["validate"])

    assert capsys.readouterr().out == "idp.yaml: Makefile: cannot list the service directory\n"
    assert code == 1


@pytest.mark.ac("IDP-22:AC-1")
def test_extra_makefile_violation_in_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    _write_makefile(tmp_path, tuple(t for t in ALL_TARGETS if t != "test-component"))
    (tmp_path / "GNUmakefile").write_text("include Makefile\n")
    monkeypatch.chdir(tmp_path)

    code = _run(["validate", "--json"])

    assert json.loads(capsys.readouterr().out) == {
        "file": "idp.yaml",
        "valid": False,
        "schema": "idp-service.v1",
        "violations": [
            {"path": "GNUmakefile", "message": EXTRA_MAKEFILE},
            {"path": "Makefile", "message": "missing required target 'test-component'"},
        ],
    }
    assert code == 1


# --- IDP-22 AC-5: the scan records every literal include word as written (conformance pins them) -----------------


@pytest.mark.ac("IDP-22:AC-5")
def test_makefile_scan_records_literal_include_words_as_written(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "include common.mk ./common.mk\n"
        "-include gen.mk\n"  # missing on disk: recorded anyway (a rule could generate it)
        "sinclude sub/x.mk\n"
        "include $(V)/d.mk\n"  # dynamic: not scanned, not recorded
        "include *.mk\n"  # glob: not scanned, not recorded
        "lint:\n\t@true\n"
    )
    (tmp_path / "common.mk").write_text("include gen.mk\nverify:\n\t@true\n")  # gen.mk again: recorded once
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.mk").write_text("test:\n\t@true\n")

    scan = contract.makefile_targets(makefile)

    assert scan.include_words == ("common.mk", "./common.mk", "gen.mk", "sub/x.mk")
    assert scan.targets == {"lint", "verify", "test"}
    assert scan.violations == ()


@pytest.mark.ac("IDP-22:AC-5")
@pytest.mark.parametrize(
    ("count", "violations"),
    [(1024, ()), (1025, (contract.Violation("Makefile", "too many include words (limit 1024)"),))],
    ids=["at-limit", "over-limit"],
)
def test_makefile_scan_caps_recorded_include_spellings(
    tmp_path: Path, count: int, violations: tuple[contract.Violation, ...]
) -> None:
    (tmp_path / "a.mk").write_text("verify:\n\t@true\n")
    # Distinct spellings of the same file: one normalised path, so only the spelling cap can trigger.
    words = ["a.mk", *(f"d{i}/../a.mk" for i in range(count - 1))]
    makefile = tmp_path / "Makefile"
    makefile.write_text(f"include {' '.join(words)}\nlint:\n\t@true\n")

    scan = contract.makefile_targets(makefile)

    assert scan.violations == violations
    assert len(scan.include_words) == 1024


# --- IDP-22 AC-6: an idp.yaml that cannot be read or decoded is a violation, not a traceback ----------------------


@pytest.mark.ac("IDP-22:AC-6")
@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("not-utf8", "cannot read: not valid UTF-8 (invalid continuation byte at byte 9)"),
        ("permission", "cannot read: Permission denied"),
        ("no-strerror", "cannot read: boom"),
    ],
    ids=["undecodable", "unreadable", "oserror-no-strerror"],
)
def test_unreadable_or_undecodable_idp_yaml_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], kind: str, message: str
) -> None:
    _write_makefile(tmp_path)
    if kind == "not-utf8":
        (tmp_path / "idp.yaml").write_bytes(b"name: caf\xe9\n")
    else:
        _write_idp(tmp_path)
        error = PermissionError(13, "Permission denied", "idp.yaml") if kind == "permission" else OSError("boom")

        def failing(path: Path) -> tuple[Any, list[contract.Violation]]:
            raise error

        monkeypatch.setattr(contract, "_load_yaml", failing)
    monkeypatch.chdir(tmp_path)

    code = _run(["validate"])

    assert capsys.readouterr().out == f"idp.yaml: <root>: {message}\n"
    assert code == 1
    assert _run(["validate", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["violations"] == [{"path": "", "message": message}]


@pytest.mark.ac("IDP-22:AC-6")
def test_deeply_nested_idp_yaml_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_makefile(tmp_path)
    (tmp_path / "idp.yaml").write_text("[" * 100000)  # the parser stops at the recursion limit, not at the end
    monkeypatch.chdir(tmp_path)

    code = _run(["validate"])

    assert capsys.readouterr().out == "idp.yaml: <root>: cannot parse: nesting too deep\n"
    assert code == 1
    assert _run(["validate", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["violations"] == [
        {"path": "", "message": "cannot parse: nesting too deep"}
    ]


# --- IDP-22 AC-7: include lines with a backslash (continuation or escape) are violations -------------------------

BACKSLASH_INCLUDE = "uses a backslash (continuation or escape); write each include word literally on one line"


@pytest.mark.ac("IDP-22:AC-7")
@pytest.mark.parametrize(
    ("extra", "common", "out", "code"),
    [
        (
            "-include common.mk \\\n  gen.mk\n",
            "COMMON := 1\n",
            f"idp.yaml: Makefile: include line in 'Makefile' {BACKSLASH_INCLUDE}\n",
            1,
        ),
        (
            "-include gen\\#.mk\n",
            "COMMON := 1\n",
            f"idp.yaml: Makefile: include line in 'Makefile' {BACKSLASH_INCLUDE}\n",
            1,
        ),
        (
            "include common.mk\n",
            "sinclude x\\ y.mk\n",
            f"idp.yaml: Makefile: include line in 'common.mk' {BACKSLASH_INCLUDE}\n",
            1,
        ),
        ("include common.mk # see notes \\\n", "COMMON := 1\n", "idp.yaml: valid (idp-service.v1.json)\n", 0),
    ],
    ids=["continuation", "escape", "in-include", "comment-only"],
)
def test_include_line_with_backslash_is_a_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra: str,
    common: str,
    out: str,
    code: int,
) -> None:
    _write_idp(tmp_path)
    makefile = _write_makefile(tmp_path)
    makefile.write_text(makefile.read_text() + extra)
    (tmp_path / "common.mk").write_text(common)
    monkeypatch.chdir(tmp_path)

    exit_code = _run(["validate"])

    assert capsys.readouterr().out == out
    assert exit_code == code
    # The words of an offending line are not queued, so they are not recorded (nor pinned) either.
    assert "gen\\#.mk" not in contract.makefile_targets(makefile).include_words


# --- IDP-28 AC-1/AC-3: the scanner reads make's logical lines (backslash-newline joined before anything else) ------


def _scan_text(tmp_path: Path, text: str) -> contract.MakefileScan:
    """Scan a Makefile with exactly `text` (bytes as given: no newline translation)."""
    makefile = tmp_path / "Makefile"
    makefile.write_bytes(text.encode("utf-8"))
    return contract.makefile_targets(makefile)


@pytest.mark.ac("IDP-28:AC-1")
@pytest.mark.parametrize(
    ("text", "targets"),
    [
        ("a \\\nverify:\n", {"a", "verify"}),
        ("X = \\\nverify:\n", set()),
        ("lint: \\\\\nverify:\n", {"lint", "verify"}),
        ("X = \\\r\nverify:\r\n", set()),
        ("lint:\n\techo \\\nverify:\n", {"lint"}),
        ("define D\nx \\\nendef\ninside:\nendef\nafter:\n", {"after"}),
        ("verify:\nlint: \\", {"verify", "lint"}),
        ("spec-trace: \\\n  KEY = x\n", set()),
    ],
    ids=[
        "rule-continuation",
        "assignment-continuation",
        "even-backslashes",
        "crlf-continuation",
        "recipe-continuation",
        "continued-endef-in-define",
        "continuation-at-eof",
        "target-specific-variable",
    ],
)
def test_logical_lines_join_odd_trailing_backslashes(tmp_path: Path, text: str, targets: set[str]) -> None:
    scan = _scan_text(tmp_path, text)

    assert scan.targets == targets
    assert scan.violations == ()


@pytest.mark.ac("IDP-28:AC-1")
def test_continuation_into_define_does_not_hide_later_lines(tmp_path: Path) -> None:
    makefile = _write_makefile(tmp_path)
    makefile.write_text(
        makefile.read_text()
        + "X = \\\n"
        + "define Y\n"
        + "-include gen.mk\n"
        + "gen.mk:\n"
        + "\techo 'EVIL := 1' > gen.mk\n"
        + "define Z\n"
        + "endef\n"
        + "late:\n"
    )

    scan = contract.makefile_targets(makefile)

    assert scan.include_words == ("gen.mk",)
    assert {"gen.mk", "late"} <= scan.targets
    assert scan.violations == ()


@pytest.mark.ac("IDP-28:AC-1")
@pytest.mark.ac("IDP-28:AC-6")
@pytest.mark.parametrize(
    ("text", "targets"),
    [
        ("a \\\n" * 200_000 + "lint:\nverify:\n", {"a", "lint", "verify"}),
        # AC-6 NFR: 200 000 `\` + newline + `  x` collapse to one logical line starting with a blank (no rule).
        ("lint:\n" + "\\\n  x" * 200_000 + "\nverify:\n", {"lint", "verify"}),
    ],
    ids=["one-char-lines", "collapsed-continuations"],
)
def test_many_continued_lines_are_joined_in_linear_time(tmp_path: Path, text: str, targets: set[str]) -> None:
    # 200 000 continued lines: quadratic joining or collapsing would take minutes; the scan must finish promptly.
    scan = _scan_text(tmp_path, text)

    assert scan.targets == targets
    assert scan.violations == ()


@pytest.mark.ac("IDP-28:AC-3")
def test_comment_ending_in_backslash_continues_onto_next_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    makefile = _write_makefile(tmp_path, tuple(t for t in ALL_TARGETS if t != "verify"))
    makefile.write_text(makefile.read_text() + "# note \\\nverify:\n\t@true\n")
    monkeypatch.chdir(tmp_path)

    code = _run(["validate"])

    assert capsys.readouterr().out == "idp.yaml: Makefile: missing required target 'verify'\n"
    assert code == 1
    assert _run(["validate", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["violations"] == [
        {"path": "Makefile", "message": "missing required target 'verify'"}
    ]


@pytest.mark.ac("IDP-28:AC-3")
@pytest.mark.parametrize(
    ("text", "targets"),
    [
        ("lint: # note \\\nverify:\n", {"lint"}),
        ("define D\n# note \\\nendef\ninside:\nendef\nafter:\n", {"after"}),
    ],
    ids=["trailing-comment", "comment-in-define-body"],
)
def test_trailing_comment_ending_in_backslash_hides_next_line(tmp_path: Path, text: str, targets: set[str]) -> None:
    scan = _scan_text(tmp_path, text)

    assert scan.targets == targets
    assert scan.violations == ()


# --- IDP-28 AC-2: line separators make does not use are violations; CRLF is accepted ------------------------------

FOREIGN_SEPARATOR = "contains a line separator make does not use"


@pytest.mark.ac("IDP-28:AC-2")
@pytest.mark.parametrize(
    ("separator", "what"),
    [
        ("\rx", "CR not followed by LF"),
        ("\r\r\n", "CR not followed by LF"),
        ("\x0b", "U+000B"),
        ("\x0c", "U+000C"),
        ("\x1c", "U+001C"),
        ("\x1d", "U+001D"),
        ("\x1e", "U+001E"),
        ("\x85", "U+0085"),
        ("\u2028", "U+2028"),
        ("\u2029", "U+2029"),
    ],
    ids=["lone-cr", "cr-cr-lf", "vt", "ff", "fs", "gs", "rs", "nel", "line-separator", "paragraph-separator"],
)
def test_line_separator_make_does_not_use_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], separator: str, what: str
) -> None:
    _write_idp(tmp_path)
    makefile = _write_makefile(tmp_path)
    makefile.write_bytes((makefile.read_text() + f"extra:{separator}tail\n").encode("utf-8"))
    monkeypatch.chdir(tmp_path)

    code = _run(["validate"])

    assert capsys.readouterr().out == (
        f"idp.yaml: Makefile: 'Makefile' {FOREIGN_SEPARATOR} ({what}); use LF or CRLF line endings\n"
    )
    assert code == 1


@pytest.mark.ac("IDP-28:AC-2")
def test_line_separator_in_included_file_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_idp(tmp_path)
    makefile = _write_makefile(tmp_path)
    makefile.write_text(makefile.read_text() + "include bad.mk other.mk\n")
    # bad.mk is not parsed (its include is not followed); other.mk is still scanned.
    (tmp_path / "bad.mk").write_bytes("include /hidden.mk\nX = 1\x85define Y\n".encode())
    (tmp_path / "other.mk").write_text("include /outside.mk\n")
    monkeypatch.chdir(tmp_path)

    code = _run(["validate", "--json"])

    assert json.loads(capsys.readouterr().out)["violations"] == [
        {"path": "Makefile", "message": f"'bad.mk' {FOREIGN_SEPARATOR} (U+0085); use LF or CRLF line endings"},
        {"path": "Makefile", "message": "include '/outside.mk' is outside the service directory"},
    ]
    assert code == 1


@pytest.mark.ac("IDP-28:AC-2")
@pytest.mark.parametrize("mixed", [False, True], ids=["crlf", "mixed-lf-crlf"])
def test_crlf_makefile_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mixed: bool
) -> None:
    _write_idp(tmp_path)
    makefile = _write_makefile(tmp_path, tuple(t for t in ALL_TARGETS if t not in {"lint", "verify"}))
    # `lint \` + `verify:` is one rule line naming both targets only if the CRLF continuation is joined.
    lines = [*makefile.read_text().splitlines(), "-include gen.mk", "lint \\", "verify:", "\t@true"]
    endings = ["\n" if mixed and i % 2 else "\r\n" for i in range(len(lines))]
    makefile.write_bytes("".join(line + end for line, end in zip(lines, endings, strict=True)).encode("utf-8"))
    monkeypatch.chdir(tmp_path)

    code = _run(["validate"])

    assert capsys.readouterr().out == "idp.yaml: valid (idp-service.v1.json)\n"
    assert code == 0
    assert contract.makefile_targets(makefile).include_words == ("gen.mk",)


# --- IDP-28 AC-4: the scan records `$` include words (conformance pins or rejects them) ----------------------------


@pytest.mark.ac("IDP-28:AC-4")
def test_makefile_scan_records_dynamic_include_words(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "include $(IDP_PROFILE_DIR)/defaults.mk common.mk\n"
        "-include $(V)/d.mk a$$b.mk *.mk\n"  # `*.mk` (glob, no `$`) is in neither list
        "include $(IDP_PROFILE_DIR)/defaults.mk\n"  # repeated spelling: recorded once
        "lint:\n\t@true\n"
    )
    (tmp_path / "common.mk").write_text("sinclude $(V)/d.mk ${W}.mk\nverify:\n\t@true\n")

    scan = contract.makefile_targets(makefile)

    assert scan.dynamic_include_words == ("$(IDP_PROFILE_DIR)/defaults.mk", "$(V)/d.mk", "a$$b.mk", "${W}.mk")
    assert scan.include_words == ("common.mk",)
    assert scan.targets == {"lint", "verify"}
    assert scan.violations == ()


@pytest.mark.ac("IDP-28:AC-4")
@pytest.mark.parametrize(
    ("dynamic", "violations"),
    [(24, ()), (25, (contract.Violation("Makefile", "too many include words (limit 1024)"),))],
    ids=["at-limit", "over-limit"],
)
def test_dynamic_include_words_share_the_include_spelling_cap(
    tmp_path: Path, dynamic: int, violations: tuple[contract.Violation, ...]
) -> None:
    literal = " ".join(f"missing{i}.mk" for i in range(1000))  # not on disk: recorded, never read
    words = " ".join(f"$(V{i}).mk" for i in range(dynamic))
    makefile = tmp_path / "Makefile"
    makefile.write_text(f"-include {literal}\n-include {words}\nlint:\n\t@true\n")

    scan = contract.makefile_targets(makefile)

    assert scan.violations == violations
    assert len(scan.include_words) == 1000
    assert len(scan.dynamic_include_words) == 24


@pytest.mark.ac("IDP-28:AC-4")
def test_dynamic_words_on_backslash_include_lines_are_not_recorded(tmp_path: Path) -> None:
    scan = _scan_text(tmp_path, "-include $(V)/x.mk \\\n  $(W)/y.mk\nsinclude $(V)/a\\ b.mk\nlint:\n")

    assert scan.dynamic_include_words == ()
    assert scan.violations == (
        contract.Violation("Makefile", f"include line in 'Makefile' {BACKSLASH_INCLUDE}"),
        contract.Violation("Makefile", f"include line in 'Makefile' {BACKSLASH_INCLUDE}"),
    )


# --- IDP-28 AC-5: load_service returns the scan it validated ------------------------------------------------------


@pytest.mark.ac("IDP-28:AC-5")
def test_load_service_returns_the_validated_scan(tmp_path: Path) -> None:
    path = _write_idp(tmp_path)
    makefile = _write_makefile(tmp_path)
    makefile.write_text(makefile.read_text() + "-include gen.mk\ninclude $(V)/d.mk\n")

    result = contract.load_service(path)

    assert len(result) == 3
    doc, violations, scan = result
    assert doc == _doc_example()
    assert violations == []
    assert scan.targets == frozenset(ALL_TARGETS)
    assert scan.include_words == ("gen.mk",)
    assert scan.dynamic_include_words == ("$(V)/d.mk",)
    assert contract.validate_service(path) == []


@pytest.mark.ac("IDP-28:AC-5")
@pytest.mark.parametrize(
    ("idp_yaml", "paths"),
    [
        ("a: [unclosed\n", [""]),
        ("- just\n- a list\n", [""]),
        (None, ["Makefile"]),
    ],
    ids=["invalid-yaml", "non-mapping-yaml", "makefile-not-found"],
)
def test_load_service_returns_an_empty_scan_when_makefile_was_not_scanned(
    tmp_path: Path, idp_yaml: str | None, paths: list[str]
) -> None:
    path = tmp_path / "idp.yaml"
    if idp_yaml is None:  # a valid idp.yaml without a Makefile
        _write_idp(tmp_path)
    else:
        path.write_text(idp_yaml)
        _write_makefile(tmp_path)

    result = contract.load_service(path)

    assert len(result) == 3
    _, violations, scan = result
    assert [v.path for v in violations] == paths
    assert scan == contract.MakefileScan(frozenset(), ())


# --- IDP-28 amendment 1 helpers -------------------------------------------------------------------------------------


def _write_service(directory: Path, extra: str, targets: Sequence[str] = ALL_TARGETS, crlf: bool = False) -> Path:
    """idp.yaml plus a Makefile defining `targets` followed by `extra` (every line ending CRLF if `crlf`)."""
    _write_idp(directory)
    makefile = _write_makefile(directory, targets)
    text = makefile.read_text() + extra
    makefile.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
    return makefile


def _validate(directory: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[str, int]:
    """Run `idp validate` in `directory`; return (stdout, exit code)."""
    monkeypatch.chdir(directory)
    code = _run(["validate"])
    return capsys.readouterr().out, code


# --- IDP-28 AC-6: continuations are collapsed (as make does) before directives are recognised ----------------------


@pytest.mark.ac("IDP-28:AC-6")
@pytest.mark.parametrize(
    ("text", "include_words", "targets"),
    [
        ("define Y\nbody\n\\\n  endef\n-include gen.mk\ngen.mk:\n\t@true\n", ("gen.mk",), {"gen.mk"}),
        ("define Y\r\nbody\r\n\\\r\n  endef\r\n-include gen.mk\r\ngen.mk:\r\n\t@true\r\n", ("gen.mk",), {"gen.mk"}),
        ("define \\\n  Y\ninside:\nendef\nafter:\n", (), {"after"}),
        ("X = a\\\\\\\n-include gen.mk\nlint:\n", (), {"lint"}),
        ("lint  \\\n  verify:\n", (), {"lint", "verify"}),
    ],
    ids=[
        "continued-endef-closes-define",
        "continued-endef-closes-define-crlf",
        "continued-define-name-opens-block",
        "three-backslashes-keep-one-literal",
        "blanks-around-continuation-collapse",
    ],
)
def test_continuations_are_collapsed_before_directives(
    tmp_path: Path, text: str, include_words: tuple[str, ...], targets: set[str]
) -> None:
    scan = _scan_text(tmp_path, text)

    assert scan.include_words == include_words
    assert scan.targets == targets
    assert scan.violations == ()


# --- IDP-28 AC-7: an include directive reached through a continuation is an IDP-22 AC-7 violation ------------------


@pytest.mark.ac("IDP-28:AC-7")
@pytest.mark.parametrize(
    ("extra", "crlf", "out", "code"),
    [
        ("\\\n-include gen.mk\n", False, f"idp.yaml: Makefile: include line in 'Makefile' {BACKSLASH_INCLUDE}\n", 1),
        ("\\\n-include gen.mk\n", True, f"idp.yaml: Makefile: include line in 'Makefile' {BACKSLASH_INCLUDE}\n", 1),
        (
            "\\\n   -include gen.mk\n",
            False,
            f"idp.yaml: Makefile: include line in 'Makefile' {BACKSLASH_INCLUDE}\n",
            1,
        ),
        ("X = \\\n-include gen.mk\n", False, "idp.yaml: valid (idp-service.v1.json)\n", 0),
    ],
    ids=["lf", "crlf", "leading-blanks", "assignment-not-include"],
)
def test_continued_include_directive_is_a_backslash_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra: str,
    crlf: bool,
    out: str,
    code: int,
) -> None:
    makefile = _write_service(tmp_path, extra, crlf=crlf)

    assert _validate(tmp_path, monkeypatch, capsys) == (out, code)
    # Offending words are not queued (so not pinned); the assignment includes nothing in make either.
    assert contract.makefile_targets(makefile).include_words == ()


# --- IDP-28 AC-8: `override \` + `define Y` opens a define block; `\` + `verify:` is not credited (Q18) ---------------


@pytest.mark.ac("IDP-28:AC-8")
@pytest.mark.parametrize(
    ("extra", "crlf"),
    [
        ("override \\\ndefine Y\nverify:\n\t@true\nendef\n", False),
        ("override \\\ndefine Y\nverify:\n\t@true\nendef\n", True),
        ("\\\nverify:\n\t@true\n", False),
    ],
    ids=["override-continued-into-define", "override-continued-into-define-crlf", "q18-blank-after-collapse"],
)
def test_override_continued_into_define_hides_its_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], extra: str, crlf: bool
) -> None:
    _write_service(tmp_path, extra, targets=tuple(t for t in ALL_TARGETS if t != "verify"), crlf=crlf)

    assert _validate(tmp_path, monkeypatch, capsys) == ("idp.yaml: Makefile: missing required target 'verify'\n", 1)


# --- IDP-28 AC-9: define body lines close and (do not) nest like make's do_define ---------------------------------


@pytest.mark.ac("IDP-28:AC-9")
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("closing", ["endef", "  endef", "endef # done"], ids=["endef", "indented", "comment"])
@pytest.mark.parametrize(
    "body",
    ["define#", "define#x", "override define B", "export define B", "\tdefine B", "defineX"],
    ids=["define-hash", "define-hash-x", "override-define", "export-define", "tab-define", "defineX"],
)
def test_define_body_lines_close_and_nest_like_make(tmp_path: Path, body: str, closing: str, newline: str) -> None:
    lines = ["define A", body, "inside:", closing, "after:"]
    scan = _scan_text(tmp_path, "".join(line + newline for line in lines))

    assert scan.targets == {"after"}
    assert scan.violations == ()


# --- IDP-28 AC-10: body lines make reads differently in skipped conditional branches are violations ---------------

AMBIGUOUS_DEFINE = (
    "has a line make reads differently in skipped conditional branches"
    " (nested define, endef followed by '#', or tab-indented endef); remove it"
)


@pytest.mark.ac("IDP-28:AC-10")
@pytest.mark.parametrize(
    ("makefile_extra", "common", "crlf", "shown"),
    [
        ("define A\ndefine B\nendef\nafter:\n", "", False, "'Makefile'"),
        ("define A\ndefine\nendef\nafter:\n", "", False, "'Makefile'"),
        ("define A\ndefine # c\nendef\nafter:\n", "", False, "'Makefile'"),
        ("define A\nendef#c\nendef\nafter:\n", "", False, "'Makefile'"),
        ("define A\n\tendef\nendef\nafter:\n", "", False, "'Makefile'"),
        ("define A\n\tendef#c\nendef\nafter:\n", "", False, "'Makefile'"),
        ("define A\ndefine B\nendef\nafter:\n", "", True, "'Makefile'"),
        # Moved from IDP-17 test_define_bodies_are_skipped_including_nested_ones (nested define, amendment 1).
        (
            "override define OUTER\ndefine INNER\ninside-nested:\nendef\nafter:\n",
            "",
            False,
            "'Makefile'",
        ),
        ("include common.mk\nafter:\n", "define A\ndefine B\nendef\n", False, "'common.mk'"),
    ],
    ids=[
        "nested-define",
        "bare-define",
        "define-blank-comment",
        "endef-hash",
        "tab-endef",
        "tab-endef-hash",
        "nested-define-crlf",
        "nested-in-override-define",
        "in-include",
    ],
)
def test_ambiguous_define_body_line_is_a_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    makefile_extra: str,
    common: str,
    crlf: bool,
    shown: str,
) -> None:
    makefile = _write_service(tmp_path, makefile_extra, crlf=crlf)
    (tmp_path / "common.mk").write_text(common)

    assert _validate(tmp_path, monkeypatch, capsys) == (
        f"idp.yaml: Makefile: define body in {shown} {AMBIGUOUS_DEFINE}\n",
        1,
    )
    # The scan goes on after the offending line: the block closes at the plain `endef`.
    assert "after" in contract.makefile_targets(makefile).targets


@pytest.mark.ac("IDP-28:AC-10")
def test_each_ambiguous_define_body_line_is_reported(tmp_path: Path) -> None:
    scan = _scan_text(tmp_path, "define A\ndefine B\nendef#c\nendef\nlint:\n")

    assert scan.violations == (
        contract.Violation("Makefile", f"define body in 'Makefile' {AMBIGUOUS_DEFINE}"),
        contract.Violation("Makefile", f"define body in 'Makefile' {AMBIGUOUS_DEFINE}"),
    )
    assert scan.targets == {"lint"}


# --- IDP-28 AC-11: characters make reads differently (Python whitespace, C0 controls incl. NUL) are violations -----

FOREIGN_CHARACTER = "contains a control or space character make reads differently"
# Computed from Python itself so a Unicode update cannot silently widen the gap: every `isspace()` character except
# space, tab, LF, CR and the AC-2 line separators, plus the C0 controls U+0000-U+0008 and U+000E-U+001B.
_AC2_SEPARATORS = " \t\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"
_FOREIGN_CHARACTERS = [
    *(chr(i) for i in range(0x110000) if chr(i).isspace() and chr(i) not in _AC2_SEPARATORS),
    *(chr(i) for i in range(0x00, 0x09)),
    *(chr(i) for i in range(0x0E, 0x1C)),
]


@pytest.mark.ac("IDP-28:AC-11")
def test_foreign_character_parameters_cover_the_known_gap() -> None:
    # Literal floor for the computed parameters: the characters the review reproduced must always be covered.
    known = {"\x00", "\x1f", "\xa0", "\u1680", "\u2000", "\u200a", "\u202f", "\u205f", "\u3000"}
    assert known <= set(_FOREIGN_CHARACTERS)
    assert len(_FOREIGN_CHARACTERS) == 40


@pytest.mark.ac("IDP-28:AC-11")
@pytest.mark.parametrize("char", _FOREIGN_CHARACTERS, ids=[f"U+{ord(c):04X}" for c in _FOREIGN_CHARACTERS])
def test_character_make_reads_differently_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], char: str
) -> None:
    _write_service(tmp_path, f"extra: a{char}b\n")

    out, code = _validate(tmp_path, monkeypatch, capsys)

    # The ids above name the code point; the message must name the same one.
    assert out == (
        f"idp.yaml: Makefile: 'Makefile' {FOREIGN_CHARACTER} (U+{ord(char):04X});"
        " use only spaces, tabs and LF or CRLF line endings\n"
    )
    assert code == 1


@pytest.mark.ac("IDP-28:AC-11")
def test_character_make_reads_differently_in_included_file_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_service(tmp_path, "include bad.mk other.mk\n")
    # bad.mk is not parsed (its include is not followed); other.mk is still scanned.
    (tmp_path / "bad.mk").write_text("include /hidden.mk\n-include a.mk\xa0b.mk\n", encoding="utf-8")
    (tmp_path / "other.mk").write_text("include /outside.mk\n")
    monkeypatch.chdir(tmp_path)

    code = _run(["validate", "--json"])

    assert json.loads(capsys.readouterr().out)["violations"] == [
        {
            "path": "Makefile",
            "message": f"'bad.mk' {FOREIGN_CHARACTER} (U+00A0); use only spaces, tabs and LF or CRLF line endings",
        },
        {"path": "Makefile", "message": "include '/outside.mk' is outside the service directory"},
    ]
    assert code == 1


@pytest.mark.ac("IDP-28:AC-11")
def test_spaces_tabs_and_crlf_are_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # DEL (U+007F) and U+FEFF are neither blanks to make nor to str.isspace(): accepted.
    extra = "extra:\t \t deps   more\n\t@echo a\x7fb\ufeffc\t  d\n"
    makefile = _write_service(tmp_path, extra, crlf=True)

    assert _validate(tmp_path, monkeypatch, capsys) == ("idp.yaml: valid (idp-service.v1.json)\n", 0)
    assert contract.makefile_targets(makefile).targets == {*ALL_TARGETS, "extra"}


# --- IDP-28 AC-12: define lines with export, unexport or private are violations ------------------------------------

MODIFIER_DEFINE = (
    "has a define with export, unexport or private, which GNU make 3.81 and 4.x read differently;"
    " use define or override define"
)


@pytest.mark.ac("IDP-28:AC-12")
@pytest.mark.parametrize(
    ("line", "crlf"),
    [
        ("export define X = 1", False),
        ("private define X = 1", False),
        ("unexport define X", False),
        ("override export define X", False),
        ("export override define X", False),
        ("private define X = 1", True),
        # Moved from IDP-17 test_define_bodies_are_skipped_including_nested_ones (amendment 1).
        ("export define EXPORTED =", False),
    ],
    ids=[
        "export",
        "private",
        "unexport",
        "override-export",
        "export-override",
        "private-crlf",
        "export-trailing-equals",
    ],
)
def test_define_with_export_unexport_or_private_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], line: str, crlf: bool
) -> None:
    makefile = _write_service(tmp_path, f"{line}\nlate:\n", crlf=crlf)

    assert _validate(tmp_path, monkeypatch, capsys) == (f"idp.yaml: Makefile: 'Makefile' {MODIFIER_DEFINE}\n", 1)
    # The line opens no block, so the scanner keeps reading the lines after it.
    assert "late" in contract.makefile_targets(makefile).targets


@pytest.mark.ac("IDP-28:AC-12")
@pytest.mark.parametrize(
    "extra",
    [
        "define X\ninside:\nendef\n",
        "override define X\ninside:\nendef\n",
        "export define ?= 3\n",
        "define X = 1\ninside:\nendef\n",
    ],
    ids=["define", "override-define", "assignment-to-define", "define-with-equals"],
)
def test_define_and_override_define_are_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], extra: str
) -> None:
    makefile = _write_service(tmp_path, extra + "late:\n")

    assert _validate(tmp_path, monkeypatch, capsys) == ("idp.yaml: valid (idp-service.v1.json)\n", 0)
    assert contract.makefile_targets(makefile).targets == {*ALL_TARGETS, "late"}


# --- IDP-28 AC-13: include words starting with `~` (also after leading `./` runs) are outside the service dir ------


@pytest.mark.ac("IDP-28:AC-13")
@pytest.mark.parametrize(
    ("word", "message"),
    [
        ("~/evil.mk", "include '~/evil.mk' is outside the service directory"),
        ("~user/x.mk", "include '~user/x.mk' is outside the service directory"),
        ("~", "include '~' is outside the service directory"),
        ("./~/evil.mk", "include './~/evil.mk' is outside the service directory"),
        (".//~/evil.mk", "include './/~/evil.mk' is outside the service directory"),
        ("././~/evil.mk", "include '././~/evil.mk' is outside the service directory"),
    ],
    ids=["home", "user-home", "bare-tilde", "dot-slash", "dot-double-slash", "dot-slash-twice"],
)
def test_include_word_starting_with_tilde_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], word: str, message: str
) -> None:
    makefile = _write_service(tmp_path, f"-include {word}\n")

    assert _make_messages(tmp_path, monkeypatch, capsys) == [message]
    assert word not in contract.makefile_targets(makefile).include_words


@pytest.mark.ac("IDP-28:AC-13")
def test_tilde_inside_include_word_is_a_literal_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # make expands `~` only at the start (after leading `./` runs): these are read as written, inside the service.
    makefile = _write_service(tmp_path, "-include a~b.mk sub/../~/x.mk\n")

    assert _validate(tmp_path, monkeypatch, capsys) == ("idp.yaml: valid (idp-service.v1.json)\n", 0)
    assert contract.makefile_targets(makefile).include_words == ("a~b.mk", "sub/../~/x.mk")


# --- IDP-28 review loop 2: regressions found after T14 -------------------------------------------------------------


@pytest.mark.ac("IDP-28:AC-9")
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_tab_continued_into_define_after_rule_is_a_recipe_line(tmp_path: Path, newline: str) -> None:
    # make decides recipe-or-directive on the raw line (tab first), before collapsing: `\t\` + `define X` after a rule
    # is a recipe line, so the lines after it are read (collapsed it would look like ` define X`).
    lines = ["unused:", "\t\\", "define X", "-include gen.mk", "after:"]
    scan = _scan_text(tmp_path, "".join(line + newline for line in lines))

    assert scan.targets == {"unused", "after"}
    assert scan.include_words == ("gen.mk",)
    assert scan.violations == ()


@pytest.mark.ac("IDP-28:AC-9")
@pytest.mark.parametrize(
    "line",
    ["define $(NAME) = 1", "override define $(NAME) = 1", "define ${NAME} = 1", "define $(NAME)"],
    ids=["dollar-paren", "override-dollar-paren", "dollar-brace", "dollar-no-operator"],
)
def test_define_with_variable_reference_name_opens_a_block(tmp_path: Path, line: str) -> None:
    # GNU make 3.81, 4.3 and 4.4.1 all open a define block here (4.x warns about extra text after `define`; an empty
    # name is fatal), so the body is not read: the scanner skips it too.
    scan = _scan_text(tmp_path, f"NAME := n\n{line}\n-include gen.mk\ninside:\nendef\nafter:\n")

    assert scan.targets == {"after"}
    assert scan.include_words == ()
    assert scan.violations == ()


@pytest.mark.ac("IDP-28:AC-13")
@pytest.mark.parametrize(
    ("words", "outside"),
    [
        ("sub/../~/x.mk ~/x.mk", "~/x.mk"),
        ("~/x.mk sub/../~/x.mk", "~/x.mk"),
        ("sub/../~/x.mk ./~/x.mk", "./~/x.mk"),
        ("./~/x.mk sub/../~/x.mk", "./~/x.mk"),
    ],
    ids=["alias-then-tilde", "tilde-then-alias", "alias-then-dot-tilde", "dot-tilde-then-alias"],
)
def test_tilde_word_is_reported_when_a_literal_word_normalises_to_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], words: str, outside: str
) -> None:
    # `sub/../~/x.mk` normalises to `~/x.mk`; the tilde word must not be dropped as its duplicate (make reads $HOME).
    makefile = _write_service(tmp_path, f"-include {words}\n")

    assert _make_messages(tmp_path, monkeypatch, capsys) == [f"include '{outside}' is outside the service directory"]
    assert contract.makefile_targets(makefile).include_words == ("sub/../~/x.mk",)


@pytest.mark.ac("IDP-28:AC-13")
def test_repeated_outside_include_words_are_checked_in_linear_time(tmp_path: Path) -> None:
    # 200 000 repeats of one outside word (just under 1 MiB): each repeat must be an O(1) lookup.
    scan = _scan_text(tmp_path, "-include" + " ../a" * 200_000 + "\nlint:\n")

    assert scan.violations == (contract.Violation("Makefile", "include '../a' is outside the service directory"),)
    assert scan.targets == {"lint"}


@pytest.mark.ac("IDP-28:AC-13")
@pytest.mark.parametrize("word", ["~/x.m?", "./~/x.m*", "~[a]", "../../home/x.m?", "/etc/*.mk"])
def test_outside_glob_include_word_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], word: str
) -> None:
    # make globs these words outside the service directory (`~` is expanded first): fail closed.
    makefile = _write_service(tmp_path, f"-include {word}\n")

    assert _make_messages(tmp_path, monkeypatch, capsys) == [f"include {word!r} is outside the service directory"]
    assert contract.makefile_targets(makefile).include_words == ()


@pytest.mark.ac("IDP-28:AC-13")
def test_glob_include_word_inside_service_is_still_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    makefile = _write_service(tmp_path, "-include sub/*.mk a?.mk a~[b].mk\n")

    assert _validate(tmp_path, monkeypatch, capsys) == ("idp.yaml: valid (idp-service.v1.json)\n", 0)
    assert contract.makefile_targets(makefile).include_words == ()


@pytest.mark.ac("IDP-17:AC-6")
def test_include_spellings_through_a_symlink_are_scanned_as_make_reads_them(tmp_path: Path) -> None:
    # `link/../b.mk` with `link -> sub/deep` is `sub/b.mk` for make (the OS resolves the link before `..`), not `b.mk`.
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    (tmp_path / "link").symlink_to(Path("sub") / "deep")
    (tmp_path / "b.mk").write_text("top:\n")
    (tmp_path / "sub" / "b.mk").write_text("hidden:\n")

    scan = _scan_text(tmp_path, "-include b.mk\n-include link/../b.mk ./b.mk\n")

    assert scan.targets == {"top", "hidden"}
    assert scan.include_words == ("b.mk", "link/../b.mk", "./b.mk")
    assert scan.violations == ()


@pytest.mark.ac("IDP-28:AC-10")
def test_define_problems_past_the_cap_stop_the_scan(tmp_path: Path) -> None:
    limit = contract.MAX_INCLUDE_PROBLEMS
    scan = _scan_text(tmp_path, "define A\n" + "define B\n" * 50_000 + "endef\nlint:\n")

    assert len(scan.violations) == limit + 1
    assert scan.violations[-1] == contract.Violation("Makefile", f"too many include problems (limit {limit})")
