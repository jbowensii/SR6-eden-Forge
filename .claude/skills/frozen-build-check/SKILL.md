---
name: frozen-build-check
description: Verify a PyInstaller/Windows build against the failure modes that are invisible from source. Use before shipping an installer, or when the installed app misbehaves in a way that cannot be reproduced by running from the repo — spawned windows, silent phases, encoding crashes, missing icons.
---

# Checking a frozen build

Every item here shipped at least once in the SR6 Catalog Builder, and every one
**passed its tests from source**. From the repo `sys.executable` is python,
stdout is whatever the terminal says, and resources are read off disk — so the
whole class is invisible until the bundle runs on a real machine.

Rule of thumb: **if a change touches launching a process, writing to stdout,
or reading a resource, test the exe, not the source.**

## 1. Never hand a script path to `sys.executable`

In a bundle `sys.executable` IS the app exe. `[sys.executable, "-u", "x.py"]`
does not run `x.py` — the exe ignores unknown arguments, falls through to its
entry point and opens **another window**. Sixteen phases became sixteen
windows and sixteen no-ops.

```bash
grep -rn 'sys.executable' --include=*.py . | grep -v test
```

Anything frozen must dispatch by module through a marker argument
(`--run-pipeline <module>`). Check the dispatcher treats "module has no
`main()`" as SUCCESS — most pipeline scripts do their work at import.

## 2. Spawn re-imports the target's module

Windows has no fork. A worker function defined in a **script** makes every
child re-execute that script from the top, recursively.

- worker targets live in importable modules with no side effects
- any script that starts a pool has `if __name__ == "__main__":`
- `multiprocessing.freeze_support()` at every entry point

```bash
grep -rn "ProcessPoolExecutor\|multiprocessing" --include=*.py . | grep -v test
```

## 3. stdout is cp1252 and can kill the program

A frozen build gets a cp1252 stdout. Printing a box-drawing character, an em
dash, or a U+FFFD from `errors="replace"` decoding raises `UnicodeEncodeError`
and takes the run with it — after the work succeeded. Every entry point needs:

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

## 4. A child with no console has nowhere to inherit stdout

Subprocess output vanished entirely in the installed app. Capture it:
`Popen(stdout=PIPE, stderr=STDOUT)` and forward the lines yourself.

## 5. External tools need resolving

`"npm"` is `npm.cmd`; `CreateProcess` does not apply PATHEXT. Use
`shutil.which()` for anything not a bare .exe.

## The actual test — run the exe

Source tests cannot prove any of the above. Stage the pipeline beside the
built exe (directory junctions are instant; copying 156 MB is not), run one
real unit of work, and check BOTH that it did the work and that nothing
appeared on screen:

```bash
before=$(powershell -NoProfile -Command "@(Get-Process YourApp -EA 0).Count")
"build/dist/YourApp/YourApp.exe" --run-pipeline tools.some_phase --apply
after=$(powershell -NoProfile -Command "@(Get-Process YourApp -EA 0).Count")
# after must equal before, AND the phase's effect must be visible on disk
```

## Icons, if the app has them

- Pillow's default `.ico` save is PNG-compressed for every entry, and Windows
  only renders a PNG entry at 256x256 — use `bitmap_format="bmp"`.
- The shell caches "no icon" PER PATH, so a shortcut keeps the generic glyph
  after the exe is fixed. Point shortcuts at a separate `.ico` via
  `IconFilename`.
- To verify, enumerate `RT_GROUP_ICON` — do not byte-scan for bitmap headers,
  which matches any bundled image. Pass the ctypes callback params as
  `c_void_p`: with `LPCWSTR` it tries to read a string from an integer
  resource id and silently returns nothing.

## Reporting

If a fix here is a hypothesis rather than a proven cause, say which. Several
of these were found only because a run was instrumented first and the evidence
contradicted the obvious explanation.
