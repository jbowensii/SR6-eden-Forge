from __future__ import annotations

import json
from pathlib import Path

from validator.model import DataFile, Issue


def discover(root: Path) -> tuple[list[DataFile], list[Issue]]:
    """Recursively find *.json files under root.

    Returns (files, issues) sorted by path. Files that cannot be read or
    parsed (including non-UTF-8 encoding) are reported as ``parse`` issues
    rather than raising an exception.
    """
    files: list[DataFile] = []
    issues: list[Issue] = []
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            issues.append(Issue(file=str(path), item_id=None, rule="parse", message=str(exc)))
            continue
        if not isinstance(payload, dict):
            issues.append(
                Issue(file=str(path), item_id=None, rule="parse", message="root must be a JSON object")
            )
            continue
        files.append(DataFile(path=path, payload=payload))
    return files, issues
