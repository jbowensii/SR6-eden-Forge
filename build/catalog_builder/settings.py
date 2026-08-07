"""Where the builder remembers what you told it.

Settings live in ``%APPDATA%\\SR6CatalogBuilder\\settings.json`` — outside the
install directory, so an upgrade or uninstall does not take your configuration
with it, and a per-user path so two accounts on one machine do not fight.

Only choices go here. Extracted data lives in the workspace the user picks,
and the PDFs stay wherever they already are; nothing is copied.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "SR6CatalogBuilder"


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    return Path(base) / APP_NAME


def default_workspace() -> Path:
    """Where extracted data goes. Documents, because the user will look at it."""
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "SR6 Catalog"


DEFAULTS: dict = {
    "pdfFolder": "",          # where the books are
    "commlink6Jar": "",       # optional
    "foundryData": "",        # ...\FoundryVTT\Data
    "workspace": "",          # extracted library + built modules
    "lastImport": "",
    "artSupport": False,      # the optional heavy download
    "firstRunDone": False,
}


class Settings:
    """A dict that knows where it lives. Saves are atomic."""

    def __init__(self, path: Path | None = None):
        self.path = path or (config_dir() / "settings.json")
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return                       # absent or unreadable: defaults stand
        if isinstance(stored, dict):
            # unknown keys are kept, so a downgrade does not discard newer ones
            self.data = {**DEFAULTS, **stored}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)           # atomic: never a half-written config

    # dict-ish access, because that is how it reads at the call sites
    def __getitem__(self, k):
        return self.data.get(k, DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.data[k] = v

    def get(self, k, default=None):
        return self.data.get(k, DEFAULTS.get(k, default))

    def workspace(self) -> Path:
        return Path(self["workspace"] or default_workspace())


#: Created under the workspace on first run rather than asked about. They are
#: ours to place — the user has no existing folder we would be overriding, and
#: a question with only one sensible answer is a question not worth asking.
WORKSPACE_DIRS = {
    "data": "extracted library, one folder per book",
    "export": "built catalog modules",
    "icons": "drop icon sets here to assign in the review app",
    "art": "artwork lifted from the books, and anything you add",
    "_ids": "catalog id lockfile — keeps ids stable when you rename things",
}


def ensure_workspace(ws: Path) -> Path:
    """Create the working folders, with a note saying what each is for.

    Idempotent, and it never touches anything already there.
    """
    ws = Path(ws)
    ws.mkdir(parents=True, exist_ok=True)
    for name, what in WORKSPACE_DIRS.items():
        d = ws / name
        d.mkdir(exist_ok=True)
        readme = d / "README.txt"
        if not readme.exists():
            readme.write_text(f"{name} - {what}\n", encoding="utf-8")
    return ws


def detect_foundry_data() -> Path | None:
    """Foundry's user data directory, if it is where Foundry usually puts it.

    Checked in the order Foundry itself prefers, so a user who moved it with
    --dataPath is simply asked instead of being silently pointed at a stale
    default.
    """
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "FoundryVTT" / "Data",
        Path.home() / "AppData" / "Local" / "FoundryVTT" / "Data",
        Path.home() / "FoundryVTT" / "Data",
        Path("C:/FoundryVTT/Data"),
    ]
    for c in candidates:
        if (c / "modules").is_dir() or (c / "worlds").is_dir():
            return c
    return None


def detect_commlink6() -> Path | None:
    """An installed Commlink6 jar, if one is lying around in the usual place."""
    roots = [
        Path.home() / "CommLink6" / "app",
        Path(os.environ.get("LOCALAPPDATA", "")) / "CommLink6",
        Path(os.environ.get("PROGRAMFILES", "")) / "CommLink6",
    ]
    newest = None
    for r in roots:
        if not r.is_dir():
            continue
        for jar in r.rglob("commlink6-*.jar"):
            if newest is None or jar.stat().st_mtime > newest.stat().st_mtime:
                newest = jar
    return newest
