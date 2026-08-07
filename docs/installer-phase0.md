# Phase 0 — PyInstaller spike: results

**The pipeline freezes. The estimate holds. Build phase 1.**

```
  PASS  import extractor            v0.5.0
  PASS  extractor submodules        7 modules
  PASS  PyMuPDF (native)            opened corebook: 322 pages
  PASS  pdfplumber text + chars     page 21: 5426 chars, 5395 glyphs
  PASS  layout engine (our xtable)  importable
  PASS  Commlink6 jar reader        33 books, 3481 items
  PASS  jsonschema $ref resolution  jsonschema 4.26.0
  PASS  zipfile + XML               ok
```

Frozen, and again with `env -i` — no `PATH`, no `PYTHONPATH`, no `PYTHONHOME` —
which is the closest proxy available here for a machine with no Python at all.

Reproduce:

```bash
python -m PyInstaller build/spike.spec --noconfirm \
    --distpath build/dist --workpath build/work
build/dist/sr6-spike/sr6-spike.exe "<path-to-a-book.pdf>"
```

## Size

| | |
|---|---|
| On disk | **144 MB**, 369 files |
| Compressed | **69.2 MB** — the download |

The scope estimated ~130 MB and 60–70 MB compressed. Close enough to plan on.

Largest contributors:

| | |
|---|---|
| pymupdf | 37 MB |
| numpy.libs (OpenBLAS) | 21 MB |
| Pillow | 13 MB |
| cryptography | 8.9 MB |
| pdfminer | 7.9 MB |
| pypdfium2_raw | 6.9 MB |
| lxml | 6.9 MB |

Excludes confirmed absent from the bundle: **cv2, onnxruntime, torch, pandas,
matplotlib, tkinter**. That is the ~200 MB the scope predicted could come out,
and it did — OpenCV and onnxruntime are reachable only from
`images_extract.py`, verified by loading the ingest chain and inspecting
`sys.modules`. Art support becomes an optional download, as planned.

(A grep for "scipy" hits `libscipy_openblas64_*.dll` inside `numpy.libs`. That
is numpy's own BLAS, not scipy.)

## The one real finding

A default freeze **succeeds and then fails at runtime**:

```
ModuleNotFoundError: No module named '81d243bd2c585b0f4821__mypyc'
```

`charset-normalizer` 3.4.5 ships a mypyc-compiled extension whose module name
is a bare content hash. Nothing imports that name in source, so PyInstaller's
static analysis never sees it, the build reports success, and the failure only
appears when pdfminer decodes a page and asks charset-normalizer to sniff an
encoding. Import-level smoke tests do not catch it — which is exactly why the
spike does real work on a real PDF rather than just importing.

Fixed in `build/spike.spec` by scanning site-packages for `*__mypyc*.pyd` and
adding what it finds as binaries plus hidden imports. Deliberately a scan and
not a hardcoded hash: the hash changes with every charset-normalizer release,
and hardcoding it would break silently on the next upgrade — in exactly the
same runtime-only way.

`chardet` ships mypyc modules too, under `chardet/pipeline/`. The same scan
covers them.

## What this settles

**Estimate stands at 6–7 days.** Phase 0 was the risk, and it came in at well
under its half-day allowance with one solvable problem.

Decisions now backed by measurement rather than guesswork:

- One-folder confirmed. Startup is immediate; a one-file build would unpack
  144 MB to temp on every launch.
- The exclusion strategy works and is worth ~200 MB.
- 69 MB is a reasonable download, so bundling the runtimes stays the right call.

## Trims available if 69 MB proves too much

Not taken — each costs either capability or confidence, and none is needed yet:

- **numpy + OpenBLAS (~28 MB)** — pulled in via Pillow/pdfplumber. Dropping it
  needs proof that no text path touches an array.
- **pypdfium2_raw (6.9 MB)** — pdfplumber's renderer, used for page images
  rather than text.
- **cryptography (8.9 MB)** — pdfminer needs it for encrypted PDFs. Some
  publisher PDFs are encrypted, so this stays.

Roughly 100 MB uncompressed looks reachable, at the cost of testing every one
of those assumptions against real books.

## Next

Phase 1: the Tkinter shell — window, wizard frames, settings in `%APPDATA%`.
Note that `tkinter` is currently in the exclude list because the spike has no
UI; phase 1 removes it.
