"""Shadowrun 6th World Catalog Builder — the window.

Four questions, then three buttons. Nothing here computes anything: every step
delegates to the pipeline modules and spends its own effort on saying clearly
what is happening and what to do next.

Tkinter, deliberately. The heavy interface is the review app that already
exists in a browser; this only has to ask where things are and show a progress
bar, and Tk is in the standard library — no wheel to freeze, nothing to go
stale. A Qt or Electron shell would outweigh the entire rest of the bundle.

Long work never runs on the UI thread. See runner.Job.
"""
from __future__ import annotations

import sys
import tempfile
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Absolute, not relative. A frozen entry script has no package context, and a
# relative import there fails only in the packaged build — the worst place to
# find out. See __main__.py.
try:
    from catalog_builder import books, commlink6, publish
    from catalog_builder.runner import Job, Progress, pipeline_command
    from catalog_builder.settings import (
        Settings, default_workspace, detect_commlink6, detect_foundry_data,
        ensure_workspace)
except ImportError:                       # installed under a different root
    from build.catalog_builder import books, commlink6, publish
    from build.catalog_builder.runner import Job, Progress, pipeline_command
    from build.catalog_builder.settings import (
        Settings, default_workspace, detect_commlink6, detect_foundry_data,
        ensure_workspace)

APP_TITLE = "Shadowrun 6th World Catalog Builder"
#: a blank line inside a message box
NL2 = chr(10) + chr(10)
REVIEW_URL = "http://localhost:8347"

BG = "#11141c"
FG = "#c8cede"
ACCENT = "#2fd4d9"
MUTED = "#5d6678"
OK = "#5ad48a"
WARN = "#e0a33e"
BAD = "#c4183c"


