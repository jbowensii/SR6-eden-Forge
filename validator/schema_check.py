from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from validator.model import DataFile, Issue

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


@lru_cache(maxsize=None)
def _registry() -> Registry:
    registry = Registry()
    for schema_path in SCHEMA_DIR.glob("*.schema.json"):
        resource = Resource.from_contents(json.loads(schema_path.read_text(encoding="utf-8")))
        registry = resource @ registry
    return registry


@lru_cache(maxsize=None)
def _validator_for(domain: str) -> Draft202012Validator | None:
    schema_path = SCHEMA_DIR / f"{domain}.schema.json"
    if not schema_path.is_file():
        return None
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_registry())


def _item_id_for(payload: dict, error_path: list) -> str | None:
    if len(error_path) >= 2 and error_path[0] == "items" and isinstance(error_path[1], int):
        item = payload["items"][error_path[1]]
        if isinstance(item, dict):
            return item.get("id")
    return None


def _without_blanks(payload: dict) -> dict:
    """A copy with empty-string system fields dropped. Items carry blank ("")
    fields so the editor shows every applicable slot to fill; those blanks are
    "not set" and must not be validated against a typed schema."""
    out = {**payload, "items": []}
    for item in payload.get("items", []):
        system = {k: v for k, v in item.get("system", {}).items() if v != ""}
        out["items"].append({**item, "system": system})
    return out


def check_file(df: DataFile) -> list[Issue]:
    validator = _validator_for(df.domain)
    if validator is None:
        return [
            Issue(
                file=str(df.path),
                item_id=None,
                rule="no-schema",
                message=f"no schema for domain {df.domain!r} (expected schemas/{df.domain}.schema.json)",
            )
        ]
    issues = []
    cleaned = _without_blanks(df.payload)
    for error in validator.iter_errors(cleaned):
        path = list(error.absolute_path)
        issues.append(
            Issue(
                file=str(df.path),
                item_id=_item_id_for(cleaned, path),
                rule="schema",
                message=f"{'/'.join(str(p) for p in path) or '<root>'}: {error.message}",
            )
        )
    return issues
