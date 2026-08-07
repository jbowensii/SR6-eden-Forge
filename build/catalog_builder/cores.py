"""Ask how many books to read at once, and say what the answer costs.

Reading is the slow part of an import and each book is read independently, so
books can be read several at a time -- one per worker process. Merging is
always one book at a time, in plan order, because every book merges into the
one shared library and Commlink6 rows must keep their precedence over anything
read off a page. This setting does not touch that.

The ceiling is MEMORY, not cores. A worker holds a whole PDF's extracted words
while it works; the single-process import was measured at roughly 3 GB resident
on the core rulebook. Sixteen of those would page a 32 GB machine into the
ground and finish slower than one. So the recommendation is whichever is
smaller: the cores you can spare, or the memory you have.
"""
from __future__ import annotations

import ctypes
import os

#: Peak resident memory to budget per worker, in GB. From measurement, not
#: guesswork: the one-process import peaked around 3 GB on the core rulebook.
GB_PER_WORKER = 3.0

#: Left free so the machine stays usable while an import runs.
CORES_HELD_BACK = 2


def total_ram_gb() -> float:
    """Installed RAM. Returns 0.0 if it cannot be determined."""
    try:
        class Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        s = Status()
        s.dwLength = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            return s.ullTotalPhys / (1024 ** 3)
    except Exception:
        pass
    return 0.0


def advise(cores: int | None = None, ram_gb: float | None = None) -> dict:
    """What to recommend, and the reason for it.

    :returns: ``{cores, ramGb, byCores, byMemory, recommended, limit, why}``
        where *limit* is the largest value the dialog offers.
    """
    cores = cores if cores is not None else (os.cpu_count() or 4)
    ram_gb = ram_gb if ram_gb is not None else total_ram_gb()

    by_cores = max(1, cores - CORES_HELD_BACK)
    # no memory reading -> do not pretend to know; fall back to cores alone
    by_memory = max(1, int(ram_gb // GB_PER_WORKER)) if ram_gb else by_cores

    recommended = max(1, min(by_cores, by_memory))
    why = ("your cores, less a couple left free" if by_cores <= by_memory
           else f"your memory — about {GB_PER_WORKER:.0f} GB per worker")

    return {"cores": cores, "ramGb": ram_gb, "byCores": by_cores,
            "byMemory": by_memory, "recommended": recommended,
            "limit": max(1, cores), "why": why}


def explain(a: dict) -> str:
    """The text shown in the dialog. Plain, and honest about the trade."""
    ram = f"{a['ramGb']:.0f} GB RAM" if a["ramGb"] else "unknown RAM"
    return (
        f"Reading the books is the slow part of an import, and each book is read "
        f"on its own — so several can be read at the same time, one per worker.\n\n"
        f"Merging is always done one book at a time, in order, so Commlink6 keeps "
        f"precedence over the printed page. This setting does not change that.\n\n"
        f"This machine: {a['cores']} logical processors, {ram}.\n"
        f"Recommended: {a['recommended']} — limited by {a['why']}.\n\n"
        f"More workers finish sooner, but each one holds a whole book in memory "
        f"while it works (about {GB_PER_WORKER:.0f} GB on a big one). Asking for "
        f"more than the memory allows makes an import slower, not faster.\n\n"
        f"Set it to 1 to read one book at a time, as before."
    )


def ask_workers(parent, settings) -> int | None:
    """Modal chooser. Returns the count, or None if the user backed out."""
    import tkinter as tk
    from tkinter import ttk

    a = advise()
    start = int(settings.get("workers") or 0) or a["recommended"]
    start = max(1, min(a["limit"], start))

    win = tk.Toplevel(parent)
    win.title("How many books at once?")
    win.transient(parent)
    win.resizable(False, False)

    frame = ttk.Frame(win, padding=16)
    frame.grid(sticky="nsew")

    ttk.Label(frame, text="Reading the books", font=("Segoe UI", 12, "bold")
              ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
    ttk.Label(frame, text=explain(a), wraplength=460, justify="left"
              ).grid(row=1, column=0, columnspan=3, sticky="w")

    chosen = tk.IntVar(value=start)
    row = ttk.Frame(frame)
    row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(14, 4))
    ttk.Label(row, text="Workers:").pack(side="left")
    spin = ttk.Spinbox(row, from_=1, to=a["limit"], textvariable=chosen, width=5)
    spin.pack(side="left", padx=(8, 12))
    ttk.Scale(row, from_=1, to=a["limit"], orient="horizontal", length=240,
              command=lambda v: chosen.set(int(float(v)))).pack(side="left")

    result: dict = {"value": None}

    def start_now():
        result["value"] = max(1, min(a["limit"], int(chosen.get() or 1)))
        settings["workers"] = result["value"]
        settings.save()
        win.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=0, columnspan=3, sticky="e", pady=(14, 0))
    ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(buttons, text="Start import", command=start_now
               ).pack(side="right", padx=(0, 8))

    win.bind("<Return>", lambda _e: start_now())
    win.bind("<Escape>", lambda _e: win.destroy())
    win.grab_set()
    spin.focus_set()
    parent.wait_window(win)
    return result["value"]
