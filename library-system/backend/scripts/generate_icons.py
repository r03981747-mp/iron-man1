"""Generate the PWA/app icons for Libra.

Run from the backend directory after installing Pillow:

    .\\.venv\\Scripts\\python scripts\\generate_icons.py

The generated PNGs live in web/ and are served by FastAPI's static mount.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

WEB = Path(__file__).resolve().parents[2] / "web"
SIZE = 1024


def gradient(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            t = (x / size + y / size) / 2
            pixels[x, y] = (
                int(79 + (124 - 79) * t),
                int(70 + (58 - 70) * t),
                int(229 + (237 - 229) * t),
            )
    return image


def make_icon(size: int) -> Image.Image:
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, SIZE - 1, SIZE - 1), radius=int(SIZE * 0.22), fill=255
    )
    base.paste(gradient(SIZE), (0, 0), mask)

    draw = ImageDraw.Draw(base)
    white = (255, 255, 255, 246)
    pale = (255, 255, 255, 228)
    ink = (49, 46, 129, 205)

    # Open book: two pages meeting at a central spine.
    draw.polygon(
        [(218, 300), (482, 352), (482, 748), (218, 690)],
        fill=white,
    )
    draw.polygon(
        [(542, 352), (806, 300), (806, 690), (542, 748)],
        fill=pale,
    )
    draw.line([(512, 350), (512, 748)], fill=(67, 56, 202, 255), width=18)

    for y in (430, 500, 570, 640):
        draw.line([(282, y - 20), (430, y - 5)], fill=ink, width=18)
        draw.line([(594, y - 5), (742, y - 20)], fill=ink, width=18)

    # Gold bookmark on the right page.
    draw.polygon(
        [(704, 334), (770, 346), (770, 470), (737, 438), (704, 464)],
        fill=(245, 190, 80, 255),
    )

    return base.resize((size, size), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    WEB.mkdir(parents=True, exist_ok=True)
    make_icon(512).save(WEB / "icon-512.png", optimize=True)
    make_icon(192).save(WEB / "icon-192.png", optimize=True)
    make_icon(180).save(WEB / "apple-touch-icon.png", optimize=True)
    make_icon(32).save(WEB / "favicon-32.png", optimize=True)
    print("Generated PWA icons in", WEB)
