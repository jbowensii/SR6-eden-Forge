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
    from catalog_builder import (books, commlink6, cores, identify, ports,
                                 publish, theme)
    from catalog_builder.runner import Job, Progress, pipeline_command
    from catalog_builder.settings import (
        Settings, default_workspace, detect_commlink6, detect_foundry_data,
        ensure_workspace, sync_review_settings)
except ImportError:                       # installed under a different root
    from build.catalog_builder import (books, commlink6, cores, identify,
                                       ports, publish, theme)
    from build.catalog_builder.runner import Job, Progress, pipeline_command
    from build.catalog_builder.settings import (
        Settings, default_workspace, detect_commlink6, detect_foundry_data,
        ensure_workspace, sync_review_settings)

APP_TITLE = "Shadowrun 6th World Catalog Builder"
#: a blank line inside a message box
NL2 = chr(10) + chr(10)
#: the review app's port is chosen per run — see catalog_builder.ports

#: The palette, chosen from what the OS is set to. Read once at startup —
#: Windows can change it mid-session, but restyling a live Tk window widget by
#: widget is more machinery than a settings screen deserves.
P = theme.palette()
BG = P["bg"]
FG = P["text"]
ACCENT = P["blue"]
MUTED = P["muted"]
OK = P["ok"]
WARN = P["warn"]
BAD = P["bad"]


