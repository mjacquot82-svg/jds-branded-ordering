"""Drawing primitives for JDS generated starter illustrations (no external assets).

Everything is drawn procedurally with Pillow at 2x resolution and downsampled,
so the output is original, license-free, and reproducible from this file.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 2400  # working canvas (downsampled to 1200 on save)


def rgb(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def mix(a: str, b: str, t: float) -> str:
    ca, cb = rgb(a), rgb(b)
    return "#" + "".join(f"{round(ca[i] + (cb[i] - ca[i]) * t):02x}" for i in range(3))


def blank_mask() -> Image.Image:
    return Image.new("L", (S, S), 0)


def ellipse_mask(cx: float, cy: float, rx: float, ry: float) -> Image.Image:
    mask = blank_mask()
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    return mask


def poly_mask(points) -> Image.Image:
    mask = blank_mask()
    ImageDraw.Draw(mask).polygon([tuple(p) for p in points], fill=255)
    return mask


def union(*masks: Image.Image) -> Image.Image:
    out = masks[0]
    for mask in masks[1:]:
        out = ImageChops.lighter(out, mask)
    return out


def intersect(a: Image.Image, b: Image.Image) -> Image.Image:
    return ImageChops.multiply(a, b)


def subtract(a: Image.Image, b: Image.Image) -> Image.Image:
    return ImageChops.subtract(a, b)


def linear_alpha(box, start: float, end: float, direction: str = "h") -> Image.Image:
    """Full-canvas L image ramping start→end (0..1) across box along x ('h') or y ('v')."""
    x0, y0, x1, y1 = box
    c0, c1 = (x0, x1) if direction == "h" else (y0, y1)
    span = max(1.0, c1 - c0)
    values = []
    for c in range(S):
        t = min(1.0, max(0.0, (c - c0) / span))
        values.append(int(255 * (start + (end - start) * t)))
    if direction == "h":
        line = Image.new("L", (S, 1)); line.putdata(values)
    else:
        line = Image.new("L", (1, S)); line.putdata(values)
    return line.resize((S, S), Image.Resampling.NEAREST)


def paint(base: Image.Image, mask: Image.Image, color: str, alpha: float = 1.0) -> None:
    layer = Image.new("RGBA", (S, S), rgb(color))
    a = mask if alpha >= 1 else mask.point(lambda v: int(v * alpha))
    layer.putalpha(a)
    base.alpha_composite(layer)


def paint_gradient(base: Image.Image, mask: Image.Image, c1: str, c2: str, box, direction: str = "h") -> None:
    paint(base, mask, c1)
    ramp = linear_alpha(box, 0.0, 1.0, direction)
    paint(base, intersect(mask, ramp), c2)


def shade(base: Image.Image, mask: Image.Image, box, color: str = "#000000", start: float = 0.0, end: float = 0.35, direction: str = "h") -> None:
    paint(base, intersect(mask, linear_alpha(box, start, end, direction)), color)


def blur(mask: Image.Image, radius: float) -> Image.Image:
    return mask.filter(ImageFilter.GaussianBlur(radius))


def shadow(base: Image.Image, cx: float, cy: float, rx: float, ry: float, strength: float = 0.28, radius: float = 40) -> None:
    paint(base, blur(ellipse_mask(cx, cy, rx, ry), radius), "#3b2a1e", strength)


def stroke(base: Image.Image, points, color: str, width: int, alpha: float = 1.0, radius: float = 0) -> None:
    mask = blank_mask()
    ImageDraw.Draw(mask).line([tuple(p) for p in points], fill=255, width=width, joint="curve")
    for p in (points[0], points[-1]):
        ImageDraw.Draw(mask).ellipse((p[0] - width / 2, p[1] - width / 2, p[0] + width / 2, p[1] + width / 2), fill=255)
    if radius:
        mask = blur(mask, radius)
    paint(base, mask, color, alpha)


def ring(base: Image.Image, cx, cy, rx, ry, color: str, width: int, alpha: float = 1.0) -> None:
    mask = blank_mask()
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=255, width=width)
    paint(base, mask, color, alpha)


def rounded_rect_mask(x0, y0, x1, y1, radius, angle: float = 0.0, center=None) -> Image.Image:
    mask = blank_mask()
    ImageDraw.Draw(mask).rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=255)
    if angle:
        cx, cy = center or ((x0 + x1) / 2, (y0 + y1) / 2)
        mask = mask.rotate(angle, center=(cx, cy), resample=Image.Resampling.BICUBIC)
    return mask


def vessel_mask(cx, top_y, bot_y, top_rx, bot_rx, curve: float = 1.0, rim: float = 0.26, steps: int = 60):
    """Side silhouette of a round vessel (cup, glass, bowl) incl. top & bottom ellipses."""
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        y = top_y + (bot_y - top_y) * t
        rx = top_rx + (bot_rx - top_rx) * (t ** curve)
        left.append((cx - rx, y))
        right.append((cx + rx, y))
    bottom = [(cx + bot_rx * math.cos(a), bot_y + bot_rx * rim * math.sin(a)) for a in [math.pi * k / 40 for k in range(40, -1, -1)]]
    bottom = list(reversed(bottom))
    outline = left + bottom[1:-1] + list(reversed(right))
    return union(poly_mask(outline), ellipse_mask(cx, top_y, top_rx, top_rx * rim), ellipse_mask(cx, bot_y, bot_rx, bot_rx * rim))


def vessel_rx_at(y, top_y, bot_y, top_rx, bot_rx, curve=1.0):
    t = min(1.0, max(0.0, (y - top_y) / (bot_y - top_y)))
    return top_rx + (bot_rx - top_rx) * (t ** curve)


def background(palette: dict) -> Image.Image:
    base = Image.new("RGBA", (S, S), rgb(palette["bg_top"]))
    ramp = linear_alpha((0, 0, S, S), 0, 1, "v")
    paint(base, ramp, palette["bg_bottom"])
    # soft halo behind the subject
    paint(base, blur(ellipse_mask(S / 2, S * 0.47, S * 0.36, S * 0.36), 120), palette["halo"], 0.85)
    # table line / surface
    surface = poly_mask([(0, S * 0.74), (S, S * 0.74), (S, S), (0, S)])
    paint(base, blur(surface, 30), palette["surface"], 0.55)
    return base


def steam(base: Image.Image, cx: float, top: float, count: int = 3, height: float = 380, color: str = "#ffffff") -> None:
    rnd = random.Random(int(cx + top))
    for index in range(count):
        x = cx + (index - (count - 1) / 2) * 110
        phase = rnd.random() * math.pi
        pts = [(x + math.sin(phase + t * 3.2) * 38, top - t * height) for t in [k / 24 for k in range(25)]]
        stroke(base, pts, color, 34, alpha=0.55, radius=10)


def speckles(base: Image.Image, mask: Image.Image, color: str, count: int, size: tuple[int, int], seed: int, alpha: float = 1.0) -> None:
    rnd = random.Random(seed)
    bbox = mask.getbbox()
    if not bbox:
        return
    dots = blank_mask()
    draw = ImageDraw.Draw(dots)
    for _ in range(count * 4):
        x, y = rnd.uniform(bbox[0], bbox[2]), rnd.uniform(bbox[1], bbox[3])
        if mask.getpixel((int(x), int(y))) < 200:
            continue
        r = rnd.uniform(*size)
        draw.ellipse((x - r, y - r * 0.8, x + r, y + r * 0.8), fill=255)
        count -= 1
        if count <= 0:
            break
    paint(base, intersect(dots, mask), color, alpha)


def finish(base: Image.Image) -> Image.Image:
    return base.convert("RGB").resize((S // 2, S // 2), Image.Resampling.LANCZOS)
