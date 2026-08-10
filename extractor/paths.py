"""Where the library lives, for tools that used to assume it was ``./data``.

The pipeline scripts each pinned the data root themselves — some relative to
the repo, some relative to the working directory — which was fine while the
only caller was a developer standing in the repo. The installed Catalog
Builder keeps its library in a workspace the user chose, so a hard-coded
``data/`` silently wrote to the wrong place, or to nowhere.

One resolution order, used by all of them:

1. ``--data <path>`` on the command line
2. ``SR6_DATA`` in the environment
3. the workspace the Catalog Builder recorded, if that library exists
4. ``<repo>/data``, which is what a developer expects

Step 3 is the important one. ``<repo>/data`` is a developer's scratch copy that
drifts from the real library the moment the installed builder is used, and a
tool run against it reports entirely plausible numbers while changing nothing
the user can see. That has cost real data twice — a backup that protected the
scratch copy, and an icon pass that appeared to do nothing. When the builder has
recorded a workspace, that workspace IS the library; ask for the scratch copy
explicitly with ``--data`` if you want it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def builder_workspace() -> Path | None:
    """The library the installed Catalog Builder is managing, if any.

    Reads the same ``%APPDATA%\\SR6CatalogBuilder\\settings.json`` the builder
    writes, rather than duplicating the path here, so the two can never disagree
    about where the data went.
    """
    base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    config = Path(base) / "SR6CatalogBuilder" / "settings.json"
    try:
        workspace = json.loads(config.read_text(encoding="utf-8")).get("workspace")
    except (OSError, ValueError, AttributeError):
        return None
    if not workspace:
        return None
    data = Path(workspace) / "data"
    return data if data.is_dir() else None


def data_root(argv: list[str] | None = None) -> Path:
    """The library root, per the order above."""
    argv = sys.argv[1:] if argv is None else argv
    for i, a in enumerate(argv):
        if a == "--data" and i + 1 < len(argv):
            return Path(argv[i + 1])
        if a.startswith("--data="):
            return Path(a.split("=", 1)[1])
    env = os.environ.get("SR6_DATA")
    if env:
        return Path(env)
    recorded = builder_workspace()
    if recorded is not None:
        return recorded
    return REPO / "data"


def positional(argv: list[str] | None = None) -> list[str]:
    """Everything that is NOT the ``--data`` option.

    Some tools read bare ``sys.argv[1:]`` as a list of book slugs. Without this
    they would treat ``--data`` and its value as two books named "--data" and
    "C:\\...\\data", quietly scoping the run to nothing.
    """
    argv = sys.argv[1:] if argv is None else argv
    out: list[str] = []
    skip = False
    for a in argv:
        if skip:
            skip = False
            continue
        if a == "--data":
            skip = True
            continue
        if a.startswith("--data="):
            continue
        out.append(a)
    return out
