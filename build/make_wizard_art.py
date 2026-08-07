"""Build the installer's wizard artwork from a character render.

    python build/make_wizard_art.py <character.png>

Inno draws a tall panel down the left of the welcome and finished pages, and a
small square top-right on the rest. Both want several sizes so Windows can pick
one per display scaling — supply only the 100% image and it is stretched, which
on a 200% display looks exactly as bad as it sounds.

The source render is a square with a lot of empty space, so the subject is
cropped to its alpha bounding box before anything else. Scaling the untrimmed
square would waste most of a narrow panel on nothing.

Two formats are written. Inno 6.3+ takes PNG with alpha, which lets the figure
sit on the wizard's own background; older versions need BMP, which cannot, so
those are composited onto the app's dark panel colour first.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "wizard"

#: The app's own palette, so the installer and the program look related.
BG_TOP = (17, 20, 28)          # #11141c
BG_BOTTOM = (8, 11, 18)
ACCENT = (47, 212, 217)        # #2fd4d9

#: Panel sizes Inno picks between by display scaling (100/125/150/200%).
LARGE = [(164, 314), (192, 386), (256, 482), (328, 628)]
SMALL = [(55, 55), (64, 68), (92, 97), (110, 110)]

#: The full-height figure drawn down the left of EVERY page by the [Code]
#: section. Generated tall and wide enough for a 200% display, then scaled
#: down in the wizard rather than up, which never softens.
SIDEBAR = [(220, 420), (264, 504), (330, 630), (440, 840)]

#: Inno's wizard pages are white, and a custom TBitmapImage has no alpha —
#: so "transparent" means composited onto that background, seamlessly.
PAGE_BG = (255, 255, 255)


def gradient(size: tuple[int, int]) -> Image.Image:
    """A vertical wash, so the panel is not a flat rectangle of one colour."""
    w, h = size
    img = Image.new("RGB", size, BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)],
               fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return img


def trimmed(src: Image.Image) -> Image.Image:
    """The subject alone — the render is mostly transparent space."""
    box = src.getbbox()
    return src.crop(box) if box else src


def fit(subject: Image.Image, size: tuple[int, int], pad: float = 0.06) -> Image.Image:
    """Scale the subject to the panel width, standing on the bottom edge.

    Width-led, not height-led. The panel is far narrower than the render is
    wide — 328x628 against a 531x654 subject — so filling the height crops the
    sides, and on this figure that takes the axe head clean off. Fitting the
    width keeps the whole character and leaves the space above for the wizard's
    own text, which is where it wants to be anyway.
    """
    w, h = size
    avail_w = int(w * (1 - pad))
    scale = min(avail_w / subject.width, (h * 0.94) / subject.height)
    fig = subject.resize((max(1, int(subject.width * scale)),
                          max(1, int(subject.height * scale))), Image.LANCZOS)

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    # centred horizontally, standing on the bottom edge
    layer.paste(fig, ((w - fig.width) // 2, h - fig.height), fig)
    return layer


def accent_edge(img: Image.Image) -> Image.Image:
    """A thin accent rule down the inner edge — the one bit of colour."""
    d = ImageDraw.Draw(img)
    d.line([(img.width - 1, 0), (img.width - 1, img.height)], fill=ACCENT, width=1)
    return img


def build(src_path: Path) -> None:
    src = Image.open(src_path).convert("RGBA")

    # Mirror across the vertical axis, so the figure faces into the wizard's
    # text rather than off the edge of the window.
    src = src.transpose(Image.FLIP_LEFT_RIGHT)
    subject = trimmed(src)
    print(f"subject {subject.size} (from {src.size})")

    OUT.mkdir(parents=True, exist_ok=True)

    for size in LARGE:
        fig = fit(subject, size)
        # PNG keeps the alpha for Inno 6.3+
        png = Image.new("RGBA", size, (0, 0, 0, 0))
        png.alpha_composite(fig)
        png.save(OUT / f"wizard-{size[0]}x{size[1]}.png")
        # BMP cannot, so flatten onto the panel colour
        bmp = gradient(size)
        bmp.paste(fig, (0, 0), fig)
        accent_edge(bmp).save(OUT / f"wizard-{size[0]}x{size[1]}.bmp")

    # the small square: the head, which is the recognisable part at 55px
    head = subject.crop((0, 0, subject.width, int(subject.height * 0.34)))
    for size in SMALL:
        s = min(size)
        h2 = head.copy()
        h2.thumbnail((s, s), Image.LANCZOS)
        png = Image.new("RGBA", size, (0, 0, 0, 0))
        png.paste(h2, ((size[0] - h2.width) // 2, (size[1] - h2.height) // 2), h2)
        png.save(OUT / f"small-{size[0]}x{size[1]}.png")
        bmp = gradient(size)
        bmp.paste(h2, ((size[0] - h2.width) // 2, (size[1] - h2.height) // 2), h2)
        bmp.save(OUT / f"small-{size[0]}x{size[1]}.bmp")

    # the full-height sidebar figure, on the wizard's own white
    for size in SIDEBAR:
        w, h = size
        # fills the height; the panel is sized to the figure so nothing crops
        scale = (h * 0.98) / subject.height
        fig = subject.resize((max(1, int(subject.width * scale)),
                              max(1, int(subject.height * scale))), Image.LANCZOS)
        panel = Image.new("RGB", size, PAGE_BG)
        panel.paste(fig, ((w - fig.width) // 2, h - fig.height), fig)
        panel.save(OUT / f"sidebar-{w}x{h}.bmp")

    made = sorted(p.name for p in OUT.glob("*"))
    print(f"wrote {len(made)} files to {OUT}")
    for m in made:
        print(f"  {m}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    if not src.is_file():
        print(f"no such image: {src}")
        return 1
    build(src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
