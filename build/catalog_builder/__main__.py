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
import sys
from pathlib import Path

WORKER_FLAG = "--run-pipeline"


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
    _ensure_paths()

    if len(sys.argv) > 2 and sys.argv[1] == WORKER_FLAG:
        module_name = sys.argv[2]
        # the module parses sys.argv itself, so present the argv it expects
        sys.argv = [module_name, *sys.argv[3:]]
        mod = importlib.import_module(module_name)
        fn = getattr(mod, "main", None)
        if fn is None:
            print(f"{module_name} has no main()", file=sys.stderr)
            return 2
        result = fn()
        return 0 if result is None else int(result)

    return _load_app().main()


if __name__ == "__main__":
    sys.exit(main())
