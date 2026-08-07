"""Artwork support, downloaded only if it is wanted.

OpenCV is 155 MB and onnxruntime 41 MB. Together they are roughly two thirds
of everything the builder would otherwise ship, and they are reachable from
exactly one module — ``extractor/images_extract.py``, which lifts
illustrations off the page and strips their backgrounds. The text pipeline
never imports them; that was measured, not assumed.

So the base install is ~150 MB and does everything except artwork, and the
art path installs on demand into the workspace rather than the program folder
— it is data the user chose to add, not part of the program, and an uninstall
should not have to reason about it.

Without it, items still get icons from the local icon library. What is missing
is automatic extraction of illustrations from the page.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

#: What the art path actually needs, beyond the base install.
PACKAGES = ["opencv-python-headless", "onnxruntime", "rembg", "pillow"]

SIZE_HINT = "about 250 MB"

EXPLAIN = (
    "Artwork support lets the builder lift illustrations straight off the "
    f"page and strip their backgrounds. It is {SIZE_HINT}, which is why it is "
    "not part of the main install.\n\n"
    "Without it everything else works: items still take icons from your local "
    "icon library, and you can assign artwork by hand in the review app."
)


def target_dir(workspace: Path) -> Path:
    """Where the extra packages live — beside the data, not in the program."""
    return Path(workspace) / "_art-support"


def installed(workspace: Path) -> bool:
    d = target_dir(workspace)
    return d.is_dir() and any(d.glob("cv2*"))


def install(workspace: Path, on_line=None) -> bool:
    """Fetch the art packages into the workspace.

    Uses pip against the bundled interpreter. A frozen build has no pip, so
    this needs Python present — which is the honest limitation, reported
    rather than papered over.
    """
    d = target_dir(workspace)
    d.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-m", "pip", "install", "--target", str(d), *PACKAGES]
    if getattr(sys, "frozen", False):
        if on_line:
            on_line("Artwork support needs Python installed to fetch its "
                    "components. Install Python 3.11+ and try again, or assign "
                    "artwork by hand in the review app.")
        return False
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1)
    for line in p.stdout:
        if on_line:
            on_line(line.rstrip())
    p.wait()
    return p.returncode == 0


def enable_on_path(workspace: Path) -> None:
    """Make an installed art pack importable for this process."""
    d = str(target_dir(workspace))
    if d not in sys.path:
        sys.path.insert(0, d)
