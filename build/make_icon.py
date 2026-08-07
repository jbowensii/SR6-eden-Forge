"""Build the application icon from the site's favicon.

    python build/make_icon.py

The website mark is an SVG — a dark rounded square, a magenta hex outline and a
"6". Windows wants a multi-resolution .ico, so it is redrawn here at each size
rather than scaled from one bitmap: at 16px a downscaled 256px render turns the
hex into mud, whereas a 16px draw keeps the stroke a clean pixel wide.

Drawn with Pillow rather than rendered from the SVG so the build needs no
cairosvg or rsvg — the mark is four shapes, and matching them by hand is
cheaper than the dependency.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "wizard"

BG = (11, 13, 18, 255)        # #0b0d12
HEX = (229, 23, 123, 255)     # #e5177b
SIX = (255, 79, 163, 255)     # #ff4fa3

SIZES = [256, 128, 64, 48, 32, 24, 16]


def _hex_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    """A pointy-top hexagon, matching the favicon's orientation."""
    return [(cx + r * math.sin(math.radians(a)),
             cy - r * math.cos(math.radians(a)))
            for a in range(0, 360, 60)]


def _font(px: int):
    for name in ("arialbd.ttf", "seguisb.ttf", "segoeuib.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def draw(size: int) -> Image.Image:
    # drawn at 4x and reduced: the only cheap way to get a smooth hex stroke
    ss = 4
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    radius = int(s * 0.19)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=BG)

    r = s * 0.40
    width = max(ss, int(s * 0.062))
    d.polygon(_hex_points(s / 2, s / 2, r), outline=HEX, width=width)

    # the "6", optically centred — a numeral's ink sits high in its box
    f = _font(int(s * 0.56))
    text = "6"
    box = d.textbbox((0, 0), text, font=f)
    d.text(((s - (box[2] - box[0])) / 2 - box[0],
            (s - (box[3] - box[1])) / 2 - box[1] - s * 0.02),
           text, font=f, fill=SIX)

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    layers = [draw(n) for n in SIZES]
    ico = OUT / "app.ico"
    # Every size embedded, so Explorer, the taskbar and Alt-Tab each get one
    # drawn at their own resolution.
    #
    # bitmap_format="bmp" is load-bearing. Pillow's default writes EVERY entry
    # PNG-compressed, and Windows only renders a PNG entry at 256x256 — at
    # 16/24/32/48 the shell needs BMP (DIB). A default save therefore produces
    # an .ico that embeds cleanly, reports the right dimensions, and draws as
    # nothing: the file has an icon resource the shell cannot decode.
    layers[0].save(ico, format="ICO", bitmap_format="bmp",
                   sizes=[(n, n) for n in SIZES], append_images=layers[1:])
    draw(256).save(OUT / "app-256.png")
    print(f"wrote {ico} ({', '.join(str(n) for n in SIZES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
