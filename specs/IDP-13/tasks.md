# IDP-13: tasks

- [ ] T1 Add `spec_trace.to_dict(report)` and the `--json` flag on the success path of `idp spec-trace` (sorted, de-duplicated lists; key order per spec). Add tests `test_json_all_covered_prints_object_and_exits_0`, `test_json_output_is_sorted_and_deterministic`, `test_json_uncovered_ac_listed_in_missing_and_exits_1` and `test_without_json_flag_output_is_unchanged` in packages/idp-gate/tests/test_spec_trace.py. (AC-1, AC-2, AC-4)
- [ ] T2 Handle a missing spec in `--json` mode: print `{"ticket", "ok": false, "error": "spec not found: <path>"}` to stdout, nothing to stderr, exit 1. Add test `test_json_missing_spec_prints_error_object_and_exits_1`. (AC-3, AC-4)
- [ ] T3 Add the CHANGELOG `[Unreleased]` / `Added` entry for IDP-13; run `make verify` and `idp spec-trace IDP-13` (both green). (AC-1, AC-2, AC-3, AC-4)
