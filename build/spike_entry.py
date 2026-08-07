"""Phase-0 spike: does the pipeline survive being frozen?

Not a smoke test of imports — imports are the easy part. This does real work
with the pieces most likely to break under PyInstaller, and says which one
failed if any does:

* **PyMuPDF (fitz)** is a native extension shipping its own binaries. If it
  survives freezing at all, it survives here: the check opens a real PDF and
  counts pages.
* **pdfplumber / pdfminer** carry data files (CMaps, encodings) that a naive
  freeze leaves behind, and the failure only shows when a page with embedded
  fonts is read — not at import.
* **The jar reader** proves zipfile plus our XML parsing work from a bundle.
* **jsonschema** resolves ``$ref`` across files, which needs its own data.
* Our own package must be importable with its submodules intact.

Run frozen:  dist/sr6-spike/sr6-spike.exe [path-to-pdf]
Run direct:  python build/spike_entry.py  [path-to-pdf]
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import zipfile
from pathlib import Path

#: Running from source, `extractor` lives one level up and is not installed.
#: Frozen, PyInstaller has already put it on the path — inserting the repo root
#: there would be wrong, since the repo does not exist on a user's machine.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str):
    """Decorator: run a probe, record pass/fail, never let one abort the rest."""
    def wrap(fn):
        t0 = time.time()
        try:
            detail = fn() or "ok"
            RESULTS.append((name, True, f"{detail}  ({time.time() - t0:.2f}s)"))
        except Exception as e:
            RESULTS.append((name, False, f"{type(e).__name__}: {e}"))
            if "--traceback" in sys.argv:
                traceback.print_exc()
        return fn
    return wrap


def main() -> int:
    frozen = getattr(sys, "frozen", False)
    print(f"SR6 pipeline spike — {'FROZEN' if frozen else 'source'} "
          f"| python {sys.version.split()[0]}")
    if frozen:
        print(f"bundle: {Path(sys.executable).parent}")
    print()

    pdf = None
    for a in sys.argv[1:]:
        if a.lower().endswith(".pdf") and Path(a).is_file():
            pdf = Path(a)
            break

    @check("import extractor")
    def _():
        import extractor
        return f"v{extractor.__version__}"

    @check("extractor submodules")
    def _():
        import extractor.chargen_xml, extractor.gear_meta  # noqa: F401
        import extractor.identity, extractor.ingest        # noqa: F401
        import extractor.ownership, extractor.packs_xml    # noqa: F401
        import extractor.reconcile                          # noqa: F401
        return "7 modules"

    @check("PyMuPDF (native)")
    def _():
        import fitz
        if not pdf:
            return f"{fitz.__doc__.strip().splitlines()[0]} (no PDF given)"
        with fitz.open(pdf) as doc:
            return f"opened {pdf.name}: {doc.page_count} pages"

    @check("pdfplumber text + chars")
    def _():
        import pdfplumber
        if not pdf:
            return "imported (no PDF given)"
        with pdfplumber.open(pdf) as d:
            page = d.pages[min(20, len(d.pages) - 1)]
            text = page.extract_text() or ""
            # chars exercise the font machinery, which is where a bad freeze bites
            return f"page {page.page_number}: {len(text)} chars, {len(page.chars)} glyphs"

    @check("layout engine (our xtable)")
    def _():
        from extractor.xtable import __name__ as _n  # noqa: F401
        return "importable"

    @check("Commlink6 jar reader")
    def _():
        from extractor.commlink6 import DEFAULT_JAR
        if not Path(DEFAULT_JAR).is_file():
            return "jar not installed (skipped)"
        from extractor.ownership import commlink6_books
        books = commlink6_books(Path(DEFAULT_JAR))
        return f"{len(books)} books, {sum(books.values())} items"

    @check("jsonschema $ref resolution")
    def _():
        import jsonschema
        from referencing import Registry  # noqa: F401
        return f"jsonschema {jsonschema.__version__}"

    @check("zipfile + XML")
    def _():
        import xml.etree.ElementTree as ET
        ET.fromstring("<a><b id='x'/></a>")
        return f"zipfile {zipfile.__name__} ok"

    width = max(len(n) for n, _, _ in RESULTS)
    for name, ok, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print()
    if failed:
        print(f"{len(failed)} FAILED: {', '.join(failed)}")
        return 1
    print(f"all {len(RESULTS)} checks passed"
          + ("" if pdf else "  (pass a PDF path for the full PDF checks)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
