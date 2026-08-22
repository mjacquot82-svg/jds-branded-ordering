from __future__ import annotations

from io import BytesIO
from pathlib import Path
import struct
import zlib

from PIL import Image
import qrcode
import qrcode.image.svg


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return (47, 51, 40)
    try:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (47, 51, 40)


def tenant_icon_png(size: int, background: str, accent: str, *, maskable: bool = False) -> bytes:
    """Generate a dependency-free tenant-colored PNG with a centered brand mark."""
    if size not in {192, 512}:
        raise ValueError("Unsupported icon size.")
    bg = _rgb(background); mark = _rgb(accent)
    margin = size // (5 if maskable else 7)
    center = size / 2; radius = (size - margin * 2) / 2
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            inside = (x - center) ** 2 + (y - center) ** 2 <= radius ** 2
            rows.extend(mark if inside else bg)
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")


def tenant_media_icon_png(path: Path, size: int, background: str, position: dict, *, contain: bool = False, maskable: bool = False) -> bytes:
    if size not in {192, 512}:
        raise ValueError("Unsupported icon size.")
    with Image.open(path) as source:
        source = source.convert("RGBA")
        zoom = float(position.get("zoom", 1)); x = float(position.get("x", 50)) / 100; y = float(position.get("y", 50)) / 100
        # The editor's central 70% dotted box is the literal output crop. Render
        # one fixed normalized canvas so 192px and 512px output are equivalent.
        canvas_size = 1000; crop_inset = 150; crop_size = 700
        scale = max(canvas_size / source.width, canvas_size / source.height) * zoom
        resized = source.resize((max(1,round(source.width*scale)),max(1,round(source.height*scale))),Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA",(canvas_size,canvas_size),_rgb(background)+(255,))
        left = round((canvas_size-resized.width)*x); top = round((canvas_size-resized.height)*y)
        canvas.alpha_composite(resized,(left,top))
        cropped=canvas.crop((crop_inset,crop_inset,crop_inset+crop_size,crop_inset+crop_size)).resize((size,size),Image.Resampling.LANCZOS)
        output=BytesIO();cropped.convert("RGB").save(output,"PNG",optimize=True);return output.getvalue()


def launch_qr_svg(url: str) -> bytes:
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    output = BytesIO(); image.save(output)
    return output.getvalue()
