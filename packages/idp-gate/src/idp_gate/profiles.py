"""Build profiles (`build-profiles/<name>/profile.yaml`) validated against schema build-profile.v1 (ADR-0012)."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from idp_gate import contract

PROFILE_SCHEMA_ID = "build-profile.v1"
PROFILE_SCHEMA_NAME = f"{PROFILE_SCHEMA_ID}.json"
PROFILE_FILE = "profile.yaml"


def validate_profile_document(doc: Any, dirname: str) -> list[contract.Violation]:
    """Schema violations of `doc`, then a violation at `name` if it differs from the profile's directory name."""
    validator = Draft202012Validator(contract.load_schema(PROFILE_SCHEMA_NAME))
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    violations = [contract.Violation(".".join(str(p) for p in e.absolute_path), e.message) for e in errors]
    name = doc.get("name") if isinstance(doc, dict) else None
    if isinstance(name, str) and name != dirname:
        violations.append(contract.Violation("name", f"name {name!r} does not match directory {dirname!r}"))
    return violations
