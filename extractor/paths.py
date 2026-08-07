"""Where the library lives, for tools that used to assume it was ``./data``.

The pipeline scripts each pinned the data root themselves — some relative to
the repo, some relative to the working directory — which was fine while the
only caller was a developer standing in the repo. The installed Catalog
Builder keeps its library in a workspace the user chose, so a hard-coded
``data/`` silently wrote to the wrong place, or to nowhere.

One resolution order, used by all of them:

1. ``--data <path>`` on the command line
2. ``SR6_DATA`` in the environment
3. ``<repo>/data``, which is what a developer expects
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


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
