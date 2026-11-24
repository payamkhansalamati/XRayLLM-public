"""Generate the study capability pilot image without external data."""

import struct
import zlib
from pathlib import Path


def _chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return (
        struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
    )


def _make_test_png(path: Path) -> None:
    """Create an unlabeled white image with a blue triangle and red circle."""
    width = height = 256
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)
        for x in range(width):
            color = (255, 255, 255)
            # Solid blue triangle with a horizontal base and an upward apex.
            if 30 <= y <= 200:
                half_width = int((y - 30) * 0.40)
                if 85 - half_width <= x <= 85 + half_width:
                    color = (30, 90, 220)
            # Separate solid red circle.
            if (x - 190) ** 2 + (y - 190) ** 2 <= 28**2:
                color = (220, 40, 40)
            pixels.extend(color)

    image = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(pixels)))
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(image)
