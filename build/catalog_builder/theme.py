"""Colours, in the Foundry/eden register, following whatever the OS is wearing.

The palette is neon pink and cyan on a near-black slate, matching the eden
system's own look and this project's mark. That reads beautifully on dark and
is close to illegible on light, so the light palette does NOT simply swap the
background: the accents are re-mixed to darker, denser versions of the same
hues. Neon is a light-on-dark effect; #ff4fa3 on white is a pale smear.

Readability is enforced rather than eyeballed. :func:`contrast_ratio`
implements the WCAG 2.1 formula and the tests hold every text colour to 4.5:1
against the surface it is drawn on, in BOTH modes. Change a colour and the
tests say whether it is still readable.
"""
from __future__ import annotations

#: WCAG 2.1 minimum for body text. Large/bold text may sit at 3.0.
AA_NORMAL = 4.5
AA_LARGE = 3.0


def _srgb(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    """Relative luminance, per WCAG 2.1."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """Contrast between two colours: 1.0 (identical) to 21.0 (black on white)."""
    a, b = luminance(fg), luminance(bg)
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


#: Dark: the eden look proper — neon on slate.
DARK = {
    "mode": "dark",
    "bg": "#0b0d12",          # the page
    "surface": "#161b26",     # entries, log
    "raised": "#212836",      # buttons
    "hover": "#2c3446",
    "text": "#dfe5f0",
    "muted": "#98a2b8",       # hints — still held to 4.5:1, they are real text
    "pink": "#ff4fa3",        # headings, the mark
    "blue": "#3ad9f0",        # the action colour
    "onAccent": "#07101a",    # text ON a pink/blue fill
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "bad": "#ff6b81",
    "border": "#2a3244",
}

#: Light: same hues, re-mixed. Neon does not survive a white background.
LIGHT = {
    "mode": "light",
    "bg": "#f2f4f8",
    "surface": "#ffffff",
    "raised": "#e4e8f0",
    "hover": "#d5dbe6",
    "text": "#141821",
    "muted": "#59617400",     # placeholder, fixed below
    "pink": "#a3005f",        # deep magenta: the same hue with contrast
    "blue": "#0b6b80",
    "onAccent": "#ffffff",
    "ok": "#1a7f3c",
    "warn": "#8a5200",
    "bad": "#b3261e",
    "border": "#c3cad6",
}
LIGHT["muted"] = "#4d5566"

PALETTES = {"dark": DARK, "light": LIGHT}


def detect_mode() -> str:
    """What the OS is set to. Falls back to dark, which is this app's home.

    Windows keeps it in the registry as ``AppsUseLightTheme`` (1 light, 0 dark)
    — note the inversion, the value names the LIGHT case.

    ``SR6_THEME=light|dark`` overrides, which is how the light palette gets
    looked at without changing the whole desktop to check.
    """
    import os

    forced = (os.environ.get("SR6_THEME") or "").strip().lower()
    if forced in PALETTES:
        return forced

    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        with key:
            light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if light else "dark"
    except Exception:
        return "dark"


def palette(mode: str | None = None) -> dict:
    return PALETTES[mode or detect_mode()]


def apply(root, style, p: dict) -> None:
    """Paint every widget class. ttk needs each one named explicitly."""
    root.configure(bg=p["bg"])
    try:
        style.theme_use("clam")           # the only stock theme that obeys us
    except Exception:
        pass

    style.configure(".", background=p["bg"], foreground=p["text"],
                    fieldbackground=p["surface"], bordercolor=p["border"],
                    borderwidth=0, focuscolor=p["blue"])
    style.configure("TFrame", background=p["bg"])
    style.configure("TLabel", background=p["bg"], foreground=p["text"])
    style.configure("Head.TLabel", foreground=p["pink"],
                    font=("Segoe UI Semibold", 11))
    style.configure("Title.TLabel", foreground=p["text"],
                    font=("Segoe UI Semibold", 15))
    style.configure("Hint.TLabel", foreground=p["muted"], font=("Segoe UI", 9))

    style.configure("TButton", background=p["raised"], foreground=p["text"],
                    padding=(12, 6), borderwidth=1, relief="solid",
                    bordercolor=p["border"], lightcolor=p["raised"],
                    darkcolor=p["raised"])
    style.map("TButton",
              background=[("active", p["hover"]), ("disabled", p["bg"])],
              bordercolor=[("active", p["blue"])],
              foreground=[("disabled", p["muted"])])

    # the one filled control: pink, because it is the thing to press
    style.configure("Go.TButton", background=p["pink"], foreground=p["onAccent"],
                    font=("Segoe UI Semibold", 10), padding=(16, 8),
                    bordercolor=p["pink"], lightcolor=p["pink"],
                    darkcolor=p["pink"], relief="flat")
    style.map("Go.TButton",
              background=[("active", p["blue"]), ("disabled", p["raised"])],
              bordercolor=[("active", p["blue"])],
              lightcolor=[("active", p["blue"])],
              darkcolor=[("active", p["blue"])],
              foreground=[("disabled", p["muted"])])

    style.configure("TEntry", fieldbackground=p["surface"], foreground=p["text"],
                    insertcolor=p["text"], padding=6, borderwidth=1)
    style.configure("TSpinbox", fieldbackground=p["surface"],
                    foreground=p["text"], arrowcolor=p["blue"], padding=4)
    style.configure("TProgressbar", background=p["blue"],
                    troughcolor=p["surface"], borderwidth=0)
    style.configure("TScale", background=p["bg"], troughcolor=p["surface"])
    style.configure("TScrollbar", background=p["raised"],
                    troughcolor=p["bg"], arrowcolor=p["muted"])


#: Every (foreground, background) pair the window actually draws, so the tests
#: check what is on screen rather than a hopeful subset.
TEXT_PAIRS = [
    ("text", "bg"), ("text", "surface"), ("text", "raised"),
    ("muted", "bg"), ("muted", "surface"),
    ("pink", "bg"), ("blue", "bg"),
    ("ok", "bg"), ("warn", "bg"), ("bad", "bg"),
    ("onAccent", "pink"), ("onAccent", "blue"),
]
