# python-uv: notes for test-writing agents

Stack idioms for services and libraries using the `python-uv` build profile (ADR-0012). Read these before you write
tests.

## pytest idioms
- Layout: each package has a `tests/` directory next to `src/`. Files are named `test_*.py` and use plain `test_*`
  functions. Do not use `unittest.TestCase`.
- Use plain `assert` with LITERAL expected values (`assert out == "name: demo\n"`). Never recompute the expected value
  with the code under test.
- Errors: `with pytest.raises(SomeError) as excinfo:`, then assert on `excinfo.value`.
- Cases: `@pytest.mark.parametrize(...)` with readable `ids=[...]`. Do not loop over cases inside one test.
- CLIs: call the entry point (`main([...])`) and check stdout/stderr with `capsys.readouterr()`. Assert the exit code.
- Subprocesses: use `subprocess.run(..., capture_output=True, text=True, timeout=60, check=False)`. Call
  `pytest.skip(...)` when the tool is missing (`shutil.which(...) is None`).
- No sleeps, no network and no dependence on wall-clock time. Every test must be able to fail
  (`idp test-quality-lint` flags tests that cannot).
- Type-annotate tests (`-> None`, fixture parameter types): mypy runs in strict mode.

## AC tagging
- Tag every test that covers an acceptance criterion with `@pytest.mark.ac("<KEY>:AC-n")`, for example
  `@pytest.mark.ac("IDP-18:AC-1")`. One test may carry several ids. Evidence reports the tag as `ac:<KEY>:AC-n`.
- `ac` is registered under `[tool.pytest.ini_options].markers` in `pyproject.toml`, and pytest runs with
  `--strict-markers`, so an unregistered marker is an error.
- `idp spec-trace <KEY>` checks that every `**AC-n**` in `specs/<KEY>/spec.md` has at least one tagged test. It reads
  the decorator statically, so write the id as a string literal.
- Other registered markers: `p0`, `p1`, `critical`, `smoke`, `quarantine`.

## Fixture conventions
- Use built-in fixtures first: `tmp_path` for files and directories, and `monkeypatch` for environment variables,
  module attributes (`monkeypatch.setattr(module, "_NAME", value)`) and the working directory. Never write into the
  repository during a test.
- Put shared fixtures in a `conftest.py` at the narrowest scope that needs them, such as `tests/<area>/conftest.py`.
- Prefer small factory helpers (`_valid_doc(name="demo") -> dict`) that return fresh data over shared mutable
  fixtures. Each test builds its own data and passes in any order.
- `make test` runs pytest with coverage and writes JUnit (`junit-unit.xml`) and Cobertura (`coverage.xml`) to
  `$(REPORTS_DIR)`.
