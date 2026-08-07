"""Run a long job without freezing the window.

Extracting a book is minutes, not seconds. Run that on the UI thread and the
window stops repainting, Windows greys it out and titles it "Not Responding",
and a reasonable person kills it — losing the work and, worse, trusting the
program less next time. So every job runs in a worker thread, its output is
streamed back a line at a time, and there is always a way to stop it.

Frozen or from source, the same code has to launch the pipeline. Under
PyInstaller there is no ``python.exe`` to call and no ``tools/`` on disk, so a
frozen build re-invokes *itself* with a marker argument and the bundled
interpreter runs the pipeline in-process. From source it shells out to the
current interpreter. :func:`pipeline_command` hides the difference.
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

#: argv marker a frozen build uses to run a pipeline entry point in-process
WORKER_FLAG = "--run-pipeline"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def pipeline_command(module: str, args: list[str]) -> list[str]:
    """The command line that runs one pipeline entry point.

    :param module: dotted path, e.g. ``tools.import_library``
    """
    if is_frozen():
        return [sys.executable, WORKER_FLAG, module, *args]
    return [sys.executable, "-m", module, *args]


@dataclass
class Job:
    """A running command, its output, and the means to stop it."""

    argv: list[str]
    cwd: Path | None = None
    env: dict | None = None
    lines: queue.Queue = field(default_factory=queue.Queue)
    returncode: int | None = None
    _proc: subprocess.Popen | None = None
    _thread: threading.Thread | None = None
    _cancelled: bool = False

    def start(self) -> "Job":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        env = {**os.environ, **(self.env or {})}
        # unbuffered, or the log arrives in one lump when the job ends
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            self._proc = subprocess.Popen(
                self.argv, cwd=str(self.cwd) if self.cwd else None, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            self.lines.put(f"!! could not start: {e}")
            self.returncode = 127
            self.lines.put(None)
            return

        for line in self._proc.stdout:            # streams as it arrives
            self.lines.put(line.rstrip("\r\n"))
        self._proc.wait()
        self.returncode = -1 if self._cancelled else self._proc.returncode
        self.lines.put(None)                      # sentinel: no more output

    def cancel(self) -> None:
        """Stop the job. Terminate first; kill only if it will not go."""
        self._cancelled = True
        p = self._proc
        if not p or p.poll() is not None:
            return
        try:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        except Exception:
            pass

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def drain(self, limit: int = 200):
        """Pull what has arrived since last time. Never blocks.

        :returns: ``(lines, finished)``
        """
        out, done = [], False
        for _ in range(limit):
            try:
                item = self.lines.get_nowait()
            except queue.Empty:
                break
            if item is None:
                done = True
                break
            out.append(item)
        return out, done


#: The import's per-book marker: "[3/47] street_grimoire reading|done ..."
_STEP = re.compile(r"\[(\d+)/(\d+)\]\s+(\S+)\s+(.*)")


class Progress:
    """Turn pipeline chatter into a number, without pretending to precision.

    The import prints a marker when it starts a book and another when that book
    finishes. Reading those is honest and needs no guesswork; a fabricated
    smooth percentage would only be a lie told slowly.

    Both markers matter. Reading the finish alone leaves the bar and the label
    frozen for the several minutes a book takes, which is indistinguishable
    from a hang — so the start marker moves the label, and only the finish
    moves the bar.
    """

    #: How the bar splits between the two phases. Reading is the long pole even
    #: with every core busy; merging is mostly bookkeeping.
    READ_SHARE = 0.8

    def __init__(self, total_books: int):
        self.total = max(1, total_books)
        self.read = 0
        self.done = 0
        self.current = ""
        self.phase = ""

    def feed(self, line: str) -> None:
        # reading  (in parallel): "[3/47] street_grimoire read  212 pages"
        # merging  (in order):    "[3/47] street_grimoire merging"
        #                         "[3/47] street_grimoire done  +pdf new=12"
        m = _STEP.match(line.strip())
        if not m:
            return
        idx, total, book, what = int(m[1]), int(m[2]), m[3], m[4]
        # The pipeline counts the books it will actually process; we only
        # counted the ones the scan matched, and the two differ whenever a book
        # is skipped for want of a PDF. Its number is the true one.
        self.total = max(1, total)
        self.current = book
        if what.startswith("read"):
            # books finish reading out of order, so idx is a completion count
            self.phase = "reading"
            self.read = max(self.read, idx)
        elif what.startswith("done"):
            self.phase = "merging"
            self.done = max(self.done, idx)
        else:
            self.phase = "merging"

    @property
    def fraction(self) -> float:
        return (self.READ_SHARE * (self.read / self.total)
                + (1 - self.READ_SHARE) * (self.done / self.total))

    def label(self) -> str:
        if not self.current:
            return "starting"
        if self.done >= self.total:
            return "finishing up"
        n = self.read if self.phase == "reading" else self.done
        return f"{self.current} — {self.phase}  ({n}/{self.total})"
