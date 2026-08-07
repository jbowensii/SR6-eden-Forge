"""Find or fetch Commlink6.

Commlink6 is Stefan Prelle's software, distributed from rpgframework.de under
his terms. It is not redistributed here and nothing about it is bundled: the
builder either finds a copy the user already installed, or offers to download
one from the author's own site, saying whose software it is before it does.

It is optional throughout. Without it every owned PDF is still read; what is
lost is the structure the printed page leaves implicit — counted accessory
mounts, what a quality grants, PACK contents, fake SIN levels.
"""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

HOME_PAGE = "https://commlink.rocks"
DOWNLOAD_PAGE = "https://commlink.rocks/download"

#: What the author actually ships on Windows: an updater, which then fetches
#: Commlink6 itself. Kept as a fallback — the live page is read first, because
#: this URL carries a version number and will go stale.
FALLBACK_MSI = ("https://www.rpgframework.de/commlink6-builds/win/"
                "Commlink6-Updater-1.0.3.msi")

#: Where a manual install usually lands, newest jar wins.
SEARCH_ROOTS = ("CommLink6/app", "CommLink6", "commlink6")

USER_AGENT = "SR6CatalogBuilder/1.0 (+https://github.com/jbowensii/SR6-eden-Forge)"


def find_local(extra: Path | None = None) -> Path | None:
    """An installed Commlink6 jar, newest first, or None."""
    import os

    roots = [Path.home() / r for r in SEARCH_ROOTS]
    for var in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(var)
        if base:
            roots += [Path(base) / r for r in SEARCH_ROOTS]
    if extra:
        roots.insert(0, Path(extra))

    found: list[Path] = []
    for r in roots:
        if r.is_dir():
            found += [p for p in r.rglob("commlink6-*.jar") if p.is_file()]
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


def validate(jar: Path) -> tuple[bool, str]:
    """Is this really a Commlink6 data jar?

    Checked by looking for the data tree rather than by filename, so a
    truncated download or the wrong jar is caught here instead of halfway
    through an import.
    """
    import zipfile

    jar = Path(jar)
    if not jar.is_file():
        return False, "file not found"
    try:
        with zipfile.ZipFile(jar) as z:
            names = z.namelist()
    except Exception as e:
        return False, f"not a readable zip ({type(e).__name__})"

    marker = "de/rpgframework/shadowrun6/data/"
    books = {n.split("/")[4] for n in names
             if n.startswith(marker) and len(n.split("/")) > 5}
    if not books:
        return False, "no Shadowrun 6 data inside — is this Commlink6?"
    return True, f"{len(books)} books"


def latest_windows_url(timeout: int = 12) -> str:
    """The Windows installer URL, verified reachable before it is handed back.

    Scraping the download page was tried and abandoned: commlink.rocks serves a
    240-byte shell and renders its links in the browser, so there is nothing in
    the HTML to find. A scraper would have failed silently on every run and
    quietly returned the fallback anyway — worse than not having one.

    So the known URL is used, but CHECKED first. When the author publishes a
    new version and this 404s, the caller is told, and the honest response is
    to open the download page and let the user pick — not to guess a filename.
    """
    req = urllib.request.Request(FALLBACK_MSI, method="HEAD",
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"installer not available (HTTP {r.status})")
    return FALLBACK_MSI


def download(url: str, dest: Path, on_progress=None) -> Path:
    """Fetch a jar to ``dest``, reporting progress.

    Written to a temporary name and moved into place only once complete, so an
    interrupted download can never be mistaken for a working install.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if on_progress:
                on_progress(got, total)

    if dest.suffix.lower() == ".jar":
        ok, why = validate(tmp)
        if not ok:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"downloaded file is not usable: {why}")
    elif tmp.stat().st_size < 100_000:
        # an installer this small is an error page, not a program
        tmp.unlink(missing_ok=True)
        raise RuntimeError("the download was too small to be an installer — "
                           "the link may have moved")
    tmp.replace(dest)
    return dest


def install_windows(msi: Path) -> None:
    """Hand the downloaded installer to Windows.

    Deliberately NOT silent. This is third-party software; the user should see
    its own installer, its licence and where it is going, and be able to say
    no. We fetched it, they install it.
    """
    import subprocess

    subprocess.Popen(["msiexec", "/i", str(msi)], close_fds=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


NOTICE = (
    "Commlink6 is a separate program by Stefan Prelle, distributed from "
    "rpgframework.de under his own terms. It is not part of this software and "
    "is not redistributed with it.\n\n"
    "It is optional. Your PDFs are read either way — Commlink6 adds the "
    "structure the printed page leaves implicit: how many accessories fit an "
    "item, what a quality hands over, what is inside a PACK."
)
