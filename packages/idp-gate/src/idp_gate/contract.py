"""Service contract (`idp.yaml`) validation against schema idp-service.v1 (ADR-0010)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SCHEMA_NAME = "idp-service.v1.json"


@dataclass(frozen=True)
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path or '<root>'}: {self.message}"


def load_schema() -> dict[str, Any]:
    text = resources.files("idp_gate.schemas").joinpath(SCHEMA_NAME).read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


def validate_document(doc: Any) -> list[Violation]:
    validator = Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    return [Violation(".".join(str(p) for p in e.absolute_path), e.message) for e in errors]


def validate_file(path: Path) -> list[Violation]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [Violation("", f"invalid YAML: {exc}")]
    return validate_document(doc)