def repo_root() -> Path:
    """Where the pipeline lives — beside the exe when frozen, else the repo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG)

        self._set_window_icon()
        self.settings = Settings()
        self.job: Job | None = None
        self.review_job: Job | None = None
        self.review_port: int = 0
        self.progress: Progress | None = None
        self.scan_result: dict | None = None
        self._deep_key: str | None = None    # folder the content scan covered
        self._c6_job: threading.Thread | None = None   # Commlink6 download

        self._style()
        self._build()
        self._prefill()
        self._refresh_state()
        self._fit_window()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
        theme.apply(self, ttk.Style(self), P)

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
        # Deliberately NOT pre-filled. There is no folder we could guess that
        # would be right, and a wrong path presented as a default reads as
        # "this is where your icons are" when it is nothing of the kind.
        self._row(form, "5.  Icon sets  (optional)",
                  "A folder of icon packs to match items against in the review "
                  "app. Leave empty if you have none.",
                  "icons", self._pick_icons, 16)

        actions = ttk.Frame(pad)
        actions.grid(row=3, column=0, sticky="ew", pady=(16, 6))
        self.import_btn = ttk.Button(actions, text="Import books", style="Go.TButton",
                                     command=self._import)
        self.import_btn.pack(side="left")
        self.review_btn = ttk.Button(actions, text="Review & correct",
                                     command=self._review)
        self.review_btn.pack(side="left", padx=8)
        self.publish_btn = ttk.Button(actions, text="Publish to Foundry",
                                      command=self._publish)
        self.publish_btn.pack(side="left")
        self.cancel_btn = ttk.Button(actions, text="Stop", command=self._cancel)
        self.cancel_btn.pack(side="right")
        # Enabled only once the content scan has found files whose names do not
        # match the retail pattern — an offer, never something that happens on
        # its own, because it changes files on disk.
        self.rename_btn = ttk.Button(actions, text="Rename files…",
                                     command=self._rename_files, state="disabled")
        self.rename_btn.pack(side="right", padx=(0, 8))

        self.pbar = ttk.Progressbar(pad, mode="determinate", maximum=1000)
        self.pbar.grid(row=4, column=0, sticky="ew")
        self.stage = ttk.Label(pad, text="Ready.", style="Hint.TLabel")
        self.stage.grid(row=5, column=0, sticky="w", pady=(2, 6))

        self.log = tk.Text(pad, height=8, bg=P["surface"], fg=P["muted"],
                           insertbackground=FG, relief="flat", wrap="none",
                           highlightthickness=1, highlightbackground=P["border"],
                           font=("Consolas", 9))
        self.log.grid(row=6, column=0, sticky="nsew")
        pad.rowconfigure(6, weight=1)
        sb = ttk.Scrollbar(pad, command=self.log.yview)
        sb.grid(row=6, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set, state="disabled")

    def _fit_window(self) -> None:
        """Size to what the widgets actually need, then centre.

        This used to be a hard-coded 880x620, which fitted the layout it was
        measured against and nothing else: adding a fifth field pushed the
        buttons and the log off the bottom and the Browse buttons off the
        right. Tk already knows the required size — asking it means the window
        cannot be outgrown by adding a row.
        """
        self.update_idletasks()
        need_w, need_h = self.winfo_reqwidth(), self.winfo_reqheight()

        # never larger than the display, allowing for the taskbar
        max_w = self.winfo_screenwidth() - 80
        max_h = self.winfo_screenheight() - 140
        w = max(960, min(need_w, max_w))
        h = max(700, min(need_h, max_h))

        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")
        # the floor is what the fields need, not a number someone liked
        self.minsize(min(need_w, max_w), min(need_h, max_h))

    # ---------- identifying books by what is inside them ----------
    def _start_deep_scan(self, pdf_dir: Path, registry: dict) -> None:
        """Confirm the filename guess against the contents, off the UI thread.

        A filename is a convention; the Catalyst product code printed in the
        book is a fact. Reading fifty PDFs takes a minute or two the first time,
        so it happens in a worker thread and the answer replaces the filename
        one when it lands. Signals are cached by path+size+mtime, so every scan
        after the first is instant.

        Only one runs at a time, and a stale one is discarded: the folder box
        fires this on every keystroke.
        """
        key = str(pdf_dir)
        if getattr(self, "_deep_key", None) == key:
            return                              # already done or in flight
        self._deep_key = key

        def work():
            try:
                cache = identify.SignalCache(identify.default_cache_path())
                result = books.scan(
                    pdf_dir, registry,
                    identify_fn=lambda p: identify.identify(p, registry, cache))
                cache.save()
            except Exception as e:              # never take the window down
                self.after(0, lambda: self._write(
                    f"!! could not read the PDFs: {type(e).__name__}: {e}"))
                return
            self.after(0, lambda: self._deep_scan_done(key, result))

        threading.Thread(target=work, daemon=True).start()

    def _deep_scan_done(self, key: str, result: dict) -> None:
        """Adopt the content-based result, if the folder has not moved on."""
        if getattr(self, "_deep_key", None) != key:
            return                              # the user changed folder
        self.scan_result = result
        n = len(result["matched"])
        by_content = sum(1 for m in result["matched"]
                         if "filename" not in (m.get("how") or ""))
        self.pdf_status.configure(
            text=f"{books.summary(result)}   ({by_content} identified from "
                 f"inside the file)",
            foreground=OK if n else WARN)
        self._refresh_rename_button()

    def _refresh_rename_button(self) -> None:
        plan = self._rename_plan()
        self.rename_btn.configure(
            text=f"Rename {len(plan)} file(s)…" if plan else "Rename files…",
            state="normal" if plan else "disabled")

    def _rename_plan(self) -> list:
        if not self.scan_result:
            return []
        try:
            return identify.plan_renames(self.scan_result["matched"],
                                         books.load_registry(repo_root()))
        except Exception:
            return []

    def _rename_files(self) -> None:
        """Offer to rename recognised books to the retail naming pattern."""
        plan = self._rename_plan()
        if not plan:
            messagebox.showinfo(APP_TITLE, "Every recognised book is already "
                                           "named the standard way.")
            return

        clashes = [p for p in plan if p["collision"]]
        preview = NL2.join(f"{p['from']}\n    -> {p['to']}" for p in plan[:12])
        more = f"{NL2}...and {len(plan) - 12} more" if len(plan) > 12 else ""
        warn = (f"{NL2}{len(clashes)} will be SKIPPED — a different file "
                f"already has that name." if clashes else "")

        if not messagebox.askyesno(
                APP_TITLE,
                f"Rename {len(plan)} file(s) on disk?{NL2}{preview}{more}{warn}"):
            return

        out = identify.apply_renames(plan)
        self._write(f"=== renamed {len(out['renamed'])} file(s), "
                    f"skipped {len(out['skipped'])}")
        for s in out["skipped"]:
            self._write(f"    skipped {s['from']}: {s['why']}")
        self._deep_key = None                   # paths changed; scan afresh
        self._refresh_state()

    def _on_close(self) -> None:
        """Ask about the review server before the window disappears.

        The review app is a real web server in its own process. Closing this
        window used to leave it listening, so the port stayed busy, edits could
        still be made to a library nothing was watching, and the only way to
        stop it was Task Manager. Nor should it be killed silently: leaving it
        up to keep working in the browser is a perfectly reasonable thing to
        want.
        """
        running = (self.review_job is not None and self.review_job.running) or (
            self.review_port and ports.is_listening(self.review_port))

        if running:
            answer = messagebox.askyesnocancel(
                APP_TITLE,
                f"The review app is still running on port {self.review_port}."
                + NL2
                + "Yes  — stop it and close" + chr(10)
                + "No   — leave it running and close" + chr(10)
                + "Cancel — go back")
            if answer is None:
                return                      # cancel: stay open
            if answer:
                if self.review_job:
                    self.review_job.cancel()
                self._write("=== review app stopped")
            else:
                self._write(f"=== leaving the review app on "
                            f"http://localhost:{self.review_port}")

        # an import or publish is a different question: it writes to the library
        if self.job and self.job.running and self.job is not self.review_job:
            if not messagebox.askyesno(
                    APP_TITLE,
                    "A job is still running and will be stopped." + NL2
                    + "Close anyway?"):
                return
            self.job.cancel()

        self.destroy()

    # ---------- state ----------
    def _prefill(self) -> None:
        s = self.settings
        self.pdf_var.set(s["pdfFolder"])
        self.jar_var.set(s["commlink6Jar"] or str(detect_commlink6() or ""))
        self.foundry_var.set(s["foundryData"] or str(detect_foundry_data() or ""))
        self.workspace_var.set(s["workspace"] or str(default_workspace()))
        self.icons_var.set(s["iconLibrary"])      # never guessed
        for v in (self.pdf_var, self.jar_var, self.foundry_var,
                  self.workspace_var, self.icons_var):
            v.trace_add("write", lambda *_: self._refresh_state())

    def _save(self) -> None:
        s = self.settings
        s["pdfFolder"] = self.pdf_var.get().strip()
        s["commlink6Jar"] = self.jar_var.get().strip()
        s["foundryData"] = self.foundry_var.get().strip()
        s["workspace"] = self.workspace_var.get().strip()
        s["iconLibrary"] = self.icons_var.get().strip()
        s.save()

        # Push the paths to the review app every time they change, not only at
        # import: the website shows the same settings, and the two silently
        # disagreeing is worse than either being wrong on its own.
        try:
            sync_review_settings(
                Path(s["workspace"] or default_workspace()),
                s["iconLibrary"], s["commlink6Jar"])
        except OSError:
            pass                       # the workspace may not exist yet

    def _refresh_state(self) -> None:
        """Say what each answer means, before anything is run."""
        pdf = Path(self.pdf_var.get().strip() or ".")
        if self.pdf_var.get().strip() and pdf.is_dir():
            reg = books.load_registry(repo_root())
            # The FAST answer, from filenames only. This runs on every keystroke
            # in the folder box, so it must not open a single PDF — reading
            # fifty of them here would freeze the window mid-type.
            self.scan_result = books.scan(pdf, reg)
            n = len(self.scan_result["matched"])
            self.pdf_status.configure(
                text=books.summary(self.scan_result),
                foreground=OK if n else WARN)
            # ...then confirm it against what is INSIDE the files, off-thread.
            self._start_deep_scan(pdf, reg)
        else:
            self.scan_result = None
            self.pdf_status.configure(text="No folder chosen.", foreground=MUTED)
        # Offered off the filename scan as well, not only the content one: a
        # stale "Rename 12 file(s)…" left on the button after the folder is
        # cleared is an offer to rename files that are no longer in view.
        self._refresh_rename_button()

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

        icons = self.icons_var.get().strip()
        if icons and Path(icons).is_dir():
            sets = sorted(d.name for d in Path(icons).iterdir() if d.is_dir())
            n = sum(1 for _ in Path(icons).rglob("*") if _.is_file())
            self.icons_status.configure(
                text=(f"{len(sets)} set(s), {n} files: " + ", ".join(sets[:3])
                      + (" ..." if len(sets) > 3 else "")) if sets
                     else f"{n} file(s).",
                foreground=OK if n else WARN)
        elif icons:
            self.icons_status.configure(text="That folder does not exist.",
                                        foreground=BAD)
        else:
            self.icons_status.configure(
                text="Not set — item art matching is skipped.", foreground=MUTED)

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

    def _pick_icons(self):
        d = filedialog.askdirectory(title="Folder holding your icon sets")
        if d:
            self.icons_var.set(d)

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

        # asked every run, remembered between runs: the right answer depends on
        # what else the machine is doing today
        workers = cores.ask_workers(self, self.settings)
        if workers is None:
            return                                   # backed out of the dialog

        ws = ensure_workspace(self.workspace_var.get().strip() or default_workspace())
        sync_review_settings(ws, self.icons_var.get().strip(),
                             self.jar_var.get().strip())

        n = len(self.scan_result["matched"])
        self._write(f"=== importing {n} book(s) into {ws}")
        self._write(f"    reading {workers} book(s) at a time; "
                    f"merging one at a time, in order")

        # The registry, with the matched PDF paths filled in, written INTO the
        # workspace the pipeline is about to read. Without this the import dies
        # on a missing data/books.json: the scan's results only ever existed in
        # this process, and ownership gating has nothing to gate on.
        reg = books.apply_to_registry(repo_root(), self.scan_result,
                                      out=ws / "data" / "books.json")
        self._write(f"    book registry -> {reg}")

        self.progress = Progress(n)

        args = ["--apply", "--data", str(ws / "data"),
                "--workers", str(workers)]
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

        port = ports.ask_port(self, self.settings)
        if port is None:
            return
        url = f"http://localhost:{port}"

        if ports.is_listening(port):
            webbrowser.open(url)                       # already running
            return

        # Pre-flight. The server needs its dependencies and its built front
        # end; without them node exits immediately and the old code opened a
        # browser tab at a dead port anyway, with the reason nowhere on screen.
        site = repo_root() / "site"
        missing = [str(p.relative_to(repo_root()))
                   for p in (site / "node_modules", site / "dist")
                   if not p.is_dir()]
        if missing:
            self._write(f"!! the review app cannot start — missing: "
                        f"{', '.join(missing)}")
            messagebox.showerror(
                APP_TITLE,
                "The review app is not installed completely." + NL2
                + "Missing: " + ", ".join(missing) + NL2
                + "Reinstall the Catalog Builder to restore it.")
            return

        self._write(f"=== starting the review app on {port}")
        # SR6_DATA, or the review app reads the installation's own data/ — which
        # does not exist — and records the user's edits there too, where the
        # import would never find them.
        ws = ensure_workspace(self.workspace_var.get().strip() or default_workspace())
        self.job = Job(["node", "site/server/index.mjs"], cwd=repo_root(),
                       env={"PORT": str(port),
                            "SR6_DATA": str(ws / "data")}).start()
        # kept apart from self.job, which every other action reuses — closing
        # the window has to be able to find THIS one specifically
        self.review_job = self.job
        self.review_port = port
        self.after(120, self._pump)
        self._await_review(port, url, tries=0)

    def _await_review(self, port: int, url: str, tries: int) -> None:
        """Open the browser only once the server actually answers.

        Opening on a timer was the bug: a server that died on startup still got
        a browser tab pointed at it, so the failure looked like an empty page
        rather than an error.
        """
        if ports.is_listening(port):
            self._write(f"    review app ready at {url}")
            webbrowser.open(url)
            return
        if self.job and not self.job.running:
            self._write("!! the review app stopped before it began listening — "
                        "see the log above for the reason")
            return
        if tries > 60:                                 # ~24 seconds
            self._write(f"!! the review app did not answer on {port} in time")
            return
        self.after(400, lambda: self._await_review(port, url, tries + 1))

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
