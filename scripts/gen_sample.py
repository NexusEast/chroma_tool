"""Generate a deterministic sample sprite sheet for the README screenshot.

Draws a grid of simple coloured shapes on the tool's default chroma-green
background (BGR 50,180,138 = RGB 138,180,50), each with a soft drop
shadow so the screenshot shows off the shadow-preserving pipeline.  The
output is fully synthetic — no game assets — so the screenshot in CI is
reproducible and ships nothing private.

Usage::

    python scripts/gen_sample.py [output_path]

Defaults to ``<repo>/_sample_sheet.png``.  Prints the path it wrote so
the screenshot driver can pick it up.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent

# RGB form of the GUI's default background (BGR 50,180,138).
BG_RGB = (138, 180, 50)

COLS, ROWS = 6, 4
CELL = 180
MARGIN = 30
ICON = 110  # nominal icon size inside a cell

# A fixed palette so output is deterministic across runs/platforms.
PALETTE = [
    (231, 76, 60), (52, 152, 219), (241, 196, 15), (155, 89, 182),
    (26, 188, 156), (230, 126, 34), (46, 204, 113), (52, 73, 94),
    (236, 64, 122), (149, 165, 166), (255, 138, 101), (124, 77, 255),
]

# Shape kinds cycled across the grid: each cell picks one deterministically.
KINDS = ("circle", "square", "triangle", "diamond", "star", "rounded")


def _star_points(cx: float, cy: float, r_out: float, r_in: float,
                 n: int = 5) -> list[tuple[float, float]]:
    import math
    pts: list[tuple[float, float]] = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        ang = math.pi / 2 + i * math.pi / n
        pts.append((cx + r * math.cos(ang), cy - r * math.sin(ang)))
    return pts


def _draw_shape(draw: ImageDraw.ImageDraw, kind: str, box: tuple[int, int, int, int],
                colour: tuple[int, int, int]) -> None:
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if kind == "circle":
        draw.ellipse(box, fill=colour)
    elif kind == "square":
        draw.rectangle(box, fill=colour)
    elif kind == "triangle":
        draw.polygon([(cx, y0), (x1, y1), (x0, y1)], fill=colour)
    elif kind == "diamond":
        draw.polygon([(cx, y0), (x1, cy), (cx, y1), (x0, cy)], fill=colour)
    elif kind == "star":
        draw.polygon(_star_points(cx, cy, (x1 - x0) / 2, (x1 - x0) / 4),
                     fill=colour)
    else:  # rounded
        draw.rounded_rectangle(box, radius=(x1 - x0) // 4, fill=colour)


def generate(out_path: Path) -> Path:
    w = MARGIN * 2 + COLS * CELL
    h = MARGIN * 2 + ROWS * CELL
    img = Image.new("RGB", (w, h), BG_RGB)

    # Shadow layer rendered separately, blurred, then composited under the
    # icons so each shape sits on a soft drop shadow.
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    base = Image.new("RGB", (w, h), BG_RGB)
    bdraw = ImageDraw.Draw(base)

    idx = 0
    for row in range(ROWS):
        for col in range(COLS):
            cx0 = MARGIN + col * CELL + (CELL - ICON) // 2
            cy0 = MARGIN + row * CELL + (CELL - ICON) // 2
            box = (cx0, cy0, cx0 + ICON, cy0 + ICON)
            kind = KINDS[idx % len(KINDS)]
            colour = PALETTE[idx % len(PALETTE)]
            # Drop shadow: same shape, offset down-right, dark + translucent.
            soff = (box[0] + 10, box[1] + 12, box[2] + 10, box[3] + 12)
            _draw_shape(sdraw, kind, soff, (0, 0, 0, 110))
            idx += 1

    shadow = shadow.filter(ImageFilter.GaussianBlur(6))
    base = Image.alpha_composite(base.convert("RGBA"), shadow).convert("RGB")

    bdraw = ImageDraw.Draw(base)
    idx = 0
    for row in range(ROWS):
        for col in range(COLS):
            cx0 = MARGIN + col * CELL + (CELL - ICON) // 2
            cy0 = MARGIN + row * CELL + (CELL - ICON) // 2
            box = (cx0, cy0, cx0 + ICON, cy0 + ICON)
            kind = KINDS[idx % len(KINDS)]
            colour = PALETTE[idx % len(PALETTE)]
            _draw_shape(bdraw, kind, box, colour)
            idx += 1

    base.save(out_path)
    return out_path


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "_sample_sheet.png"
    path = generate(out)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
