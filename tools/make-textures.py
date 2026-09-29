#!/usr/bin/env python3
"""
make-textures.py — Generates the static background textures.

Why PNGs and not shaders: the background has to be free. A ShaderEffect
would cost a GPU pass on every frame just to draw noise or a gradient
that never changes. Here the cost is paid once, at load.

Two textures, both black and white plus alpha, so they compose in
overlay mode on top of any base colour:

  grain.png     128x128 tileable — two-scale film grain
  vignette.png  1024x1024       — radial vignette, increasing alpha

The vignette is a texture because Rectangle in QML only accepts LINEAR
gradients (Gradient). A radialgradient would need QtQuick.Shapes or a
ShaderEffect: both reintroduce a cost there is no reason to pay here.

Usage:
    python3 tools/make-textures.py
"""
import random
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "qml" / "shared"

GRAIN_SIZE = 128
VIGNETTE_SIZE = 1024
SEED = 0x0B7EC1  # deterministic: the grain must not change on every build

# VIGNETTE: where the darkening reaches its maximum (0..1 from the centre).
# 0.30 = the centre is completely free, the falloff starts towards the corners.
VIGNETTE_START = 0.30
VIGNETTE_STRENGTH = 0.40


def write_png(path: Path, size: int, pixels) -> None:
    """Writes an 8-bit RGBA PNG, with no external dependencies."""
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter 0 (None) per row
        for px in row:
            raw += bytes(px)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def make_grain() -> None:
    """Two-scale noise: raw pixels + 2x2 blocks.

    The block blur is what makes it 'film grain' rather than 'salt and
    pepper'. Salt and pepper is digitally noisy; film is grainy. The
    difference is visible.
    """
    rng = random.Random(SEED)
    size = GRAIN_SIZE
    half = size // 2

    fine = [[rng.gauss(0, 1.0) for _ in range(size)] for _ in range(size)]
    coarse = [[rng.gauss(0, 1.0) for _ in range(half)] for _ in range(half)]

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            n = fine[y][x] * 0.75 + coarse[y // 2][x // 2] * 0.25
            v = int(max(0.0, min(1.0, n / 3.0 * 0.5 + 0.5)) * 255)
            a = int(min(1.0, abs(n) / 2.0) * 46)  # very low alpha
            row.append((v, v, v, a))
        rows.append(row)

    out = OUT_DIR / "grain.png"
    write_png(out, size, rows)
    print(f"✓ {out.name}  {size}x{size} tileable, {out.stat().st_size} bytes")


def make_vignette() -> None:
    """Alpha increasing from the centre towards the edges, black.

    smoothstep over the [START, 1] range: a linear transition would make
    a hard ring visible in the shading, and banding is the worst defect
    on a wide dark surface.
    """
    size = VIGNETTE_SIZE
    c = (size - 1) / 2.0
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            dx = (x - c) / c
            dy = (y - c) / c
            # normalise on the diagonal: the corners reach exactly 1.0
            d = min(1.0, (dx * dx + dy * dy) ** 0.5 / 1.41421)
            t = (d - VIGNETTE_START) / (1.0 - VIGNETTE_START)
            t = max(0.0, min(1.0, t))
            s = t * t * (3.0 - 2.0 * t)  # smoothstep
            a = int(s * VIGNETTE_STRENGTH * 255)
            row.append((0, 0, 0, a))
        rows.append(row)

    out = OUT_DIR / "vignette.png"
    write_png(out, size, rows)
    print(f"✓ {out.name}  {size}x{size} radial, {out.stat().st_size} bytes")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_grain()
    make_vignette()


if __name__ == "__main__":
    main()
