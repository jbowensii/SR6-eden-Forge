"""Put the built catalog into Foundry.

The last step, and the one where a plain error message is worth most: by now
the user has spent real time extracting and correcting, and "Access is denied"
tells them nothing they can act on.

Two things reliably go wrong, and both are anticipated:

**Foundry is running.** Compendium packs are LevelDB, and Foundry holds a lock
on every pack in an open world. Copying over that lock fails partway and can
leave a pack unreadable. So the check happens *before* anything is written, and
the answer is "close Foundry first", not a permission trace.

**The data directory is somewhere else.** Foundry's ``--dataPath`` moves it.
Rather than guess wrong, an undetected path is asked for.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
from pathlib import Path

MANIFEST_URL = ("https://github.com/jbowensii/SR6-eden-Forge/"
                "releases/latest/download/module.json")


def foundry_running() -> bool:
    """Is Foundry up?

    Port first — it is the cheap, definitive answer for a running server — then
    the process name, which catches a launcher that has not opened a world yet.
    """
    try:
        with socket.socket() as s:
            s.settimeout(0.35)
            if s.connect_ex(("127.0.0.1", 30000)) == 0:
                return True
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Foundry Virtual Tabletop.exe"],
            capture_output=True, text=True, timeout=8, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return "Foundry" in out
    except Exception:
        return False


def module_dir(foundry_data: Path, module_id: str) -> Path:
    return Path(foundry_data) / "modules" / module_id


def check(foundry_data: Path) -> tuple[bool, str]:
    """Can we publish right now? Returns (ok, why-not)."""
    d = Path(foundry_data)
    if not d.is_dir():
        return False, f"Foundry data folder not found: {d}"
    if not (d / "modules").is_dir() and not (d / "worlds").is_dir():
        return False, (f"{d} does not look like Foundry's Data folder — it "
                       "should contain 'modules' and 'worlds'.")
    if foundry_running():
        return False, ("Foundry is running. Close it first — it keeps the "
                       "compendium files open, and writing over them while it "
                       "holds them can corrupt a pack.")
    return True, ""


def install(built: Path, foundry_data: Path, module_id: str) -> Path:
    """Copy one built module into Foundry, replacing any previous copy.

    The old module is moved aside rather than deleted first, and only removed
    once the new one is fully in place — so a failure midway leaves the
    previous working catalog rather than nothing at all.
    """
    src = Path(built)
    if not (src / "module.json").is_file():
        raise RuntimeError(f"{src} is not a built module (no module.json)")

    dest = module_dir(foundry_data, module_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup = dest.with_name(dest.name + ".previous")

    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    if dest.exists():
        dest.rename(backup)
    try:
        shutil.copytree(src, dest)
    except Exception:
        # put the working copy back before surfacing the failure
        shutil.rmtree(dest, ignore_errors=True)
        if backup.exists():
            backup.rename(dest)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    return dest


def summary(foundry_data: Path, module_id: str) -> str:
    d = module_dir(foundry_data, module_id)
    try:
        import json
        m = json.loads((d / "module.json").read_text(encoding="utf-8"))
        packs = len(m.get("packs") or [])
        return f"{m.get('title', module_id)} v{m.get('version', '?')} — {packs} packs"
    except Exception:
        return module_id


NEXT_STEPS = (
    "Installed. In Foundry:\n\n"
    "  1.  Launch your world\n"
    "  2.  Game Settings -> Manage Modules\n"
    "  3.  Enable 'Shadowrun 6th World Catalog'\n\n"
    "For the character generator, install SR6 Forge from this manifest URL:\n"
    f"  {MANIFEST_URL}\n\n"
    "(Add-on Modules -> Install Module -> paste into Manifest URL.)"
)