def repo_root() -> Path:
    """Where the pipeline lives — beside the exe when frozen, else the repo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("880x620")
        self.minsize(760, 560)
        self.configure(bg=BG)

        self._set_window_icon()
        self.settings = Settings()
        self.job: Job | None = None
        self.progress: Progress | None = None
        self.scan_result: dict | None = None

        self._style()
        self._build()
        self._prefill()
        self._refresh_state()

    def _set_window_icon(self) -> None:
        """Give the window our icon.

        Tk draws its own feather in the title bar and the taskbar regardless of
        what icon the executable carries — the exe icon covers Explorer, this
        covers the running window. Two different things, and only fixing one
        leaves the other looking like a stray Python script.
        """
        for base in (Path(getattr(sys, "_MEIPASS", "")),
                     Path(sys.executable).parent,
                     Path(__file__).resolve().parent.parent):
            ico = base / "app.ico"
            if ico.is_file():
                try:
                    self.iconbitmap(default=str(ico))
                    return
                except tk.TclError:
                    continue

    # ---------- chrome ----------
    def _style(self) -> None:
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background=BG, foreground=FG, fieldbackground="#181c26",
                    borderwidth=0, focuscolor=ACCENT)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Head.TLabel", foreground=ACCENT,
                    font=("Segoe UI Semibold", 11))
        s.configure("Hint.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        s.configure("TButton", background="#1d2230", foreground=FG, padding=(12, 6))
        s.map("TButton", background=[("active", "#28304a")])
        s.configure("Go.TButton", background=ACCENT, foreground="#08111a",
                    font=("Segoe UI Semibold", 10), padding=(16, 8))
        s.map("Go.TButton", background=[("active", "#5ce8ec")])
        s.configure("TEntry", fieldbackground="#181c26", foreground=FG,
                    insertcolor=FG, padding=6)
        s.configure("TProgressbar", background=ACCENT, troughcolor="#181c26")

    def _row(self, parent, label, hint, key, browse, row, extra=None):
        ttk.Label(parent, text=label, style="Head.TLabel").grid(
            row=row, column=0, sticky="w", pady=(12, 0))
        ttk.Label(parent, text=hint, style="Hint.TLabel").grid(
            row=row + 1, column=0, columnspan=3, sticky="w")
        var = tk.StringVar()
        ent = ttk.Entry(parent, textvariable=var)
        ent.grid(row=row + 2, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(parent, text="Browse…", command=browse).grid(
            row=row + 2, column=1, padx=(8, 0), pady=(4, 0))
        if extra:
            ttk.Button(parent, text=extra[0], command=extra[1]).grid(
                row=row + 2, column=2, padx=(8, 0), pady=(4, 0))
        status = ttk.Label(parent, text="", style="Hint.TLabel")
        status.grid(row=row + 3, column=0, columnspan=3, sticky="w")
        setattr(self, f"{key}_var", var)
        setattr(self, f"{key}_status", status)
        return var

    def _build(self) -> None:
        pad = ttk.Frame(self, padding=18)
        pad.pack(fill="both", expand=True)
        pad.columnconfigure(0, weight=1)

        ttk.Label(pad, text=APP_TITLE,
                  font=("Segoe UI Semibold", 15)).grid(row=0, column=0, sticky="w")
        ttk.Label(pad, style="Hint.TLabel",
                  text="Turn the Shadowrun PDFs you own into a Foundry VTT "
                       "compendium.").grid(row=1, column=0, sticky="w")

        form = ttk.Frame(pad)
        form.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        form.columnconfigure(0, weight=1)

        self._row(form, "1.  Where are your PDFs?",
                  "The folder holding your Shadowrun 6 books. Subfolders are "
                  "searched too.",
                  "pdf", self._pick_pdfs, 0)
        self._row(form, "2.  Commlink6  (optional)",
                  "Adds structure the printed page leaves implicit. Leave empty "
                  "to skip.",
                  "jar", self._pick_jar, 4, extra=("Get it…", self._get_commlink6))
        self._row(form, "3.  Where is Foundry?",
                  "Foundry's Data folder — the one containing 'modules' and "
                  "'worlds'.",
                  "foundry", self._pick_foundry, 8)
        self._row(form, "4.  Working folder",
                  "Where the extracted library and the built catalog are kept.",
                  "workspace", self._pick_workspace, 12)

        bar = ttk.Frame(pad)
        bar.grid(row=3, column=0, sticky="ew", pady=(16, 6))
        self.import_btn = ttk.Button(bar, text="Import books", style="Go.TButton",
                                     command=self._import)
        self.import_btn.pack(side="left")
        self.review_btn = ttk.Button(bar, text="Review & correct",
                                     command=self._review)
        self.review_btn.pack(side="left", padx=8)
        self.publish_btn = ttk.Button(bar, text="Publish to Foundry",
                                      command=self._publish)
        self.publish_btn.pack(side="left")
        self.cancel_btn = ttk.Button(bar, text="Stop", command=self._cancel)
        self.cancel_btn.pack(side="right")

        self.pbar = ttk.Progressbar(pad, mode="determinate", maximum=1000)
        self.pbar.grid(row=4, column=0, sticky="ew")
        self.stage = ttk.Label(pad, text="Ready.", style="Hint.TLabel")
        self.stage.grid(row=5, column=0, sticky="w", pady=(2, 6))

        self.log = tk.Text(pad, height=12, bg="#0c0f16", fg="#9aa4bb",
                           insertbackground=FG, relief="flat", wrap="none",
                           font=("Consolas", 9))
        self.log.grid(row=6, column=0, sticky="nsew")
        pad.rowconfigure(6, weight=1)
        sb = ttk.Scrollbar(pad, command=self.log.yview)
        sb.grid(row=6, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set, state="disabled")

    # ---------- state ----------
    def _prefill(self) -> None:
        s = self.settings
        self.pdf_var.set(s["pdfFolder"])
        self.jar_var.set(s["commlink6Jar"] or str(detect_commlink6() or ""))
        self.foundry_var.set(s["foundryData"] or str(detect_foundry_data() or ""))
        self.workspace_var.set(s["workspace"] or str(default_workspace()))
        for v in (self.pdf_var, self.jar_var, self.foundry_var, self.workspace_var):
            v.trace_add("write", lambda *_: self._refresh_state())

    def _save(self) -> None:
        s = self.settings
        s["pdfFolder"] = self.pdf_var.get().strip()
        s["commlink6Jar"] = self.jar_var.get().strip()
        s["foundryData"] = self.foundry_var.get().strip()
        s["workspace"] = self.workspace_var.get().strip()
        s.save()

    def _refresh_state(self) -> None:
        """Say what each answer means, before anything is run."""
        pdf = Path(self.pdf_var.get().strip() or ".")
        if self.pdf_var.get().strip() and pdf.is_dir():
            reg = books.load_registry(repo_root())
            self.scan_result = books.scan(pdf, reg)
            n = len(self.scan_result["matched"])
            self.pdf_status.configure(
                text=books.summary(self.scan_result),
                foreground=OK if n else WARN)
        else:
            self.scan_result = None
            self.pdf_status.configure(text="No folder chosen.", foreground=MUTED)

        jar = self.jar_var.get().strip()
        if jar:
            ok, why = commlink6.validate(Path(jar))
            self.jar_status.configure(
                text=f"Commlink6: {why}" if ok else f"Not usable — {why}",
                foreground=OK if ok else BAD)
        else:
            self.jar_status.configure(
                text="Not set — PDFs will be read on their own.", foreground=MUTED)

        fd = self.foundry_var.get().strip()
        if fd:
            ok, why = publish.check(Path(fd))
            self.foundry_status.configure(text=why or "Found.",
                                          foreground=OK if ok else WARN)
        else:
            self.foundry_status.configure(text="Not set.", foreground=MUTED)

        ws = self.workspace_var.get().strip()
        if ws:
            # icons/ and art/ are created here rather than asked about — there
            # is only one sensible answer, so a question would be noise
            try:
                ensure_workspace(Path(ws))
                self.workspace_status.configure(
                    text=f"{ws}   (data, export, icons, art created)",
                    foreground=MUTED)
            except OSError as e:
                self.workspace_status.configure(
                    text=f"Cannot create folders there — {e.strerror}", foreground=BAD)
        else:
            self.workspace_status.configure(text="Not set.", foreground=MUTED)

        busy = bool(self.job and self.job.running)
        self.import_btn.configure(state="disabled" if busy else "normal")
        self.publish_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    # ---------- pickers ----------
    def _pick_pdfs(self):
        d = filedialog.askdirectory(title="Folder containing your Shadowrun PDFs")
        if d:
            self.pdf_var.set(d)
            self._save()

    def _pick_jar(self):
        f = filedialog.askopenfilename(title="Commlink6 jar",
                                       filetypes=[("Jar", "*.jar")])
        if f:
            self.jar_var.set(f)
            self._save()

    def _get_commlink6(self):
        """Find Commlink6, or download the author's installer and run it.

        Detection first: most people who have it already have it, and asking
        them to download it again would be daft.

        Failing that, this fetches the installer from rpgframework.de and hands
        it to Windows — NOT silently. It is someone else's software; they should
        see its own installer, its terms and where it is going, and be able to
        decline. We do the fetching, they do the installing.

        If the link has moved, the download page opens instead. Guessing a
        filename would produce a 404 the user would fairly blame on us.
        """
        found = commlink6.find_local()
        if found:
            self.jar_var.set(str(found))
            self._save()
            ok, why = commlink6.validate(found)
            messagebox.showinfo(
                APP_TITLE,
                "Commlink6 is already installed:" + NL2 + str(found)
                + NL2 + ("Looks good — " + why if ok else "But: " + why))
            return

        if not messagebox.askokcancel(
                APP_TITLE,
                commlink6.NOTICE + NL2
                + "Download the installer from rpgframework.de and run it?",
                icon="question"):
            return

        self._write("=== fetching Commlink6 from rpgframework.de")
        self.stage.configure(text="Downloading Commlink6…")
        try:
            url = commlink6.latest_windows_url()
        except Exception as e:
            self._write(f"!! could not reach the installer: {e}")
            if messagebox.askokcancel(
                    APP_TITLE,
                    "That download link is no longer valid — the author has "
                    "probably published a new version." + NL2
                    + "Open the download page so you can pick it up there?"):
                webbrowser.open(commlink6.DOWNLOAD_PAGE)
            return

        dest = Path(tempfile.gettempdir()) / Path(url).name
        self._c6_job = threading.Thread(
            target=self._fetch_commlink6, args=(url, dest), daemon=True)
        self._c6_job.start()

    def _fetch_commlink6(self, url: str, dest: Path) -> None:
        """Download off the UI thread, then offer to run the installer."""
        def progress(got, total):
            if total:
                self.after(0, lambda: self.stage.configure(
                    text=f"Downloading Commlink6… {got * 100 // total}%"))

        try:
            commlink6.download(url, dest, on_progress=progress)
        except Exception as e:
            self.after(0, lambda: self._write(f"!! download failed: {e}"))
            self.after(0, lambda: self.stage.configure(text="Download failed."))
            return

        def done():
            self._write(f"=== downloaded {dest.name}")
            self.stage.configure(text="Ready.")
            if messagebox.askokcancel(
                    APP_TITLE,
                    "Downloaded." + NL2 + str(dest) + NL2
                    + "Run the installer now? Commlink6 will ask its own "
                      "questions. When it has finished, press 'Get it…' again "
                      "and the jar will be found automatically."):
                commlink6.install_windows(dest)
                self._write("=== Commlink6 installer started")
        self.after(0, done)

    def _pick_foundry(self):
        d = filedialog.askdirectory(title="Foundry VTT Data folder")
        if d:
            self.foundry_var.set(d)
            self._save()

    def _pick_workspace(self):
        d = filedialog.askdirectory(title="Working folder")
        if d:
            self.workspace_var.set(d)
            self._save()

    # ---------- log ----------
    def _write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------- actions ----------
    def _import(self):
        if not self.scan_result or not self.scan_result["matched"]:
            messagebox.showwarning(
                APP_TITLE, "No Shadowrun books found in that folder.\n\n"
                "Point step 1 at the folder holding your PDFs.")
            return
        self._save()
        ws = ensure_workspace(self.workspace_var.get().strip() or default_workspace())

        n = len(self.scan_result["matched"])
        self._write(f"=== importing {n} book(s) into {ws}")

        # The registry, with the matched PDF paths filled in, written INTO the
        # workspace the pipeline is about to read. Without this the import dies
        # on a missing data/books.json: the scan's results only ever existed in
        # this process, and ownership gating has nothing to gate on.
        reg = books.apply_to_registry(repo_root(), self.scan_result,
                                      out=ws / "data" / "books.json")
        self._write(f"    book registry -> {reg}")

        self.progress = Progress(n)

        args = ["--apply", "--data", str(ws / "data")]
        jar = self.jar_var.get().strip()
        if jar:
            args += ["--jar", jar]
        self.job = Job(pipeline_command("tools.import_library", args),
                       cwd=repo_root()).start()
        self._refresh_state()
        self.after(120, self._pump)

    def _pump(self):
        if not self.job:
            return
        lines, done = self.job.drain()
        for ln in lines:
            self._write(ln)
            if self.progress:
                self.progress.feed(ln)
        if self.progress:
            self.pbar["value"] = int(self.progress.fraction * 1000)
            self.stage.configure(text=self.progress.label())
        if done:
            rc = self.job.returncode
            self.stage.configure(
                text="Import finished." if rc == 0
                else ("Stopped." if rc == -1 else f"Import failed (exit {rc})."),
                foreground=OK if rc == 0 else BAD)
            if rc == 0:
                self.pbar["value"] = 1000
                self._write("\nNext: 'Review & correct' to check what was read, "
                            "then 'Publish to Foundry'.")
            self.job = None
            self._refresh_state()
            return
        self.after(120, self._pump)

    def _cancel(self):
        if self.job:
            self._write("!! stopping…")
            self.job.cancel()

    def _review(self):
        """Open the review app, starting it if it is not already up."""
        self._save()
        import socket

        with socket.socket() as s:
            s.settimeout(0.3)
            up = s.connect_ex(("127.0.0.1", 8347)) == 0
        if not up:
            self._write("=== starting the review app")
            self.job = Job(["node", "site/server/index.mjs"], cwd=repo_root()).start()
            self.after(1500, lambda: webbrowser.open(REVIEW_URL))
            self.after(120, self._pump)
        else:
            webbrowser.open(REVIEW_URL)

    def _publish(self):
        self._save()
        fd = self.foundry_var.get().strip()
        if not fd:
            messagebox.showwarning(APP_TITLE, "Set Foundry's Data folder first.")
            return
        ok, why = publish.check(Path(fd))
        if not ok:
            messagebox.showwarning(APP_TITLE, why)
            return
        self._write("=== building and publishing the catalog")
        self.progress = None
        self.stage.configure(text="Building…")
        self.job = Job(pipeline_command("tools.publish_catalog",
                                        ["--foundry", fd,
                                         "--data", str(Path(self.workspace_var.get()) / "data")]),
                       cwd=repo_root()).start()
        self._refresh_state()
        self.after(120, self._pump)


def main() -> int:
    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
