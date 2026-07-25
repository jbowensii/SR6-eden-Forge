from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Issue:
    file: str
    item_id: str | None
    rule: str
    message: str


@dataclass
class DataFile:
    path: Path
    payload: dict

    @property
    def book(self) -> str:
        return self.payload.get("book", "")

    @property
    def domain(self) -> str:
        return self.payload.get("domain", "")

    @property
    def category(self) -> str:
        return self.payload.get("category", "")
