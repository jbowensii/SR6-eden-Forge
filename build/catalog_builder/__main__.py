"""Entry point, for both halves of a frozen build.

A PyInstaller bundle has one executable but needs to do two jobs: show the
window, and run a pipeline step as a subprocess. There is no ``python.exe`` in
the bundle to call and no ``tools/`` on disk to point at, so the exe re-invokes
itself with a marker argument and dispatches to the requested module here.

    SR6CatalogBuilder.exe                                  -> the window
    SR6CatalogBuilder.exe --run-pipeline tools.import_library --apply
                                                           -> that module's main()

Running the work in a child process rather than a thread is deliberate. The
pipeline is long, chatty and occasionally fatal; a child can be cancelled by
terminating it, and a crash inside it cannot take the window down with it.
"""
from __future__ import annotations

import importlib
import sys

WORKER_FLAG = "--run-pipeline"


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == WORKER_FLAG:
        module_name = sys.argv[2]
        # the module parses sys.argv itself, so present it the argv it expects
        sys.argv = [module_name, *sys.argv[3:]]
        mod = importlib.import_module(module_name)
        fn = getattr(mod, "main", None)
        if fn is None:
            print(f"{module_name} has no main()", file=sys.stderr)
            return 2
        result = fn()
        return 0 if result is None else int(result)

    from .app import main as gui
    return gui()


if __name__ == "__main__":
    sys.exit(main())
