---
name: sr6-release
description: Build, sign, deliver and publish a SR6 Catalog Builder release. Use when the user asks to "cut a release", "rebuild and sign", "push a new installer", "bump the version and ship", or to refresh the installer on the desktop or GitHub.
---

# Releasing the SR6 Catalog Builder

Mechanical, repeated often, and easy to get subtly wrong. Two mistakes have
actually shipped: forgetting that the version lives in **two** files, and
breaking the build itself with a change that was never run.

## Before anything

Both suites must pass. Do not start a release on a red build.

```bash
python -m pytest tests/ -q
cd site && npx vitest run
```

## 1. Version — TWO files, and one of them is not obvious

`build/build_release.py::version()` reads **`foundry-module/sr6-forge/module.json`**,
not the installer script. The `.iss` value is only a fallback default. Bump
both or you ship an installer labelled with the previous version.

- `foundry-module/sr6-forge/module.json` → `"version"`
- `build/installer.iss` → `#define AppVersion`

Convention here: feature work is `+0.1.0`; a fix to a release that is already
out is `+0.0.1`. Ask which if it is not obvious — the user has asked for both.

## 2. Build and sign

```bash
python build/build_release.py
```

Five steps: build the review app (`npm run build` + `npm ci --omit=dev`),
freeze with PyInstaller, sign the exe, compile the installer, sign the
installer. Signing uses `C:\Users\johnb\Tools\CodeSignTool\sign.bat`.

If it fails in step 0, check `shutil.which("npm")` is still used — a bare
`"npm"` raises FileNotFoundError on Windows because `CreateProcess` ignores
PATHEXT. If it dies while PRINTING, `_utf8_console()` is missing.

## 3. Verify before delivering

Never hand over an installer you have not checked.

```bash
powershell -NoProfile -Command "(Get-AuthenticodeSignature 'export\dist\SR6CatalogBuilder_Setup_vX.Y.Z.exe').Status"
```

Must be `Valid`. Also confirm the review app's payload is really inside:

```bash
ls build/work/site-deps/node_modules/express/package.json   # runtime deps staged
ls site/dist/index.html                                      # front end built
```

## 4. Deliver to BOTH desktops

The active desktop is the OneDrive one, but copy to both — the user looks in
either. Always the same stable filename, so the shortcut they click is the
newest build:

```bash
for D in "/c/Users/johnb/OneDrive/Desktop" "/c/Users/johnb/Desktop"; do
  cp "export/dist/SR6CatalogBuilder_Setup_vX.Y.Z.exe" "$D/SR6 Catalog Builder Setup.exe"
done
```

## 5. Commit, tag, publish

```bash
git add -A && git commit    # say WHAT broke and WHY, not just what changed
git push origin main
git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z
gh release create vX.Y.Z \
  "export/dist/SR6CatalogBuilder_Setup_vX.Y.Z.exe#SR6 Catalog Builder Setup (signed)" \
  --title "SR6 Forge X.Y.Z" --notes-file <notes>
```

To refresh an asset **without** a version bump:
`gh release upload vX.Y.Z <exe> --clobber`

## 6. Tell the user what to watch

A release is not done when it uploads. Say what changed, what to look for on
the next run, and what is still open. If a fix is a hypothesis rather than a
proven cause, say so.

## Reminders that have each cost a rebuild

- **The user must close the app before installing.** Setup stops the review
  server itself, but the window holds its own files.
- **Do not publish anything containing game content.** `assert_no_books()`
  fails the build on a PDF in the freeze or a book path in the .iss. The
  bundled `creation-rules.json` carries short rulebook citations and is
  already public in the repo — check before adding anything new.
- **Clean test artefacts out of `build/dist/` first.** Copying `extractor/`
  or `tools/` there for a frozen test leaves them to be packaged twice.
