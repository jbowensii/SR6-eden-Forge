"""Entry point, for both halves of a frozen build.

A PyInstaller bundle has one executable but needs to do two jobs: show the
window, and run a pipeline step as a subprocess. There is no ``python.exe`` in
the bundle to call and no ``tools/`` on disk to point at, so the exe re-invokes
itself with a marker argument and dispatches to the requested module here.

    SR6CatalogBuilder.exe                                  -> the window
    SR6CatalogBuilder.exe --run-pipeline tools.import_library --apply
                                                           -> that module's main()

**No relative imports here.** PyInstaller runs the entry script as ``__main__``
with no package context, so ``from .app import ...`` raises "attempted relative
import with no known parent package" — and it does so only in the frozen build,
because from source this file is reached as ``catalog_builder.__main__`` where
the package *is* known. Absolute imports work in both.

Running the work in a child process rather than a thread is deliberate: a child
can be cancelled by terminating it, and a crash inside it cannot take the
window down with it.
"""
from __future__ import annotations

import importlib
import multiprocessing
import runpy
import sys
from pathlib import Path

WORKER_FLAG = "--run-pipeline"


def _utf8_console() -> None:
    """Make stdout survive anything a phase prints.

    Windows hands a frozen build a cp1252 stdout. Phase output is decoded with
    errors="replace", so it can contain U+FFFD, and printing that to cp1252
    raises UnicodeEncodeError — which killed an import at phase 4 AFTER three
    phases of real work. Reconfiguring with errors="replace" means an
    unencodable character degrades to a question mark instead of ending the run.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _ensure_paths() -> None:
    """Make both the package and the pipeline importable, frozen or not."""
    here = Path(__file__).resolve().parent          # .../build/catalog_builder
    for p in (here.parent, here.parent.parent):     # build/, repo root
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
    if getattr(sys, "frozen", False):
        # beside the exe, where the installer puts extractor/ and tools/
        bundle = Path(sys.executable).parent
        if str(bundle) not in sys.path:
            sys.path.insert(0, str(bundle))


def _load_app():
    """Import the window, whichever name the package ended up under."""
    last = None
    for name in ("catalog_builder.app", "build.catalog_builder.app"):
        try:
            return importlib.import_module(name)
        except ImportError as e:
            last = e
    raise last or ImportError("cannot locate catalog_builder.app")


def main() -> int:
    _utf8_console()
    _ensure_paths()

    if len(sys.argv) > 2 and sys.argv[1] == WORKER_FLAG:
        module_name = sys.argv[2]
        # the module parses sys.argv itself, so present the argv it expects
        sys.argv = [module_name, *sys.argv[3:]]
        # runpy, not import.
        #
        # A phase runs its work in one of two ways: top-level code, or a main()
        # under `if __name__ == "__main__"`. Importing the module only fires
        # the first. Three phases had a guard and no main(), so importing them
        # did NOTHING -- and because "no main()" was treated as success they
        # exited 0 in silence. That is the whole of "Gap 2": the new-types,
        # content and vehicle phases never ran in an installed build.
        #
        # run_module with run_name="__main__" executes the module exactly as
        # `python -m module` does: top-level code runs AND the guard fires. It
        # satisfies both shapes, so a phase cannot be silently skipped for
        # having structured itself the other way.
        try:
            runpy.run_module(module_name, run_name="__main__", alter_sys=True)
        except SystemExit as e:
            return 0 if e.code in (None, 0) else int(e.code)
        return 0

    return _load_app().main()


if __name__ == "__main__":
    # MUST be the first thing that runs, before anything touches sys.argv.
    #
    # The import reads several books at once in worker processes, and on
    # Windows a worker is started by re-executing this program. In a frozen
    # build that means re-running THIS exe: without freeze_support() each
    # worker would fall through to main() and open another copy of the window,
    # which would start its own workers, and so on until the machine gives up.
    # freeze_support() spots the re-exec, runs the worker, and exits.
    multiprocessing.freeze_support()
    sys.exit(main())
