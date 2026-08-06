# Scope — Shadowrun 6th World Catalog Builder (installer)

A signed Windows installer that takes someone with no command line, no Python
and no Node from "I own the PDFs" to "the catalog is in my Foundry world".

Decisions taken (2026-08-06): bundle the runtimes but **not** the Foundry
module; offer to **download Commlink6 on demand**; front it with a **desktop
app shell**.

---

## The two deliverables stay separate

| | Ships as | Contains |
|---|---|---|
| **Catalog Builder** | `SR6CatalogBuilder_Setup_v<x>.exe` — signed | The pipeline, the review app, and the runtimes to run them |
| **SR6 Forge** | `module.json` + `sr6-forge.zip` on a GitHub release | The Foundry module. Installed by pasting the manifest URL into Foundry. |

The module is deliberately not in the installer. It updates on Foundry's own
cadence, and a manifest URL is what Foundry users expect. The builder shows the
URL with a **Copy** button and a note to paste it into *Add-on Modules →
Install Module*.

Neither deliverable contains game data. The user's PDFs are their licence.

---

## What the user actually does

1. Run the installer. Next, next, install.
2. Launch **Shadowrun 6th World Catalog Builder**.
3. A first-run wizard, one question per screen:

   | Step | Ask | Behaviour |
   |---|---|---|
   | 1 | **Where are your PDFs?** | Browse to a folder. It scans, then lists what it recognised — *"Found: Core Rulebook, Sixth World Companion, Firing Squad"* — and names anything it could not identify. |
   | 2 | **Commlink6?** | *Download it for me* / *I already have it* (browse to the jar) / *Skip*. Explains in one line what it adds and that it is Stefan Prelle's software under his terms. |
   | 3 | **Where is Foundry?** | Auto-detects `%LOCALAPPDATA%\FoundryVTT\Data`; browse to override. |
   | 4 | **Import** | One button. Live progress, per-book log, cancellable. This is the long step and it must never look frozen. |
   | 5 | **Review** | Opens the existing web app in the default browser. Correct anything, add icons and art, approve. |
   | 6 | **Publish** | Builds the compendium packs and installs *Shadowrun 6th World Catalog* into Foundry. Ends with: enable it in your world, and here is the SR6 Forge manifest URL. |

Re-running lands on a dashboard instead: how many items, when it was last
imported, and buttons for *Import again*, *Review*, *Publish*.

---

## Build

```
build/
  catalog_builder/        the desktop shell (Tkinter)
  catalog_builder.spec    PyInstaller — one-folder, not one-file
  installer.iss           Inno Setup
  build_release.py        sync -> freeze -> stage node -> compile -> sign
```

**Shell: Tkinter.** In the standard library, so it freezes small and reliably,
and it matches the toolkit already used elsewhere in this ecosystem. The heavy
UI is the web app that already exists; the shell only has to ask four questions
and show a progress bar. A Qt or Electron shell would add more weight than the
whole rest of the bundle.

**One-folder, not one-file.** A one-file PyInstaller build unpacks ~300 MB to
temp on every launch, which is slow and a reliable way to get flagged by
antivirus. One-folder starts fast and lets Inno compress properly.

**Node ships embedded.** The official Windows zip from nodejs.org, plus
`site/` with `node_modules` **pre-installed at build time**. The user must
never see an `npm install`.

**Signing.** `C:\Users\johnb\Tools\CodeSignTool\sign.bat` (SSL.com eSigner) —
already on this machine and proven. Sign both the launcher exe and the final
installer; unsigned PyInstaller output draws SmartScreen warnings.

### Size, and the one decision that governs it

Measured on this machine:

| | |
|---|---|
| OpenCV (`cv2`) | **155 MB** |
| onnxruntime | **41 MB** |
| numpy | 34 MB |
| Pillow | 16 MB |
| `site/node_modules` | 66 MB |
| Node runtime | ~50 MB |
| pdfplumber / pymupdf | <1 MB |

Naively that is a **~360 MB** payload, most of it OpenCV and onnxruntime.

**Both are used only by `images_extract.py`** — art extraction and background
removal. The text pipeline never imports them. So:

- **Standard build** excludes them: roughly **130 MB**, perhaps 60–70 MB
  compressed. Full extraction, full review app, icon assignment from the local
  library. What is missing is automatic art lifting and background stripping.
- **Art support becomes an optional download** the app fetches on first use,
  with a plain explanation of what it enables.

This is the single biggest lever on whether the installer feels reasonable, and
it costs a feature most users will not miss on day one.

---

## Work breakdown

| Phase | Work | Est. |
|---|---|---|
| 0 | **Spike**: freeze the pipeline with PyInstaller, confirm pdfplumber/pymupdf survive, measure the real bundle | 0.5 d |
| 1 | Shell skeleton — window, wizard frames, settings persisted to `%APPDATA%` | 1 d |
| 2 | PDF folder scan + book identification, mapping to `data/books.json` | 0.5 d |
| 3 | Commlink6 download-on-demand, with checksum and a clear licence notice | 0.5 d |
| 4 | Import runner — subprocess, threaded, streamed log, progress, cancel | 1 d |
| 5 | Embedded Node staging; start/stop the review app; open the browser | 0.5 d |
| 6 | Publish — build packs, deploy to Foundry, show the manifest URL | 0.5 d |
| 7 | Inno script, shortcuts, uninstall, upgrade-in-place | 0.5 d |
| 8 | Signing wired into the build; SmartScreen check on a clean profile | 0.5 d |
| 9 | Optional art pack; first-run docs; test on a machine with no Python or Node | 1 d |

**≈ 6–7 focused days.** Phase 0 is the one that can move the estimate: if
PyInstaller fights pymupdf, phases 1–9 do not change but phase 0 grows.

---

## Risks, and what to do about them

**Antivirus false positives.** PyInstaller output is heuristically flagged
often. Signing is the mitigation, plus one-folder over one-file. Budget for a
reputation submission if it happens.

**Inno Setup is not installed on this machine.** Prerequisite before phase 7.

**Import is slow.** Extracting a full book is minutes, not seconds. The UI must
run it off-thread with a live log, or it will look hung and get killed.

**Foundry might be running during publish.** Compendium packs are LevelDB, and
Foundry holds a lock. Detect it and say "close Foundry first" rather than
failing on a permission error.

**Commlink6 may move or change.** Downloading from a third-party site is a
dependency on someone else's URL. Fail softly to *browse for it yourself*, and
never block the PDF pipeline on it.

**PDF variance.** Editions and printings differ, and the extractor will not be
perfect on every one. This is exactly why step 5 exists and why *Publish* is a
separate button — the review pass is the product, not a formality.

---

## Explicitly out of scope

macOS and Linux (Windows first), auto-update, publishing anyone else's data,
and bundling the SR6 Forge module.
