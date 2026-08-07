"""Which port the review app should use, and whether it actually came up.

The launcher used to hard-code 8347 and open the browser 1.5 seconds after
starting node, whether or not node was still alive. When the server died on a
missing dependency the result was a browser tab pointed at nothing and no
explanation anywhere — which is exactly how it failed in the field.

So two things live here: choosing a port that is genuinely free, and waiting
for the server to answer before sending anyone to it.
"""
from __future__ import annotations

import socket

DEFAULT_PORT = 8347

#: Ports below this are privileged or well-known; above it is ephemeral space
#: that Windows hands out to outgoing connections.
MIN_PORT, MAX_PORT = 1024, 65535


def is_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """Is something already answering there?"""
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def is_free(port: int, host: str = "127.0.0.1") -> bool:
    """Can we bind it? Distinct from :func:`is_listening` — a port can be
    unavailable without anything accepting connections on it.

    Deliberately WITHOUT SO_REUSEADDR. On Windows that option permits binding
    a port another socket already holds, so setting it here made every busy
    port report as free — the precise opposite of the question being asked.
    (On Linux it only relaxes the TIME_WAIT rule, which is why the mistake is
    easy to make and invisible until it is tested on Windows.)
    """
    try:
        with socket.socket() as s:
            s.bind((host, port))
        return True
    except OSError:
        return False


def next_free(start: int = DEFAULT_PORT, tries: int = 50) -> int:
    """The first free port at or after ``start``. Falls back to ``start``."""
    for p in range(max(MIN_PORT, start), min(MAX_PORT, start + tries) + 1):
        if is_free(p):
            return p
    return start


def describe(port: int) -> tuple[str, str]:
    """``(state, sentence)`` for the chosen port: ok / busy / taken."""
    if is_listening(port):
        return "busy", (f"Something is already answering on {port} — most "
                        f"likely the review app from an earlier run. It will "
                        f"be reused rather than started again.")
    if not is_free(port):
        return "taken", (f"Port {port} is in use by another program and cannot "
                         f"be bound. Try {next_free(port + 1)}.")
    return "ok", f"Port {port} is free."


def wait_until_up(port: int, seconds: float = 20.0, step: float = 0.4,
                  still_running=None) -> bool:
    """Block until the server answers, or give up.

    :param still_running: optional callable; if it returns False the wait ends
        early, because a dead process is never going to start listening.
    """
    waited = 0.0
    while waited < seconds:
        if is_listening(port):
            return True
        if still_running is not None and not still_running():
            return False
        import time

        time.sleep(step)
        waited += step
    return is_listening(port)


def ask_port(parent, settings) -> int | None:
    """Small chooser. Returns the port, or None if the user backed out."""
    import tkinter as tk
    from tkinter import ttk

    try:
        from catalog_builder import theme
    except ImportError:
        from build.catalog_builder import theme
    pal = theme.palette()

    start = int(settings.get("reviewPort") or 0) or DEFAULT_PORT
    if not is_listening(start) and not is_free(start):
        start = next_free(start + 1)

    win = tk.Toplevel(parent)
    win.title("Review app port")
    win.transient(parent)
    win.resizable(False, False)
    win.configure(bg=pal["bg"])

    frame = ttk.Frame(win, padding=16)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text="Review app", style="Head.TLabel",
              font=("Segoe UI Semibold", 12)).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
    ttk.Label(frame, justify="left", wraplength=430,
              text="The review app runs a small web server on this machine and "
                   "opens it in your browser. It listens on localhost only — "
                   "nothing is exposed to the network.\n\n"
                   "Change the port if something else already uses this one."
              ).grid(row=1, column=0, columnspan=3, sticky="w")

    chosen = tk.IntVar(value=start)
    row = ttk.Frame(frame)
    row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(14, 4))
    ttk.Label(row, text="Port:").pack(side="left")
    spin = ttk.Spinbox(row, from_=MIN_PORT, to=MAX_PORT, textvariable=chosen,
                       width=8)
    spin.pack(side="left", padx=(8, 12))

    status = ttk.Label(frame, text="", style="Hint.TLabel", wraplength=430,
                       justify="left")
    status.grid(row=3, column=0, columnspan=3, sticky="w")

    colour = {"ok": pal["ok"], "busy": pal["warn"], "taken": pal["bad"]}

    def recheck(*_a):
        try:
            p = int(chosen.get())
        except (tk.TclError, ValueError):
            status.configure(text="Enter a number.", foreground=pal["bad"])
            return
        if not (MIN_PORT <= p <= MAX_PORT):
            status.configure(text=f"Pick a port between {MIN_PORT} and {MAX_PORT}.",
                             foreground=pal["bad"])
            return
        state, sentence = describe(p)
        status.configure(text=sentence, foreground=colour[state])

    chosen.trace_add("write", recheck)
    recheck()

    result: dict = {"value": None}

    def go():
        try:
            p = int(chosen.get())
        except (tk.TclError, ValueError):
            return
        if not (MIN_PORT <= p <= MAX_PORT) or describe(p)[0] == "taken":
            return                      # the status line already says why
        result["value"] = p
        settings["reviewPort"] = p
        settings.save()
        win.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(14, 0))
    ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(buttons, text="Open review app", command=go,
               style="Go.TButton").pack(side="right", padx=(0, 8))

    win.bind("<Return>", lambda _e: go())
    win.bind("<Escape>", lambda _e: win.destroy())
    win.update_idletasks()
    win.geometry(f"+{parent.winfo_rootx() + 60}+{parent.winfo_rooty() + 90}")
    win.grab_set()
    spin.focus_set()
    parent.wait_window(win)
    return result["value"]
