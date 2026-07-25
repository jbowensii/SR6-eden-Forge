from __future__ import annotations

import json
from pathlib import Path

from validator.model import DataFile, Issue


def discover(root: Path) -> tuple[list[DataFile], list[Issue]]:
    files: list[DataFile] = []
    issues: list[Issue] = []
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            issues.append(Issue(file=str(path), item_id=None, rule="parse", message=str(exc)))
            continue
        if not isinstance(payload, dict):
            issues.append(
                Issue(file=str(path), item_id=None, rule="parse", message="root must be a JSON object")
            )
            continue
        files.append(DataFile(path=path, payload=payload))
    return files, issues
