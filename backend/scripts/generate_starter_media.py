"""Generate the JDS illustrated starter image pack (placeholder artwork, v1).

Usage (from backend/):  python scripts/generate_starter_media.py [--out DIR] [--only key,key]

Output: <out>/cafe-restaurant/<key>-v1.webp at 1200×1200. All artwork is drawn
procedurally here — no photos, stock, scraped, or third-party assets — so it is
original to JDS and safe to ship. These are clearly-identified PLACEHOLDERS; see
docs/STARTER_MEDIA_ASSET_MANIFEST.md for the licensed photography still required.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from starter_art import (  # noqa: E402
    S, background, blank_mask, blur, ellipse_mask, finish, intersect, linear_alpha, mix, paint,
    paint_gradient, poly_mask, ring, rounded_rect_mask, shade, shadow, speckles, steam, stroke,
    subtract, union, vessel_mask, vessel_rx_at,
)
from PIL import Image, ImageDraw  # noqa: E402

CX = S / 2
FRAME = (330, 420, 2070, 2160)
PALETTES = {
    "coffee": dict(bg_top="#f4e9dd", bg_bottom="#e8d3bf", halo="#fbf3ea", surface="#dcc2a8"),
    "tea": dict(bg_top="#f1ece0", bg_bottom="#e2d6bf", halo="#faf6ec", surface="#d6c7a7"),
    "cold": dict(bg_top="#e6f2ec", bg_bottom="#cfe3d8", halo="#f4faf6", surface="#b9d4c5"),
    "bakery": dict(bg_top="#f8ebdc", bg_bottom="#efd6bd", halo="#fdf5ec", surface="#e2c19f"),
    "breakfast": dict(bg_top="#f6eedb", bg_bottom="#e9dbbd", halo="#fcf8ee", surface="#d9c59c"),
    "lunch": dict(bg_top="#ebf0e1", bg_bottom="#d7e1c9", halo="#f6f9f0", surface="#c2cfae"),
    "sweet": dict(bg_top="#f8e9e6", bg_bottom="#edd2cd", halo="#fdf4f2", surface="#e0bab3"),
}
CERAMIC = ("#ffffff", "#e9e3da")
ESPRESSO, CREMA, MILK, FOAM = "#3a2418", "#b8773f", "#f6ead9", "#fbf5ec"


# ---------------------------------------------------------------- vessels
def plate(base, cx, cy, rx, color="#fbfaf7", rim_color="#e7e1d7"):
    ry = rx * 0.27
    shadow(base, cx, cy + ry * 0.35, rx * 1.02, ry * 1.1, 0.25, 36)
    paint(base, ellipse_mask(cx, cy, rx, ry), rim_color)
    paint(base, ellipse_mask(cx, cy - ry * 0.06, rx * 0.98, ry * 0.92), color)
    paint(base, ellipse_mask(cx, cy, rx * 0.66, ry * 0.62), mix(color, rim_color, 0.45))
    paint(base, ellipse_mask(cx, cy - ry * 0.04, rx * 0.63, ry * 0.57), color)


def cup(base, *, top_y, bot_y, top_rx, bot_rx, body=CERAMIC, liquid=None, surface=None, saucer=True, handle=True, curve=1.4, mug=False):
    rim = 0.26
    if saucer:
        plate(base, CX, bot_y + 30, top_rx * 1.55)
    else:
        shadow(base, CX, bot_y + 25, bot_rx * 1.25, bot_rx * 0.3, 0.3, 30)
    if handle:
        hy = top_y + (bot_y - top_y) * (0.42 if not mug else 0.45)
        hx = CX + vessel_rx_at(hy, top_y, bot_y, top_rx, bot_rx, curve) + (40 if not mug else 60)
        hrx, hry = (130, 150) if not mug else (150, 200)
        ring(base, hx, hy, hrx, hry, body[1], 64 if not mug else 76)
        ring(base, hx - 6, hy - 6, hrx - 6, hry - 6, body[0], 40 if not mug else 50)
    m = vessel_mask(CX, top_y, bot_y, top_rx, bot_rx, curve, rim)
    box = (CX - top_rx, top_y, CX + top_rx, bot_y)
    paint_gradient(base, m, body[0], body[1], box, "h")
    shade(base, m, box, "#000000", 0.0, 0.14, "h")
    # glossy highlight
    hl = poly_mask([(CX - top_rx * 0.72, top_y + 60), (CX - top_rx * 0.55, top_y + 60), (CX - bot_rx * 0.62, bot_y - 50), (CX - bot_rx * 0.78, bot_y - 60)])
    paint(base, blur(hl, 18), "#ffffff", 0.55)
    # rim + interior
    paint(base, ellipse_mask(CX, top_y, top_rx, top_rx * rim), mix(body[1], "#ffffff", 0.3))
    inner_rx = top_rx - 26
    paint(base, ellipse_mask(CX, top_y + 4, inner_rx, inner_rx * rim), mix(body[1], "#000000", 0.08))
    if liquid:
        lrx = inner_rx - 18
        paint(base, ellipse_mask(CX, top_y + 18, lrx, lrx * rim * 0.95), liquid)
        if surface:
            surface(base, CX, top_y + 18, lrx, lrx * rim * 0.95)
    return m


def glass(base, *, top_y, bot_y, top_rx, bot_rx, fill_y, liquid_top, liquid_bottom, ice=0, straw=None, garnish=None, curve=1.0, layers=None):
    rim = 0.24
    shadow(base, CX, bot_y + 18, bot_rx * 1.3, bot_rx * 0.3, 0.26, 30)
    body = vessel_mask(CX, top_y, bot_y, top_rx, bot_rx, curve, rim)
    box = (CX - top_rx, top_y, CX + top_rx, bot_y)
    paint(base, body, "#ffffff", 0.28)
    frx = vessel_rx_at(fill_y, top_y, bot_y, top_rx, bot_rx, curve) - 14
    liquid = intersect(vessel_mask(CX, fill_y, bot_y - 22, frx, bot_rx - 16, curve, rim), body)
    paint_gradient(base, liquid, liquid_top, liquid_bottom, (0, fill_y, S, bot_y), "v")
    shade(base, liquid, box, "#000000", 0.0, 0.18, "h")
    paint(base, ellipse_mask(CX, fill_y, frx, frx * rim), mix(liquid_top, "#ffffff", 0.18))
    if ice:
        rnd = random.Random(ice)
        for i in range(ice):
            size = rnd.uniform(150, 200)
            x = CX + rnd.uniform(-frx * 0.55, frx * 0.55)
            y = fill_y + rnd.uniform(-40, 260) + i * 40
            cube = intersect(rounded_rect_mask(x - size / 2, y - size / 2, x + size / 2, y + size / 2, 36, rnd.uniform(-25, 25)), body)
            paint(base, cube, "#ffffff", 0.42)
            edge = subtract(cube, rounded_rect_mask(x - size / 2 + 22, y - size / 2 + 22, x + size / 2 - 10, y + size / 2 - 10, 26))
            paint(base, edge, "#ffffff", 0.5)
    if layers:
        layers(base, liquid)
    if garnish:
        garnish(base)
    if straw:
        color, stripe = straw
        sm = rounded_rect_mask(CX + 40, top_y - 420, CX + 100, fill_y + 400, 30, -12, (CX + 70, top_y))
        paint(base, sm, color)
        if stripe:
            for k in range(8):
                y0 = top_y - 400 + k * 110
                band = intersect(sm, poly_mask([(0, y0), (S, y0 - 60), (S, y0 - 20), (0, y0 + 40)]))
                paint(base, band, stripe)
        shade(base, sm, (CX + 40, 0, CX + 110, S), "#000000", 0.0, 0.25, "h")
    # glass edges + highlight
    edge = subtract(body, vessel_mask(CX, top_y + 8, bot_y - 14, top_rx - 18, bot_rx - 18, curve, rim))
    paint(base, edge, "#ffffff", 0.75)
    ring(base, CX, top_y, top_rx, top_rx * rim, "#ffffff", 14, 0.9)
    hl = poly_mask([(CX - top_rx * 0.78, top_y + 80), (CX - top_rx * 0.66, top_y + 80), (CX - bot_rx * 0.64, bot_y - 80), (CX - bot_rx * 0.74, bot_y - 80)])
    paint(base, blur(hl, 10), "#ffffff", 0.6)
    return body


def bowl(base, *, rim_y, rx, depth, color=("#ffffff", "#e6ded2"), accent=None):
    rim = 0.3
    shadow(base, CX, rim_y + depth + 10, rx * 0.8, rx * 0.2, 0.28, 34)
    body = union(poly_mask([(CX - rx, rim_y)] + [(CX + rx * math.cos(a), rim_y + depth * math.sin(a)) for a in [math.pi * k / 60 for k in range(60, -1, -1)]] + [(CX + rx, rim_y)]),
                 ellipse_mask(CX, rim_y, rx, rx * rim))
    paint_gradient(base, body, color[0], color[1], (CX - rx, 0, CX + rx, S), "h")
    shade(base, body, (0, rim_y, S, rim_y + depth), "#000000", 0.0, 0.12, "v")
    if accent:
        band = intersect(body, poly_mask([(0, rim_y + depth * 0.18), (S, rim_y + depth * 0.18), (S, rim_y + depth * 0.3), (0, rim_y + depth * 0.3)]))
        paint(base, band, accent)
    paint(base, blur(poly_mask([(CX - rx * 0.8, rim_y + 60), (CX - rx * 0.68, rim_y + 60), (CX - rx * 0.45, rim_y + depth * 0.75), (CX - rx * 0.58, rim_y + depth * 0.7)]), 16), "#ffffff", 0.5)
    paint(base, ellipse_mask(CX, rim_y, rx, rx * rim), mix(color[1], "#ffffff", 0.4))
    return rx - 30, rx * rim - 12


# ------------------------------------------------------------ latte art
def heart(base, cx, cy, rx, ry, color=MILK, scale=0.52):
    m = blank_mask(); d = ImageDraw.Draw(m)
    w, h = rx * scale, ry * scale * 1.1
    d.ellipse((cx - w * 1.0, cy - h * 0.9, cx + w * 0.08, cy + h * 0.3), fill=255)
    d.ellipse((cx - w * 0.08, cy - h * 0.9, cx + w * 1.0, cy + h * 0.3), fill=255)
    d.polygon([(cx - w * 0.97, cy - h * 0.15), (cx + w * 0.97, cy - h * 0.15), (cx, cy + h * 1.15)], fill=255)
    paint(base, blur(m, 6), color)


def rosetta(base, cx, cy, rx, ry):
    for i, s in enumerate([0.74, 0.62, 0.5, 0.39, 0.29]):
        y = cy - ry * 0.55 + i * ry * 0.26
        paint(base, blur(ellipse_mask(cx, y, rx * s, ry * s * 0.62), 5), MILK)
        paint(base, blur(ellipse_mask(cx, y + ry * 0.06, rx * s * 0.82, ry * s * 0.42), 5), CREMA, 0.9)
    paint(base, blur(ellipse_mask(cx, cy + ry * 0.6, rx * 0.2, ry * 0.2), 4), MILK)
    stroke(base, [(cx, cy - ry * 0.75), (cx, cy + ry * 0.75)], CREMA, 14)


def crema_surface(base, cx, cy, rx, ry):
    paint(base, blur(ellipse_mask(cx, cy, rx * 0.98, ry * 0.95), 10), CREMA)
    paint(base, blur(ellipse_mask(cx - rx * 0.1, cy - ry * 0.1, rx * 0.6, ry * 0.5), 26), "#d4955a", 0.8)


# -------------------------------------------------------------- drinks
def art_brewed_coffee(base):
    steam(base, CX, 900)
    cup(base, top_y=1000, bot_y=1720, top_rx=330, bot_rx=300, body=("#5f7a68", "#3f5647"), liquid=ESPRESSO, saucer=False, mug=True, curve=1.0,
        surface=lambda b, x, y, rx, ry: paint(b, blur(ellipse_mask(x - rx * 0.2, y - ry * 0.2, rx * 0.5, ry * 0.4), 20), "#6a4330", 0.9))


def art_espresso(base):
    steam(base, CX, 1080, count=2, height=300)
    cup(base, top_y=1250, bot_y=1640, top_rx=250, bot_rx=170, liquid=ESPRESSO, surface=crema_surface, curve=1.6)
    for dx, dy, rot in ((-520, 1790, 30), (560, 1760, -20)):
        bean = rounded_rect_mask(CX + dx - 48, dy - 32, CX + dx + 48, dy + 32, 32, rot)
        paint(base, bean, "#4a2c1d"); stroke(base, [(CX + dx - 30, dy + 8), (CX + dx + 30, dy - 8)], "#2b170e", 8)


def art_latte(base):
    cup(base, top_y=1080, bot_y=1650, top_rx=420, bot_rx=250, liquid=CREMA, curve=1.8,
        surface=lambda b, x, y, rx, ry: (paint(b, ellipse_mask(x, y, rx, ry), "#c58a52"), rosetta(b, x, y, rx, ry)))


def art_cappuccino(base):
    def foam(b, x, y, rx, ry):
        paint(b, blur(ellipse_mask(x, y - 10, rx, ry * 1.05), 6), FOAM)
        paint(b, blur(ellipse_mask(x, y - 12, rx * 0.72, ry * 0.7), 30), "#b98056", 0.55)
        speckles(b, ellipse_mask(x, y - 12, rx * 0.72, ry * 0.7), "#6e4128", 160, (4, 9), 7, 0.7)
        heart(b, x, y - 10, rx, ry, FOAM, 0.34)
    steam(base, CX, 900, count=2, height=260)
    cup(base, top_y=1100, bot_y=1650, top_rx=380, bot_rx=240, liquid=FOAM, surface=foam, curve=1.7, body=("#fbf7f1", "#e6d9c8"))


def art_iced_latte(base):
    glass(base, top_y=820, bot_y=1760, top_rx=330, bot_rx=270, fill_y=930, liquid_top="#efe1cc", liquid_bottom="#8a5634", ice=5, straw=("#e9e1d3", "#b5835a"))


def art_iced_coffee(base):
    glass(base, top_y=820, bot_y=1760, top_rx=330, bot_rx=270, fill_y=930, liquid_top="#6b3f24", liquid_bottom="#2d1a10", ice=5, straw=("#2f3b33", None))


def art_hot_tea(base):
    steam(base, CX - 40, 1000, count=2, height=300)
    cup(base, top_y=1150, bot_y=1650, top_rx=360, bot_rx=230, liquid="#b5652a", curve=1.8, body=("#fdfbf7", "#e5dccd"),
        surface=lambda b, x, y, rx, ry: paint(b, blur(ellipse_mask(x - rx * 0.2, y - ry * 0.2, rx * 0.55, ry * 0.45), 24), "#d98f4c", 0.8))
    stroke(base, [(CX + 120, 1180), (CX + 250, 1120), (CX + 400, 1210), (CX + 470, 1330)], "#f3efe6", 8)
    tag = rounded_rect_mask(CX + 420, 1330, CX + 540, 1470, 14, 8)
    paint(base, tag, "#e8b44d"); paint(base, rounded_rect_mask(CX + 445, 1360, CX + 515, 1440, 8, 8), "#f6d98f")
    lemon(base, CX - 470, 1760, 110, flat=True)


def lemon(base, cx, cy, r, flat=False, color="#f2c230", pith="#fbeea6"):
    ry = r * (0.35 if flat else 1)
    paint(base, ellipse_mask(cx, cy, r, ry), color)
    paint(base, ellipse_mask(cx, cy, r * 0.86, ry * 0.86), pith)
    for k in range(8):
        a = k * math.pi / 4
        seg = poly_mask([(cx, cy), (cx + r * 0.8 * math.cos(a + 0.33), cy + ry * 0.8 * math.sin(a + 0.33)), (cx + r * 0.8 * math.cos(a - 0.33), cy + ry * 0.8 * math.sin(a - 0.33))])
        paint(base, blur(seg, 3), mix(color, "#ffffff", 0.25))


def art_hot_chocolate(base):
    def cream(b, x, y, rx, ry):
        for i, (dy, s) in enumerate(((0, 1.0), (-70, 0.78), (-135, 0.56), (-190, 0.34))):
            paint(b, blur(ellipse_mask(x, y + dy - 30, rx * s, ry * s * 1.9), 4), "#fffaf3")
            shade(b, ellipse_mask(x, y + dy - 30, rx * s, ry * s * 1.9), (x - rx, 0, x + rx, S), "#b39b86", 0.0, 0.35, "h")
        speckles(b, ellipse_mask(x, y - 120, rx * 0.8, ry * 2.2), "#5a3423", 140, (5, 10), 3, 0.85)
        for mx, my in ((-150, -40), (140, -10), (30, 30)):
            paint(b, rounded_rect_mask(x + mx - 38, y + my - 30, x + mx + 38, y + my + 30, 14, 20), "#fdf1f4")
    cup(base, top_y=1150, bot_y=1760, top_rx=320, bot_rx=290, body=("#c9573f", "#9a3d2c"), liquid="#5b3322", surface=cream, saucer=False, mug=True, curve=1.0)


def art_iced_tea(base):
    def garnish(b):
        lemon(b, CX - 220, 1010, 150, flat=False)
        for dx, rot in ((150, 30), (230, -10)):
            paint(b, rounded_rect_mask(CX + dx - 40, 840, CX + dx + 40, 980, 40, rot), "#4f8a4b")
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=260, fill_y=960, liquid_top="#d98a35", liquid_bottom="#8b3f15", ice=4, garnish=garnish)


def art_lemonade(base):
    def garnish(b):
        lemon(b, CX - 90, 1300, 120); lemon(b, CX + 120, 1480, 105)
        lemon(b, CX + 250, 860, 150)
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=260, fill_y=960, liquid_top="#fbeaa0", liquid_bottom="#f2cf55", ice=3, straw=("#f6f1e3", "#e0a22c"), garnish=garnish)


def art_smoothie(base):
    def garnish(b):
        for x, y, r, c in ((CX - 150, 900, 70, "#b32645"), (CX - 40, 870, 60, "#3a2d6b"), (CX + 70, 905, 64, "#b32645")):
            paint(b, ellipse_mask(x, y, r, r), c); paint(b, ellipse_mask(x - r * 0.3, y - r * 0.3, r * 0.25, r * 0.2), "#ffffff", 0.6)
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=240, fill_y=920, liquid_top="#e17aa0", liquid_bottom="#a8336a", straw=("#f4e7ee", "#c9477a"), garnish=garnish, curve=1.2)


# ------------------------------------------------------------- bakery
def croissant(base, cx, cy, scale=1.0, color=("#f2b866", "#b0632a")):
    """Crescent body (outer ellipse minus offset ellipse) with layered ridges."""
    rx, ry = 560 * scale, 300 * scale
    outer = ellipse_mask(cx, cy, rx, ry)
    inner = ellipse_mask(cx, cy + 330 * scale, rx * 0.5, ry * 0.8)
    body = subtract(outer, inner)
    body = blur(body, int(30 * scale)).point(lambda v: 255 if v > 128 else 0)
    shadow(base, cx, cy + ry * 0.7, rx * 0.9, ry * 0.25, 0.3, 30)
    paint_gradient(base, body, color[0], color[1], (0, cy - ry, S, cy + ry), "v")
    shade(base, body, (cx - rx, 0, cx + rx, S), "#6b3514", 0.25, 0.0, "h")
    shade(base, body, (cx - rx, 0, cx + rx, S), "#6b3514", 0.0, 0.25, "h")
    for k in range(-4, 5):
        ang = math.pi / 2 + k * 0.3
        x0 = cx + rx * 1.05 * math.cos(ang - math.pi) * -1
        ox, oy = cx - rx * math.cos(ang) * 1.02, cy - ry * math.sin(ang) * 1.02
        ix, iy = cx - rx * 0.5 * math.cos(ang) * 0.95, cy + 330 * scale - ry * 0.8 * math.sin(ang) * 0.95
        mx, my = (ox + ix) / 2 + 30 * scale * (1 if k > 0 else -1 if k < 0 else 0), (oy + iy) / 2
        line = blank_mask(); ImageDraw.Draw(line).line([(ox, oy), (mx, my), (ix, iy)], fill=255, width=int(20 * scale), joint="curve")
        paint(base, intersect(blur(line, 6), body), "#7e3f16", 0.55)
        hl = blank_mask(); ImageDraw.Draw(hl).line([(ox + 26 * scale, oy + 10), (mx + 24 * scale, my)], fill=255, width=int(24 * scale))
        paint(base, intersect(blur(hl, 10), body), "#ffe2a6", 0.55)
    paint(base, intersect(blur(ellipse_mask(cx - rx * 0.15, cy - ry * 0.62, rx * 0.45, ry * 0.18), 26), body), "#fff0c9", 0.6)


def art_plain_croissant(base):
    plate(base, CX, 1580, 720)
    croissant(base, CX, 1420)


def art_filled_croissant_danish(base):
    plate(base, CX, 1570, 700)
    for dx, dy, s in ((-260, 1330, 0.95), (280, 1400, 1.0)):
        r = 250 * s
        paint_gradient(base, ellipse_mask(CX + dx, dy, r, r * 0.62), "#efb462", "#b86b2c", (0, dy - r, S, dy + r), "v")
        for k in range(3):
            ring(base, CX + dx, dy, r * (0.85 - k * 0.22), r * 0.62 * (0.85 - k * 0.22), "#a45e27", 10, 0.6)
        paint(base, ellipse_mask(CX + dx, dy - 10, r * 0.4, r * 0.25), "#b52a3a" if dx < 0 else "#e7a72c")
        paint(base, ellipse_mask(CX + dx - r * 0.12, dy - 24, r * 0.14, r * 0.07), "#ffffff", 0.5)
        for k in range(4):
            y = dy - r * 0.4 + k * r * 0.22
            stroke(base, [(CX + dx - r * 0.7, y), (CX + dx - r * 0.2, y + 30), (CX + dx + r * 0.3, y - 10), (CX + dx + r * 0.7, y + 20)], "#fff8ec", 14, 0.9)


def art_muffin(base):
    shadow(base, CX, 1760, 330, 70, 0.3, 30)
    wrap = poly_mask([(CX - 330, 1230), (CX + 330, 1230), (CX + 250, 1760), (CX - 250, 1760)])
    paint_gradient(base, wrap, "#9fb7c9", "#6c8ba3", (CX - 330, 0, CX + 330, S), "h")
    for k in range(-6, 7):
        stroke(base, [(CX + k * 52, 1240), (CX + k * 40, 1750)], "#58748b", 8, 0.55)
    top = union(ellipse_mask(CX, 1210, 400, 220), ellipse_mask(CX - 230, 1150, 170, 150), ellipse_mask(CX + 220, 1140, 180, 160), ellipse_mask(CX, 1060, 260, 190))
    paint_gradient(base, top, "#e6a55a", "#a8612b", (0, 900, S, 1400), "v")
    paint(base, blur(ellipse_mask(CX - 90, 1030, 220, 90), 30), "#fbd497", 0.6)
    rnd = random.Random(11)
    for _ in range(14):
        x, y = CX + rnd.uniform(-330, 330), 1000 + rnd.uniform(0, 330)
        if top.getpixel((int(x), int(y))) > 200:
            r = rnd.uniform(26, 40)
            paint(base, ellipse_mask(x, y, r, r * 0.9), "#3e3a73"); paint(base, ellipse_mask(x - r * 0.3, y - r * 0.3, r * 0.3, r * 0.25), "#9c9ad6", 0.8)


def cookie(base, cx, cy, r, seed):
    shadow(base, cx, cy + r * 0.2, r * 1.02, r * 0.4, 0.25, 26)
    m = ellipse_mask(cx, cy, r, r * 0.42)
    side = union(m, ellipse_mask(cx, cy + 36, r, r * 0.42))
    paint(base, side, "#a86a2f")
    paint_gradient(base, m, "#e9b471", "#c98642", (cx - r, 0, cx + r, S), "h")
    rnd = random.Random(seed)
    for _ in range(9):
        x, y = cx + rnd.uniform(-r * 0.7, r * 0.7), cy + rnd.uniform(-r * 0.28, r * 0.28)
        if m.getpixel((int(x), int(y))) > 200:
            w = rnd.uniform(30, 52)
            pts = [(x + w * math.cos(a) * rnd.uniform(0.7, 1.2), y + w * 0.6 * math.sin(a) * rnd.uniform(0.7, 1.2)) for a in [k * math.pi / 3 for k in range(6)]]
            paint(base, poly_mask(pts), "#4a2616")
    speckles(base, m, "#b37436", 60, (4, 8), seed + 1, 0.8)


def art_cookie(base):
    cookie(base, CX - 60, 1560, 440, 4)
    cookie(base, CX + 40, 1330, 420, 5)
    cookie(base, CX - 20, 1110, 400, 6)


def art_donut(base):
    plate(base, CX, 1560, 720)
    for dx, dy, glaze in ((-60, 1400, "#f19bb4"), (120, 1180, "#6b3b2a")):
        body = subtract(ellipse_mask(CX + dx, dy, 380, 190), ellipse_mask(CX + dx, dy - 10, 110, 50))
        side = subtract(ellipse_mask(CX + dx, dy + 50, 380, 190), ellipse_mask(CX + dx, dy - 10, 110, 50))
        paint(base, union(side, body), "#c98845")
        pts = [(CX + dx + 330 * math.cos(a) + 14 * math.sin(a * 7), dy - 8 + 160 * math.sin(a) + 12 * math.cos(a * 9)) for a in [k * math.pi / 60 for k in range(120)]]
        g = subtract(poly_mask(pts), ellipse_mask(CX + dx, dy - 12, 135, 64))
        paint(base, g, glaze)
        paint(base, blur(intersect(g, ellipse_mask(CX + dx - 110, dy - 90, 170, 50)), 12), "#ffffff", 0.45)
        if dx < 0:
            rnd = random.Random(9)
            for _ in range(40):
                x, y = CX + dx + rnd.uniform(-300, 300), dy + rnd.uniform(-140, 140)
                if g.getpixel((int(x), int(y))) > 200:
                    paint(base, rounded_rect_mask(x - 20, y - 7, x + 20, y + 7, 7, rnd.uniform(0, 180)), rnd.choice(["#ffffff", "#f7d048", "#6cc3c9", "#7b5bd6"]))


def art_brownie(base):
    plate(base, CX, 1600, 700)
    for dx, dy in ((-210, 1450), (200, 1400), (0, 1180)):
        w, d, h = 300, 120, 170
        top = poly_mask([(CX + dx - w / 2, dy - h), (CX + dx + w / 2 - 60, dy - h - d / 2), (CX + dx + w / 2 + 40, dy - h + d / 3), (CX + dx - w / 2 + 100, dy - h + d)])
        front = poly_mask([(CX + dx - w / 2, dy - h), (CX + dx - w / 2 + 100, dy - h + d), (CX + dx - w / 2 + 100, dy + d), (CX + dx - w / 2, dy)])
        side = poly_mask([(CX + dx - w / 2 + 100, dy - h + d), (CX + dx + w / 2 + 40, dy - h + d / 3), (CX + dx + w / 2 + 40, dy + d / 3), (CX + dx - w / 2 + 100, dy + d)])
        paint(base, front, "#4b2a1a"); paint(base, side, "#3a2014"); paint(base, top, "#6a3d26")
        speckles(base, top, "#8d5a3b", 40, (5, 12), dx + 3, 0.9)
        speckles(base, union(front, side), "#2a150c", 50, (4, 9), dx + 5, 0.8)


def art_scone(base):
    plate(base, CX, 1580, 680)
    for dx, dy, flip in ((-200, 1420, 1), (230, 1330, -1)):
        pts = [(CX + dx - 260 * flip, dy + 60), (CX + dx + 230 * flip, dy - 20), (CX + dx + 20 * flip, dy - 250)]
        top = poly_mask(pts)
        top = blur(top, 26).point(lambda v: 255 if v > 110 else 0)
        side = poly_mask([(CX + dx - 260 * flip, dy + 60), (CX + dx + 230 * flip, dy - 20), (CX + dx + 230 * flip, dy + 120), (CX + dx - 260 * flip, dy + 190)])
        side = blur(side, 20).point(lambda v: 255 if v > 110 else 0)
        paint(base, side, "#c98a49"); paint_gradient(base, top, "#f2c689", "#d69a55", (0, dy - 250, S, dy + 60), "v")
        speckles(base, union(top, side), "#5d2a52", 12, (14, 22), dx, 1.0)


def art_loaf_slice(base):
    plate(base, CX, 1580, 680)
    for dx, dy in ((-150, 1440), (150, 1340)):
        crust = union(rounded_rect_mask(CX + dx - 250, dy - 260, CX + dx + 250, dy + 120, 50), ellipse_mask(CX + dx, dy - 250, 262, 130))
        crumb = union(rounded_rect_mask(CX + dx - 222, dy - 240, CX + dx + 222, dy + 95, 40), ellipse_mask(CX + dx, dy - 242, 232, 104))
        side = crust.transform(crust.size, 0, (1, 0, -34, 0, 1, -18))
        paint(base, side, "#7a4320"); paint(base, crust, "#96552a")
        paint_gradient(base, crumb, "#dca56a", "#c38748", (0, dy - 340, S, dy + 95), "v")
        speckles(base, crumb, "#9a6232", 80, (5, 10), dx + 40, 0.7)
        speckles(base, crumb, "#6d3c1b", 14, (10, 16), dx + 41, 0.9)


# ------------------------------------------------------ breakfast & lunch
def art_breakfast_sandwich(base):
    plate(base, CX, 1620, 700)
    y = 1470
    paint_gradient(base, union(ellipse_mask(CX, y, 360, 110), ellipse_mask(CX, y + 60, 360, 110)), "#e6bb7d", "#b87d3f", (0, y - 110, S, y + 170), "v")
    paint(base, ellipse_mask(CX - 20, y - 60, 380, 110), "#f7f1e3")
    paint(base, ellipse_mask(CX - 20, y - 70, 170, 70), "#f4b632")
    paint(base, poly_mask([(CX - 300, y - 150), (CX + 320, y - 120), (CX + 360, y - 40), (CX + 380, y + 20), (CX - 340, y - 40)]), "#f29d2a")
    paint(base, ellipse_mask(CX + 10, y - 170, 350, 100), "#b45a3c")
    dome = union(ellipse_mask(CX, y - 270, 370, 180), poly_mask([(CX - 370, y - 270), (CX + 370, y - 270), (CX + 360, y - 200), (CX - 360, y - 200)]), ellipse_mask(CX, y - 200, 360, 70))
    dome = subtract(dome, poly_mask([(0, 0), (S, 0), (S, y - 420), (0, y - 420)])) if False else dome
    paint_gradient(base, dome, "#edc488", "#c08545", (0, y - 450, S, y - 150), "v")
    paint(base, blur(ellipse_mask(CX - 90, y - 360, 200, 60), 20), "#fff1d0", 0.7)
    speckles(base, ellipse_mask(CX, y - 290, 330, 140), "#f7e8c9", 70, (5, 9), 21, 0.9)


def art_deli_sandwich(base):
    plate(base, CX, 1620, 720)
    for dx, dy, flip in ((200, 1500, -1), (-190, 1640, 1)):
        shadow(base, CX + dx, dy + 30, 300, 60, 0.3, 24)
        tip_x = CX + dx + 300 * flip
        layers = [("#e9c58f", 70), ("#6fae4a", 34), ("#e25b4a", 34), ("#f2cf5a", 26), ("#eaa3a0", 44), ("#6fae4a", 30), ("#e9c58f", 70)]
        y = dy
        for color, th in layers:
            m = poly_mask([(CX + dx - 280 * flip, y - th), (tip_x, y - th + 40), (tip_x, y + 40), (CX + dx - 280 * flip, y)])
            if color == "#6fae4a":
                pts = [(CX + dx - 300 * flip + k * 30 * flip, y - th + (18 if k % 2 else -6)) for k in range(21)]
                m = union(m, poly_mask(pts + [(tip_x, y + 40), (CX + dx - 300 * flip, y)]))
            paint(base, m, color)
            y -= th
        crust = poly_mask([(CX + dx - 290 * flip, y), (CX + dx - 280 * flip, y - 30), (tip_x + 10 * flip, y + 10), (tip_x, y + 40)])
        paint(base, crust, "#b77a3a")


def art_wrap(base):
    plate(base, CX, 1620, 720)
    for dx, dy, rot in ((210, 1500, -24), (-210, 1570, 24)):
        shadow(base, CX + dx, dy + 150, 200, 50, 0.3, 24)
        tube = rounded_rect_mask(CX + dx - 150, dy - 330, CX + dx + 150, dy + 150, 140, rot, (CX + dx, dy))
        paint_gradient(base, tube, "#f4dfb3", "#d9b97c", (CX + dx - 160, 0, CX + dx + 160, S), "h")
        speckles(base, tube, "#c49a58", 30, (6, 12), dx, 0.8)
        top = ellipse_mask(CX + dx, dy - 300, 150, 95).rotate(rot, center=(CX + dx, dy))
        paint(base, top, "#f7ecd2")
        for i, (color, s) in enumerate((("#6aa84f", 0.86), ("#f3f0e6", 0.68), ("#e0584a", 0.5), ("#e9c07c", 0.34))):
            paint(base, ellipse_mask(CX + dx + (i % 2) * 10, dy - 300, 150 * s, 95 * s).rotate(rot, center=(CX + dx, dy)), color)


def art_creamy_soup(base):
    rx, ry = bowl(base, rim_y=1230, rx=520, depth=430, color=("#fbfaf6", "#e2dace"), accent="#5f7a68")
    paint(base, ellipse_mask(CX, 1240, rx, ry), "#e0843c")
    paint(base, blur(ellipse_mask(CX - 60, 1225, rx * 0.6, ry * 0.5), 30), "#f0a45b", 0.8)
    stroke(base, [(CX - 160, 1230), (CX - 40, 1200), (CX + 90, 1250), (CX + 200, 1215)], "#fbf1e2", 22, 0.95)
    speckles(base, ellipse_mask(CX + 60, 1225, 140, 40), "#3f7a3a", 18, (8, 14), 5, 1.0)
    bread = rounded_rect_mask(CX + 330, 1560, CX + 700, 1780, 60, -12)
    paint(base, bread, "#c98b4a"); paint(base, rounded_rect_mask(CX + 350, 1580, CX + 680, 1760, 50, -12), "#efd3a0")


def art_green_salad(base):
    rx, ry = bowl(base, rim_y=1280, rx=540, depth=380, color=("#fdfcf9", "#e3dccf"))
    rnd = random.Random(14)
    mound = ellipse_mask(CX, 1180, rx * 0.95, 240)
    for _ in range(46):
        x, y = CX + rnd.uniform(-rx * 0.85, rx * 0.85), 1100 + rnd.uniform(-110, 190)
        if mound.getpixel((int(x), int(y))) < 200:
            continue
        leaf = ellipse_mask(x, y, rnd.uniform(90, 140), rnd.uniform(45, 70)).rotate(rnd.uniform(0, 180), center=(x, y))
        paint(base, leaf, rnd.choice(["#5f9e45", "#7dbb55", "#4b8a3a", "#9bcf6b"]))
        paint(base, blur(leaf, 2).point(lambda v: 255 if 60 < v < 200 else 0), "#3d6e2e", 0.5)
    for x, y in ((CX - 220, 1080), (CX + 180, 1130), (CX + 20, 1000)):
        paint(base, ellipse_mask(x, y, 62, 58), "#d83b32"); paint(base, ellipse_mask(x - 18, y - 18, 16, 12), "#ffffff", 0.6)
    for x, y in ((CX - 60, 1160), (CX + 280, 1030)):
        paint(base, ellipse_mask(x, y, 70, 40), "#cfe6a8"); ring(base, x, y, 70, 40, "#4f8a3a", 10)


def art_toast(base):
    board = rounded_rect_mask(CX - 700, 1360, CX + 700, 1760, 80)
    shadow(base, CX, 1760, 700, 80, 0.25, 30)
    paint_gradient(base, board, "#d6a56c", "#a8733f", (0, 1360, S, 1760), "v")
    for dx, dy in ((-280, 1340), (300, 1300)):
        crust = union(rounded_rect_mask(CX + dx - 280, dy - 250, CX + dx + 280, dy + 170, 60), ellipse_mask(CX + dx - 150, dy - 250, 150, 90), ellipse_mask(CX + dx + 150, dy - 250, 150, 90))
        crumb = union(rounded_rect_mask(CX + dx - 250, dy - 225, CX + dx + 250, dy + 145, 50), ellipse_mask(CX + dx - 140, dy - 240, 125, 70), ellipse_mask(CX + dx + 140, dy - 240, 125, 70))
        paint(base, crust, "#b87534"); paint(base, crumb, "#e8c28a")
        avo = blur(ellipse_mask(CX + dx, dy - 50, 220, 160), 20).point(lambda v: 255 if v > 120 else 0)
        paint(base, avo, "#8fb54c"); paint(base, blur(ellipse_mask(CX + dx - 40, dy - 90, 140, 80), 20), "#b8d46e", 0.8)
        speckles(base, avo, "#c8352b", 30, (6, 10), dx, 1.0)


def art_yogurt_granola(base):
    def garnish(b):
        for x, y, r, c in ((CX - 120, 900, 60, "#b32645"), (CX + 30, 880, 55, "#3a2d6b"), (CX + 140, 905, 58, "#e8a93a")):
            paint(b, ellipse_mask(x, y, r, r * 0.9), c); paint(b, ellipse_mask(x - r * 0.3, y - r * 0.3, r * 0.25, r * 0.2), "#ffffff", 0.6)

    def layers(b, liquid):
        for y0, y1, color in ((1120, 1270, "#c98e4a"), (1270, 1380, "#b1284a"), (1560, 1740, "#c98e4a")):
            wave = [(x, y0 + 16 * math.sin(x / 90)) for x in range(0, S + 1, 40)] + [(S, y1), (0, y1)]
            band = intersect(liquid, poly_mask(wave))
            paint(b, band, color)
            if color == "#c98e4a":
                speckles(b, band, "#8a5a28", 70, (8, 14), y0, 0.9)
                speckles(b, band, "#e7bd7c", 50, (6, 10), y0 + 1, 0.9)
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=250, fill_y=930, liquid_top="#fbf7ef", liquid_bottom="#f1e9da", garnish=garnish, curve=1.1, layers=layers)


# name -> (palette, painter)
ARTWORK = {
    "brewed-coffee": ("coffee", art_brewed_coffee),
    "espresso": ("coffee", art_espresso),
    "latte": ("coffee", art_latte),
    "cappuccino": ("coffee", art_cappuccino),
    "iced-latte": ("cold", art_iced_latte),
    "iced-coffee": ("cold", art_iced_coffee),
    "hot-tea": ("tea", art_hot_tea),
    "hot-chocolate": ("tea", art_hot_chocolate),
    "iced-tea": ("cold", art_iced_tea),
    "lemonade-fruit-cooler": ("cold", art_lemonade),
    "smoothie": ("cold", art_smoothie),
    "plain-croissant": ("bakery", art_plain_croissant),
    "filled-croissant-danish": ("bakery", art_filled_croissant_danish),
    "muffin": ("bakery", art_muffin),
    "cookie": ("bakery", art_cookie),
    "donut": ("sweet", art_donut),
    "brownie-dessert-square": ("sweet", art_brownie),
    "scone": ("bakery", art_scone),
    "loaf-slice": ("bakery", art_loaf_slice),
    "breakfast-sandwich": ("breakfast", art_breakfast_sandwich),
    "toast": ("breakfast", art_toast),
    "yogurt-granola": ("breakfast", art_yogurt_granola),
    "deli-sandwich": ("lunch", art_deli_sandwich),
    "wrap": ("lunch", art_wrap),
    "creamy-soup": ("lunch", art_creamy_soup),
    "green-salad": ("lunch", art_green_salad),
}


# ================================================== M4 additions (44 archetypes)
def bun(base, cx, cy, rx, ry, top=("#eab36a", "#b8722f"), seeds=True):
    m = union(ellipse_mask(cx, cy, rx, ry), poly_mask([(cx - rx, cy), (cx + rx, cy), (cx + rx * 0.98, cy + ry * 0.25), (cx - rx * 0.98, cy + ry * 0.25)]))
    paint_gradient(base, m, top[0], top[1], (0, cy - ry, S, cy + ry * 0.3), "v")
    paint(base, blur(ellipse_mask(cx - rx * 0.3, cy - ry * 0.55, rx * 0.4, ry * 0.25), 24), "#fff0cf", 0.6)
    if seeds:
        rnd = random.Random(int(cx + cy))
        for _ in range(34):
            x, y = cx + rnd.uniform(-rx * 0.8, rx * 0.8), cy + rnd.uniform(-ry * 0.85, -ry * 0.05)
            if m.getpixel((int(x), int(y))) > 200:
                paint(base, ellipse_mask(x, y, 13, 7).rotate(rnd.uniform(0, 180), center=(x, y)), "#fbf0d8")


def wedge(base, cx, cy, w=620, h=300, d=230, layers=(("#f3e6c6", 1.0),), top="#f6ecd2", crust=None, tip_left=True):
    """Isometric cake/pie wedge: triangular top, front face with horizontal layers, side face."""
    s = -1 if tip_left else 1
    tip = (cx + s * w * 0.55, cy + d * 0.15)
    back_l, back_r = (cx - s * w * 0.45, cy - d * 0.6), (cx - s * w * 0.35, cy + d * 0.45)
    shadow(base, cx, cy + h + d * 0.35, w * 0.6, 70, 0.3, 30)
    front = poly_mask([tip, back_r, (back_r[0], back_r[1] + h), (tip[0], tip[1] + h)])
    side = poly_mask([back_l, back_r, (back_r[0], back_r[1] + h), (back_l[0], back_l[1] + h)])
    paint(base, side, crust or mix(layers[0][0], "#7a4a2a", 0.35))
    total = sum(f for _, f in layers); y = 0
    for color, f in layers:
        band = intersect(front, poly_mask([(0, tip[1] + h * y / total - 400), (S, tip[1] + h * y / total - 400 + (back_r[1] - tip[1]) * 0), (S, back_r[1] + h * (y + f) / total), (0, tip[1] + h * (y + f) / total)]))
        band = intersect(front, poly_mask([tip_pt(tip, back_r, h * y / total, 0), tip_pt(tip, back_r, h * y / total, 1), tip_pt(tip, back_r, h * (y + f) / total, 1), tip_pt(tip, back_r, h * (y + f) / total, 0)]))
        paint(base, band, color); y += f
    shade(base, front, (min(tip[0], back_r[0]), 0, max(tip[0], back_r[0]), S), "#000000", 0.0, 0.08, "h")
    topm = poly_mask([tip, back_l, back_r])
    paint(base, topm, top)
    if crust:
        stroke(base, [back_l, back_r], crust, 46)
        paint(base, side, crust)
    return topm, front


def tip_pt(tip, back, dy, t):
    return (tip[0] + (back[0] - tip[0]) * t, tip[1] + (back[1] - tip[1]) * t + dy)


def berry(base, x, y, r, c="#b32645"):
    paint(base, ellipse_mask(x, y, r, r), c); paint(base, ellipse_mask(x - r * 0.3, y - r * 0.3, r * 0.28, r * 0.22), "#ffffff", 0.55)


def mint(base, x, y, rot=0):
    for dx, a in ((-28, rot + 30), (28, rot - 30)):
        paint(base, ellipse_mask(x + dx, y, 50, 24).rotate(a, center=(x + dx, y)), "#4f8a4b")


# ---------- coffee
def art_americano(base):
    steam(base, CX, 960, count=3, height=320)
    cup(base, top_y=1120, bot_y=1680, top_rx=360, bot_rx=250, liquid="#3b2416", curve=1.6,
        surface=lambda b, x, y, rx, ry: paint(b, blur(ellipse_mask(x - rx * 0.2, y - ry * 0.2, rx * 0.5, ry * 0.4), 22), "#6d4430", 0.85))


def art_flat_white(base):
    cup(base, top_y=1220, bot_y=1640, top_rx=320, bot_rx=210, liquid=CREMA, curve=1.6, body=("#f4efe8", "#d9cfc2"),
        surface=lambda b, x, y, rx, ry: (paint(b, ellipse_mask(x, y, rx, ry), "#c08450"), heart(b, x, y, rx, ry, MILK, 0.5)))


def art_mocha(base):
    def top(b, x, y, rx, ry):
        paint(b, ellipse_mask(x, y, rx, ry), "#8a5232")
        heart(b, x, y, rx, ry, MILK, 0.42)
        speckles(b, ellipse_mask(x, y, rx * 0.9, ry * 0.85), "#4a2616", 110, (4, 8), 8, 0.85)
    steam(base, CX, 920, count=2, height=260)
    cup(base, top_y=1080, bot_y=1700, top_rx=330, bot_rx=300, body=("#efe4d6", "#cdb9a2"), liquid="#8a5232", surface=top, saucer=False, mug=True, curve=1.0)


def art_cold_brew(base):
    glass(base, top_y=820, bot_y=1760, top_rx=300, bot_rx=270, fill_y=900, liquid_top="#4a2a18", liquid_bottom="#1f120a", ice=6, straw=("#1f2a24", None))


# ---------- tea & specialty
def art_chai_latte(base):
    def top(b, x, y, rx, ry):
        paint(b, ellipse_mask(x, y, rx, ry), "#d7a571")
        rosetta(b, x, y, rx, ry)
        speckles(b, ellipse_mask(x, y, rx * 0.9, ry * 0.85), "#8a4c22", 70, (4, 7), 12, 0.8)
    cup(base, top_y=1080, bot_y=1650, top_rx=400, bot_rx=250, liquid="#d7a571", surface=top, curve=1.8, body=("#f7f1e8", "#ddd0bd"))
    for dx, dy, rot in ((-560, 1760, 20), (520, 1790, -15)):
        paint(base, rounded_rect_mask(CX + dx - 120, dy - 26, CX + dx + 120, dy + 26, 24, rot), "#8a4a22")
        stroke(base, [(CX + dx - 100, dy), (CX + dx + 100, dy)], "#6a3615", 6, 0.6)


def art_matcha_latte(base):
    def top(b, x, y, rx, ry):
        paint(b, ellipse_mask(x, y, rx, ry), "#8fb35a")
        heart(b, x, y, rx, ry, "#f3f1df", 0.48)
    cup(base, top_y=1080, bot_y=1650, top_rx=400, bot_rx=250, liquid="#8fb35a", surface=top, curve=1.8, body=("#fbfbf6", "#dfe0d2"))
    paint(base, rounded_rect_mask(CX + 470, 1700, CX + 700, 1760, 30, -8), "#c49a6c")
    paint(base, ellipse_mask(CX + 450, 1720, 70, 34), "#9cbf62")


def art_london_fog(base):
    def top(b, x, y, rx, ry):
        paint(b, blur(ellipse_mask(x, y - 8, rx, ry * 1.04), 6), "#efe3d0")
        paint(b, blur(ellipse_mask(x, y - 8, rx * 0.6, ry * 0.55), 24), "#c9a98a", 0.5)
        speckles(b, ellipse_mask(x, y, rx * 0.5, ry * 0.5), "#7d6ab0", 26, (5, 9), 3, 0.9)
    steam(base, CX, 900, count=2, height=260)
    cup(base, top_y=1100, bot_y=1700, top_rx=330, bot_rx=300, body=("#7f93a8", "#5a6d82"), liquid="#efe3d0", surface=top, saucer=False, mug=True, curve=1.0)


# ---------- cold drinks
def art_milkshake(base):
    def garnish(b):
        for k, (dx, dy, s) in enumerate(((0, 0, 1.0), (-150, 70, 0.8), (150, 70, 0.8), (0, -110, 0.72))):
            paint(b, blur(ellipse_mask(CX + dx, 830 + dy, 210 * s, 130 * s), 4), "#fffaf3")
            shade(b, ellipse_mask(CX + dx, 830 + dy, 210 * s, 130 * s), (CX - 300, 0, CX + 300, S), "#b39b86", 0.0, 0.3, "h")
        berry(b, CX + 10, 660, 64, "#c41f3a")
        stroke(b, [(CX + 10, 600), (CX + 60, 520)], "#5a7a3a", 10)
    glass(base, top_y=880, bot_y=1760, top_rx=330, bot_rx=200, fill_y=920, liquid_top="#f6b9c9", liquid_bottom="#e88aa5", straw=("#ffffff", "#d84a6a"), garnish=garnish, curve=1.4)


def art_juice(base):
    def garnish(b):
        lemon(b, CX + 260, 880, 150, color="#f08a1c", pith="#ffd08a")
    glass(base, top_y=860, bot_y=1760, top_rx=300, bot_rx=260, fill_y=940, liquid_top="#ffb23e", liquid_bottom="#f07f12", garnish=garnish)
    lemon(base, CX - 520, 1700, 140, flat=True, color="#f08a1c", pith="#ffd08a")


# ---------- breakfast
def art_croissant_breakfast_sandwich(base):
    plate(base, CX, 1600, 720)
    croissant(base, CX, 1470, 0.95)
    y = 1450
    paint(base, poly_mask([(CX - 430, y), (CX + 430, y), (CX + 380, y + 60), (CX - 380, y + 60)]), "#f4b632")
    paint(base, blur(ellipse_mask(CX, y - 20, 420, 50), 4), "#fbf6ea")
    paint(base, ellipse_mask(CX - 30, y + 60, 400, 36), "#6fae4a")
    croissant(base, CX, 1290, 0.95)


def art_breakfast_wrap(base):
    plate(base, CX, 1620, 720)
    for dx, dy, rot in ((210, 1500, -24), (-210, 1570, 24)):
        shadow(base, CX + dx, dy + 150, 200, 50, 0.3, 24)
        tube = rounded_rect_mask(CX + dx - 150, dy - 330, CX + dx + 150, dy + 150, 140, rot, (CX + dx, dy))
        paint_gradient(base, tube, "#ecd09a", "#c99e5e", (CX + dx - 160, 0, CX + dx + 160, S), "h")
        speckles(base, tube, "#a8763a", 40, (8, 16), dx, 0.9)
        paint(base, ellipse_mask(CX + dx, dy - 300, 150, 95).rotate(rot, center=(CX + dx, dy)), "#f5e8c8")
        for i, (color, s) in enumerate((("#f6c63b", 0.86), ("#fbf4dc", 0.66), ("#b4553c", 0.48), ("#6aa84f", 0.3))):
            paint(base, ellipse_mask(CX + dx + (i % 2) * 12, dy - 300, 150 * s, 95 * s).rotate(rot, center=(CX + dx, dy)), color)


def egg(base, x, y, r):
    m = blur(union(ellipse_mask(x, y, r, r * 0.55), ellipse_mask(x + r * 0.35, y + r * 0.1, r * 0.7, r * 0.45), ellipse_mask(x - r * 0.4, y + r * 0.05, r * 0.65, r * 0.4)), 10).point(lambda v: 255 if v > 120 else 0)
    paint(base, m, "#fdfbf4"); shade(base, m, (x - r, 0, x + r, S), "#c9b99a", 0.0, 0.3, "h")
    paint(base, ellipse_mask(x - 10, y - 10, r * 0.36, r * 0.27), "#f3a51c")
    paint(base, ellipse_mask(x - 30, y - 30, r * 0.12, r * 0.07), "#ffffff", 0.6)


def art_eggs_plate(base):
    plate(base, CX, 1480, 760)
    egg(base, CX - 220, 1400, 240); egg(base, CX + 180, 1330, 220)
    for k in range(3):
        y = 1560 + k * 16
        stroke(base, [(CX - 120 + k * 60, y), (CX + 60 + k * 60, y - 30), (CX + 220 + k * 60, y + 10), (CX + 380 + k * 60, y - 20)], "#a8442f", 46)
        stroke(base, [(CX - 120 + k * 60, y), (CX + 60 + k * 60, y - 30), (CX + 220 + k * 60, y + 10), (CX + 380 + k * 60, y - 20)], "#e7a08c", 12, 0.8)
    for dx in (-470, -380):
        paint(base, rounded_rect_mask(CX + dx - 90, 1480, CX + dx + 90, 1640, 30, -10), "#c98b4a")
        paint(base, rounded_rect_mask(CX + dx - 72, 1496, CX + dx + 72, 1624, 24, -10), "#e8c28a")


def art_pancakes(base):
    plate(base, CX, 1640, 720)
    for i in range(5):
        y = 1560 - i * 95
        paint(base, ellipse_mask(CX, y + 30, 440, 130), "#b8702e")
        paint_gradient(base, ellipse_mask(CX, y, 440, 130), "#e9b067", "#cf8a42", (0, y - 130, S, y + 130), "v")
        stroke(base, [(CX - 430, y + 20), (CX, y + 60), (CX + 430, y + 20)], "#f3d29a", 10, 0.6)
    top = 1560 - 4 * 95
    syrup = union(ellipse_mask(CX + 20, top - 10, 320, 90), rounded_rect_mask(CX - 200, top, CX - 140, top + 200, 30), rounded_rect_mask(CX + 160, top, CX + 220, top + 140, 30))
    paint(base, syrup, "#a2531c", 0.88)
    paint(base, rounded_rect_mask(CX - 70, top - 80, CX + 90, top + 10, 24, -6), "#fbe39a")
    for x, c in ((CX - 260, "#3a2d6b"), (CX + 300, "#b32645")):
        berry(base, x, top - 20, 46, c)


def art_waffles(base):
    plate(base, CX, 1620, 720)
    for dx, dy in ((-170, 1460), (180, 1330)):
        m = rounded_rect_mask(CX + dx - 330, dy - 220, CX + dx + 330, dy + 120, 40, -8)
        paint(base, m.transform(m.size, 0, (1, 0, 0, 0, 1, -34)), "#a8652a")
        paint(base, m, "#e2a456")
        for k in range(1, 6):
            band = poly_mask([(CX + dx - 340 + k * 113, dy - 240), (CX + dx - 316 + k * 113, dy - 240), (CX + dx - 300 + k * 113, dy + 140), (CX + dx - 324 + k * 113, dy + 140)])
            paint(base, intersect(band, m), "#b36f2c")
        for k in range(1, 4):
            y = dy - 220 + k * 85
            paint(base, intersect(poly_mask([(0, y + 40), (S, y - 40), (S, y - 16), (0, y + 64)]), m), "#b36f2c")
    paint(base, ellipse_mask(CX + 160, 1180, 110, 60), "#fdf7ec")
    berry(base, CX + 60, 1170, 50); berry(base, CX + 270, 1200, 46, "#3a2d6b")


def art_french_toast(base):
    plate(base, CX, 1620, 720)
    for dx, dy, rot in ((-180, 1470, 8), (190, 1360, -10)):
        crust = rounded_rect_mask(CX + dx - 280, dy - 230, CX + dx + 280, dy + 150, 70, rot)
        paint(base, crust.transform(crust.size, 0, (1, 0, 0, 0, 1, -30)), "#8a4a1e")
        paint(base, crust, "#a85e26")
        inner = rounded_rect_mask(CX + dx - 245, dy - 200, CX + dx + 245, dy + 120, 55, rot)
        paint_gradient(base, inner, "#e6a24f", "#c97a30", (0, dy - 200, S, dy + 120), "v")
        speckles(base, inner, "#8a4a1e", 40, (8, 16), dx + 7, 0.7)
    rnd = random.Random(3)
    for _ in range(140):
        x, y = CX + rnd.uniform(-420, 420), 1250 + rnd.uniform(-60, 320)
        paint(base, ellipse_mask(x, y, 5, 5), "#ffffff", 0.9)
    for x, y in ((CX + 120, 1220), (CX - 60, 1320), (CX + 260, 1300)):
        berry(base, x, y, 46)


def art_bagel(base):
    plate(base, CX, 1600, 700)
    cy = 1420
    paint(base, subtract(ellipse_mask(CX, cy + 60, 420, 200), ellipse_mask(CX, cy + 30, 110, 46)), "#a8642a")
    body = subtract(ellipse_mask(CX, cy, 420, 200), ellipse_mask(CX, cy - 10, 120, 52))
    paint_gradient(base, body, "#e2a85c", "#b8722f", (0, cy - 200, S, cy + 200), "v")
    cream = subtract(blur(ellipse_mask(CX, cy - 10, 330, 150), 14).point(lambda v: 255 if v > 120 else 0), ellipse_mask(CX, cy - 10, 135, 60))
    paint(base, cream, "#fbf7ef")
    rnd = random.Random(8)
    for _ in range(50):
        x, y = CX + rnd.uniform(-400, 400), cy + rnd.uniform(-190, 190)
        if body.getpixel((int(x), int(y))) > 200 and cream.getpixel((int(x), int(y))) < 100:
            paint(base, ellipse_mask(x, y, 10, 6).rotate(rnd.uniform(0, 180), center=(x, y)), rnd.choice(["#fbf0d8", "#2a2420"]))


def art_oatmeal(base):
    rx, ry = bowl(base, rim_y=1260, rx=520, depth=420, color=("#fbfaf6", "#e2dace"), accent="#c9a27a")
    paint(base, ellipse_mask(CX, 1270, rx, ry), "#e8d5b0")
    speckles(base, ellipse_mask(CX, 1270, rx * 0.9, ry * 0.85), "#cdb48a", 160, (8, 14), 2, 0.8)
    for k, (x, y) in enumerate(((CX - 180, 1240), (CX - 60, 1210), (CX + 70, 1250))):
        paint(base, ellipse_mask(x, y, 70, 30).rotate(-20, center=(x, y)), "#f6e98a"); ring(base, x, y, 70, 30, "#b9a040", 6)
    for x, y in ((CX + 210, 1220), (CX + 280, 1260), (CX + 180, 1290)):
        berry(base, x, y, 34, "#3a2d6b")
    stroke(base, [(CX - 300, 1280), (CX - 100, 1300), (CX + 120, 1280)], "#b5651d", 12, 0.8)


# ---------- bakery
def art_cinnamon_roll(base):
    plate(base, CX, 1600, 700)
    cy = 1380
    paint(base, ellipse_mask(CX, cy + 90, 400, 200), "#a8602a")
    paint_gradient(base, ellipse_mask(CX, cy, 400, 200), "#e6a961", "#c27c38", (0, cy - 200, S, cy + 200), "v")
    pts = []
    for k in range(260):
        t = k / 260 * 4.2 * math.pi
        r = 30 + t * 26
        pts.append((CX + r * math.cos(t), cy + r * 0.5 * math.sin(t)))
    stroke(base, pts, "#8a4a1e", 26)
    stroke(base, [(x + 4, y - 6) for x, y in pts], "#fbf3e3", 14, 0.9)
    for dx in (-300, -120, 150, 320):
        paint(base, rounded_rect_mask(CX + dx - 26, cy + 60, CX + dx + 26, cy + 200 + (dx % 3) * 20, 26), "#fbf3e3", 0.95)


def art_tart(base):
    plate(base, CX, 1600, 680)
    cy = 1380
    paint(base, ellipse_mask(CX, cy + 80, 420, 190), "#b9783a")
    paint(base, ellipse_mask(CX, cy, 420, 190), "#dca15a")
    for k in range(36):
        a = k * math.pi / 18
        paint(base, ellipse_mask(CX + 420 * math.cos(a), cy + 190 * math.sin(a), 34, 24), "#c98a45")
    paint(base, ellipse_mask(CX, cy - 8, 360, 155), "#f4d86a")
    for k in range(9):
        a = k * 2 * math.pi / 9
        x, y = CX + 220 * math.cos(a), cy + 95 * math.sin(a)
        berry(base, x, y - 10, 52, "#c41f3a" if k % 2 else "#3a2d6b")
    for k in range(5):
        a = k * 2 * math.pi / 5
        paint(base, ellipse_mask(CX + 70 * math.cos(a), cy + 30 * math.sin(a), 60, 30), "#f6a23a")
    mint(base, CX, cy - 20)


def art_turnover(base):
    plate(base, CX, 1600, 700)
    for dx, dy, flip in ((-170, 1440, 1), (210, 1320, -1)):
        pts = [(CX + dx - 320 * flip, dy + 120), (CX + dx + 300 * flip, dy + 80), (CX + dx + 20 * flip, dy - 260)]
        body = blur(poly_mask(pts), 30).point(lambda v: 255 if v > 110 else 0)
        paint(base, body.transform(body.size, 0, (1, 0, 0, 0, 1, -40)), "#a8602a")
        paint_gradient(base, body, "#f0bc6c", "#c98238", (0, dy - 260, S, dy + 120), "v")
        for k in range(3):
            stroke(base, [(CX + dx - 60 * flip + k * 60 * flip, dy - 40 + k * 10), (CX + dx + 0 * flip + k * 60 * flip, dy - 120 + k * 10)], "#9a5422", 14)
        speckles(base, body, "#fff7e6", 50, (5, 9), dx, 0.95)
        stroke(base, [pts[0], pts[1]], "#8a3a2a", 22, 0.85)


# ---------- sandwiches
def art_artisan_sandwich(base):
    plate(base, CX, 1620, 740)
    for dx, dy in ((-190, 1500), (210, 1380)):
        shadow(base, CX + dx, dy + 40, 320, 60, 0.3, 24)
        y = dy
        for color, th, wave in (("#d9a35c", 80, 0), ("#6fae4a", 30, 1), ("#e25b4a", 34, 0), ("#f3efe4", 34, 0), ("#c36a60", 40, 0), ("#6fae4a", 26, 1), ("#d9a35c", 110, 0)):
            m = rounded_rect_mask(CX + dx - 300, y - th, CX + dx + 300, y, 30 if th > 60 else 8)
            if wave:
                m = union(m, poly_mask([(CX + dx - 330 + k * 33, y - th + (16 if k % 2 else -8)) for k in range(21)] + [(CX + dx + 330, y), (CX + dx - 330, y)]))
            paint(base, m, color); y -= th
        top = union(ellipse_mask(CX + dx, y + 20, 300, 80), rounded_rect_mask(CX + dx - 300, y + 20, CX + dx + 300, y + 60, 20))
        paint_gradient(base, top, "#c98a45", "#9a5a22", (0, y - 60, S, y + 60), "v")
        speckles(base, top, "#f6e6c3", 30, (6, 10), dx, 0.9)


def art_panini(base):
    plate(base, CX, 1620, 740)
    for dx, dy, flip in ((220, 1430, -1), (-200, 1560, 1)):
        shadow(base, CX + dx, dy + 40, 300, 60, 0.3, 24)
        tip = CX + dx + 320 * flip
        back = CX + dx - 300 * flip
        paint(base, poly_mask([(back, dy - 120), (tip, dy - 80), (tip, dy + 10), (back, dy + 30)]), "#d4954c")
        cheese = poly_mask([(back, dy - 80), (tip, dy - 50), (tip, dy - 10), (back, dy - 10)])
        paint(base, cheese, "#f5c842")
        for k in range(5):
            x = back + (tip - back) * (0.1 + k * 0.18)
            paint(base, rounded_rect_mask(x - 18, dy - 30, x + 18, dy + 40 + (k % 2) * 30, 18), "#f5c842")
        paint(base, poly_mask([(back, dy - 70), (tip, dy - 44), (tip, dy - 30), (back, dy - 50)]), "#c36a60")
        top = poly_mask([(back, dy - 260), (tip, dy - 200), (tip, dy - 90), (back, dy - 100)])
        paint_gradient(base, top, "#e6b06b", "#c98a45", (0, dy - 260, S, dy - 90), "v")
        for k in range(6):
            x0 = back + (tip - back) * (0.08 + k * 0.16)
            stroke(base, [(x0 - 40 * flip, dy - 250 + k * 10), (x0 + 60 * flip, dy - 100 + k * 6)], "#7a3e14", 18, 0.85)


# ---------- lunch & savoury
def art_burger(base):
    plate(base, CX, 1640, 720)
    y = 1540
    bot = union(ellipse_mask(CX, y, 380, 70), rounded_rect_mask(CX - 380, y - 90, CX + 380, y, 50))
    paint_gradient(base, bot, "#e2a85c", "#b8722f", (0, y - 90, S, y + 70), "v")
    paint(base, rounded_rect_mask(CX - 400, y - 210, CX + 400, y - 80, 60), "#5a3020")
    speckles(base, rounded_rect_mask(CX - 390, y - 200, CX + 390, y - 90, 50), "#3a1d12", 80, (6, 12), 4, 0.9)
    paint(base, poly_mask([(CX - 400, y - 220), (CX + 400, y - 220), (CX + 330, y - 140), (CX + 200, y - 210), (CX + 60, y - 130), (CX - 90, y - 210), (CX - 250, y - 140), (CX - 380, y - 200)]), "#f5c03a")
    paint(base, rounded_rect_mask(CX - 360, y - 270, CX + 360, y - 210, 30), "#d8443a")
    paint(base, poly_mask([(CX - 430 + k * 43, y - 270 - (24 if k % 2 else 0)) for k in range(21)] + [(CX + 430, y - 250), (CX - 430, y - 250)]), "#6fae4a")
    bun(base, CX, y - 290, 400, 280)


def art_hot_dog(base):
    plate(base, CX, 1620, 720)
    cy = 1420
    shadow(base, CX, cy + 140, 560, 60, 0.3, 24)
    paint(base, rounded_rect_mask(CX - 560, cy - 80, CX + 560, cy + 150, 115, -6), "#d79a52")
    paint(base, rounded_rect_mask(CX - 620, cy - 120, CX + 620, cy + 40, 80, -6), "#a8402a")
    paint(base, blur(rounded_rect_mask(CX - 560, cy - 100, CX + 520, cy - 60, 20, -6), 8), "#e27a5a", 0.7)
    pts = [(CX - 520 + k * 40, cy - 70 + 28 * math.sin(k * 0.9) + k * 3) for k in range(27)]
    stroke(base, pts, "#f3c21c", 24)
    front = rounded_rect_mask(CX - 560, cy - 10, CX + 560, cy + 190, 100, -6)
    paint_gradient(base, front, "#eab36a", "#b8722f", (0, cy, S, cy + 190), "v")


def art_quiche(base):
    plate(base, CX, 1620, 720)
    topm, front = wedge(base, CX, 1300, w=760, h=230, d=300, layers=(("#f2d27a", 1.0),), top="#e9b44a", crust="#c98a45")
    speckles(base, topm, "#3f7a3a", 26, (10, 18), 3, 0.95)
    speckles(base, topm, "#c97a3a", 30, (14, 26), 4, 0.6)
    speckles(base, front, "#3f7a3a", 20, (8, 14), 5, 0.9)


def art_pizza(base):
    board = ellipse_mask(CX, 1420, 800, 330)
    shadow(base, CX, 1460, 800, 300, 0.25, 40)
    paint(base, board.transform(board.size, 0, (1, 0, 0, 0, 1, -40)), "#a8733f")
    paint_gradient(base, board, "#d6a56c", "#b8834a", (0, 1090, S, 1750), "v")
    paint(base, ellipse_mask(CX, 1400, 660, 270), "#d79a52")
    paint(base, ellipse_mask(CX, 1395, 600, 238), "#c8402e")
    rnd = random.Random(2)
    for _ in range(18):
        x, y = CX + rnd.uniform(-480, 480), 1395 + rnd.uniform(-180, 180)
        paint(base, blur(ellipse_mask(x, y, 120, 60), 10).point(lambda v: 255 if v > 120 else 0), "#f8e6b0", 0.95)
    for _ in range(12):
        x, y = CX + rnd.uniform(-460, 460), 1395 + rnd.uniform(-170, 170)
        if ellipse_mask(CX, 1395, 560, 220).getpixel((int(x), int(y))) > 200:
            paint(base, ellipse_mask(x, y, 46, 22), "#a02a22"); paint(base, ellipse_mask(x + 50, y - 30, 30, 14).rotate(30, center=(x + 50, y - 30)), "#3f7a3a")
    for k in range(4):
        a = k * math.pi / 4
        stroke(base, [(CX - 640 * math.cos(a), 1400 - 262 * math.sin(a)), (CX + 640 * math.cos(a), 1400 + 262 * math.sin(a))], "#8a3a20", 6, 0.35)


def art_fries(base):
    shadow(base, CX, 1760, 330, 70, 0.3, 30)
    rnd = random.Random(5)
    for k in range(22):
        x = CX - 260 + k * 25 + rnd.uniform(-10, 10)
        top = 860 + rnd.uniform(0, 220)
        rot = rnd.uniform(-12, 12)
        paint(base, rounded_rect_mask(x - 26, top, x + 26, 1500, 12, rot, (x, 1400)), rnd.choice(["#f4c64e", "#e9b13a", "#f7d26a"]))
        stroke(base, [(x - 12, top + 20), (x - 12, top + 200)], "#fff0b0", 6, 0.6)
    box = poly_mask([(CX - 330, 1240), (CX + 330, 1240), (CX + 250, 1760), (CX - 250, 1760)])
    paint_gradient(base, box, "#c9433a", "#9a2e28", (CX - 330, 0, CX + 330, S), "h")
    paint(base, poly_mask([(CX - 330, 1240), (CX, 1330), (CX + 330, 1240), (CX + 320, 1300), (CX, 1390), (CX - 320, 1300)]), "#b23a32")
    paint(base, blur(poly_mask([(CX - 290, 1340), (CX - 240, 1340), (CX - 190, 1740), (CX - 230, 1740)]), 12), "#ffffff", 0.3)


def art_savoury_bowl(base):
    rx, ry = bowl(base, rim_y=1260, rx=540, depth=400, color=("#3f4a46", "#26302c"))
    paint(base, ellipse_mask(CX, 1270, rx, ry), "#f6f1e6")
    speckles(base, ellipse_mask(CX, 1270, rx * 0.9, ry * 0.85), "#e6dcc8", 160, (6, 10), 4, 0.9)
    paint(base, ellipse_mask(CX - 240, 1240, 180, 90), "#3f7a3a"); speckles(base, ellipse_mask(CX - 240, 1240, 170, 80), "#5f9e45", 30, (14, 24), 1, 1)
    for k in range(5):
        paint(base, rounded_rect_mask(CX - 40 + k * 60, 1180, CX + 10 + k * 60, 1320, 16, -20), "#b56a34")
    paint(base, ellipse_mask(CX + 300, 1250, 110, 60), "#9bc06a"); paint(base, ellipse_mask(CX + 300, 1250, 70, 36), "#d7e6a0")
    egg(base, CX + 40, 1340, 110)
    stroke(base, [(CX - 350, 1200), (CX - 100, 1180), (CX + 150, 1210)], "#e45a3a", 10, 0.8)


# ---------- soup & salad
def art_broth_soup(base):
    rx, ry = bowl(base, rim_y=1230, rx=520, depth=430, color=("#fbfaf6", "#e2dace"), accent="#c9433a")
    paint(base, ellipse_mask(CX, 1240, rx, ry), "#d9a441")
    paint(base, blur(ellipse_mask(CX - 60, 1225, rx * 0.6, ry * 0.5), 30), "#ecc565", 0.8)
    rnd = random.Random(6)
    for _ in range(10):
        x, y = CX + rnd.uniform(-rx * 0.7, rx * 0.7), 1240 + rnd.uniform(-ry * 0.6, ry * 0.6)
        paint(base, ellipse_mask(x, y, 30, 22), "#f08a2a")
    for _ in range(9):
        x, y = CX + rnd.uniform(-rx * 0.7, rx * 0.7), 1240 + rnd.uniform(-ry * 0.6, ry * 0.6)
        stroke(base, [(x - 60, y), (x, y + 14), (x + 60, y - 6)], "#f6e6b0", 14)
    speckles(base, ellipse_mask(CX, 1240, rx * 0.7, ry * 0.6), "#3f7a3a", 30, (6, 12), 7, 1.0)
    steam(base, CX, 900, count=3, height=280)


def art_chowder(base):
    rx, ry = bowl(base, rim_y=1230, rx=520, depth=430, color=("#fbfaf6", "#e2dace"), accent="#5a6d82")
    paint(base, ellipse_mask(CX, 1240, rx, ry), "#f2e6cc")
    paint(base, blur(ellipse_mask(CX - 60, 1225, rx * 0.6, ry * 0.5), 30), "#fbf4e2", 0.8)
    speckles(base, ellipse_mask(CX, 1240, rx * 0.8, ry * 0.7), "#e8d08a", 24, (16, 26), 3, 1.0)
    speckles(base, ellipse_mask(CX, 1240, rx * 0.8, ry * 0.7), "#d9b07a", 14, (14, 20), 4, 1.0)
    speckles(base, ellipse_mask(CX, 1240, rx * 0.6, ry * 0.5), "#3f7a3a", 30, (5, 9), 5, 1.0)
    for x, y in ((CX + 480, 1700), (CX + 620, 1660)):
        paint(base, ellipse_mask(x, y, 70, 60), "#e8c07a"); speckles(base, ellipse_mask(x, y, 60, 50), "#b88a4a", 6, (5, 8), int(x), 1)


def art_chili(base):
    rx, ry = bowl(base, rim_y=1230, rx=520, depth=430, color=("#c9573f", "#9a3d2c"))
    paint(base, ellipse_mask(CX, 1240, rx, ry), "#8f2e1c")
    speckles(base, ellipse_mask(CX, 1240, rx * 0.9, ry * 0.8), "#5a1c12", 70, (12, 20), 2, 1.0)
    speckles(base, ellipse_mask(CX, 1240, rx * 0.9, ry * 0.8), "#b5462a", 60, (8, 14), 3, 1.0)
    paint(base, blur(ellipse_mask(CX - 40, 1220, 170, 60), 6), "#fbf7ef")
    speckles(base, ellipse_mask(CX + 160, 1230, 160, 60), "#f3b23a", 40, (8, 12), 4, 1.0)
    speckles(base, ellipse_mask(CX - 40, 1210, 130, 40), "#3f7a3a", 14, (6, 10), 5, 1.0)


def art_composed_salad(base):
    plate(base, CX, 1500, 760)
    rnd = random.Random(21)
    for _ in range(30):
        x, y = CX + rnd.uniform(-520, 520), 1440 + rnd.uniform(-130, 130)
        leaf = ellipse_mask(x, y, rnd.uniform(90, 130), rnd.uniform(40, 60)).rotate(rnd.uniform(0, 180), center=(x, y))
        paint(base, leaf, rnd.choice(["#5f9e45", "#7dbb55", "#4b8a3a", "#9bcf6b"]))
    for k in range(5):
        x = CX - 320 + k * 150
        paint(base, rounded_rect_mask(x - 60, 1300, x + 60, 1420, 20, 10), "#d9b07a"); stroke(base, [(x - 40, 1330), (x + 40, 1390)], "#8a5a28", 10, 0.8)
    for x, y in ((CX - 380, 1500), (CX + 380, 1450)):
        paint(base, ellipse_mask(x, y, 90, 60), "#fdfbf4"); paint(base, ellipse_mask(x, y, 46, 34), "#f3a51c")
    for x, y in ((CX - 140, 1530), (CX + 160, 1540), (CX + 20, 1470)):
        paint(base, ellipse_mask(x, y, 50, 46), "#d83b32"); paint(base, ellipse_mask(x - 14, y - 14, 12, 10), "#ffffff", 0.6)


def art_grain_bowl(base):
    rx, ry = bowl(base, rim_y=1260, rx=540, depth=400, color=("#fdfcf9", "#e3dccf"), accent="#8fae6a")
    c, r = 1270, (rx, ry)
    wedges = (("#e8d6b0", 0), ("#8fb54c", 1), ("#d83b32", 2), ("#f08a2a", 3), ("#5a3a6b", 4), ("#5f9e45", 5))
    for color, k in wedges:
        a0, a1 = k * math.pi / 3, (k + 1) * math.pi / 3
        pts = [(CX, c)] + [(CX + rx * math.cos(a0 + (a1 - a0) * t / 10), c + ry * math.sin(a0 + (a1 - a0) * t / 10)) for t in range(11)]
        m = intersect(poly_mask(pts), ellipse_mask(CX, c, rx, ry))
        paint(base, m, color)
        speckles(base, m, mix(color, "#ffffff", 0.3), 30, (8, 14), k, 0.9)
    paint(base, ellipse_mask(CX, c - 10, 110, 50), "#fdfbf4")
    speckles(base, ellipse_mask(CX, c, rx * 0.8, ry * 0.7), "#2a2420", 40, (4, 6), 9, 0.9)


# ---------- desserts
def art_chocolate_cake(base):
    plate(base, CX, 1640, 720)
    topm, front = wedge(base, CX, 1180, w=720, h=420, d=280,
                        layers=(("#5a2e1c", 0.9), ("#8a5232", 0.25), ("#5a2e1c", 0.9), ("#8a5232", 0.25), ("#5a2e1c", 0.9)), top="#6a3a24", crust="#5a2e1c")
    paint(base, topm, "#4a2416")
    speckles(base, topm, "#2a120a", 30, (8, 14), 3, 0.9)
    berry(base, CX - 40, 1140, 56, "#c41f3a")


def art_light_cake(base):
    plate(base, CX, 1640, 720)
    topm, front = wedge(base, CX, 1180, w=720, h=400, d=280,
                        layers=(("#f6dc9a", 0.9), ("#fbf4e6", 0.2), ("#e0475a", 0.12), ("#f6dc9a", 0.9), ("#fbf4e6", 0.2), ("#f6dc9a", 0.9)), top="#fbf4e6", crust="#fbf4e6")
    for x, y, c in ((CX - 120, 1120, "#c41f3a"), (CX + 40, 1150, "#3a2d6b"), (CX - 10, 1080, "#c41f3a")):
        berry(base, x, y, 46, c)
    mint(base, CX + 140, 1110)


def art_cheesecake(base):
    plate(base, CX, 1640, 720)
    topm, front = wedge(base, CX, 1200, w=720, h=360, d=280, layers=(("#fbf0d2", 0.85), ("#c9935a", 0.18)), top="#f2d798", crust="#c9935a")
    for x, y, c in ((CX - 160, 1160, "#c41f3a"), (CX - 60, 1190, "#3a2d6b"), (CX - 110, 1120, "#c41f3a")):
        berry(base, x, y, 46, c)
    stroke(base, [(CX + 260, 1720), (CX + 360, 1700), (CX + 480, 1730)], "#b3263a", 22, 0.85)


def art_tiramisu(base):
    plate(base, CX, 1640, 720)
    x0, x1, y0, y1, d = CX - 330, CX + 280, 1180, 1560, 160
    paint(base, poly_mask([(x1, y0), (x1 + 160, y0 - d), (x1 + 160, y1 - d), (x1, y1)]), "#b58a62")
    layers = (("#5a3420", 0.16), ("#f3e6cc", 0.2), ("#c08a52", 0.2), ("#f3e6cc", 0.2), ("#c08a52", 0.24))
    y = y0
    for color, f in layers:
        h = (y1 - y0) * f
        paint(base, rounded_rect_mask(x0, y, x1, y + h + 2, 4), color); y += h
    top = poly_mask([(x0, y0), (x1, y0), (x1 + 160, y0 - d), (x0 + 160, y0 - d)])
    paint(base, top, "#6a3e24")
    speckles(base, top, "#3a2014", 120, (4, 8), 2, 0.9)


def art_pie_slice(base):
    plate(base, CX, 1640, 720)
    topm, front = wedge(base, CX, 1260, w=740, h=260, d=300, layers=(("#c98a45", 0.15), ("#a8302a", 0.7), ("#c98a45", 0.15)), top="#e2a85c", crust="#d4954c")
    for k in range(4):
        stroke(base, [(CX - 300 + k * 170, 1080 + k * 30), (CX - 220 + k * 170, 1320 - k * 10)], "#b8722f", 26)
    speckles(base, topm, "#f6e6c3", 50, (5, 9), 6, 0.9)
    paint(base, blur(ellipse_mask(CX + 400, 1560, 120, 60), 6), "#fffaf3")


def art_ice_cream(base):
    rx, ry = bowl(base, rim_y=1420, rx=440, depth=320, color=("#9fb7c9", "#6c8ba3"))
    for x, y, c in ((CX - 170, 1300, "#f7c3d1"), (CX + 170, 1300, "#fbf0d2"), (CX, 1130, "#6a3a24")):
        m = blur(union(ellipse_mask(x, y, 220, 190), ellipse_mask(x, y + 120, 240, 80)), 6).point(lambda v: 255 if v > 120 else 0)
        paint(base, m, c)
        shade(base, m, (x - 240, 0, x + 240, S), "#000000", 0.0, 0.15, "h")
        paint(base, blur(ellipse_mask(x - 70, y - 70, 70, 40), 14), "#ffffff", 0.45)
    paint(base, rounded_rect_mask(CX + 120, 820, CX + 200, 1120, 30, -25), "#e3b26c")
    berry(base, CX + 40, 960, 52, "#c41f3a")


def art_parfait(base):
    def garnish(b):
        for x, y, c in ((CX - 100, 880, "#c41f3a"), (CX + 40, 860, "#3a2d6b"), (CX + 140, 890, "#c41f3a")):
            berry(b, x, y, 52, c)
        mint(b, CX - 10, 820)

    def layers(b, liquid):
        for y0, y1, color in ((1080, 1220, "#c41f3a"), (1360, 1470, "#e8b36a"), (1600, 1740, "#c41f3a")):
            band = intersect(liquid, poly_mask([(x, y0 + 16 * math.sin(x / 90)) for x in range(0, S + 1, 40)] + [(S, y1), (0, y1)]))
            paint(b, band, color)
            speckles(b, band, mix(color, "#000000", 0.3), 40, (8, 14), y0, 0.8)
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=200, fill_y=930, liquid_top="#fdf9f2", liquid_bottom="#f4ecdd", garnish=garnish, curve=1.5, layers=layers)


def art_fruit_cup(base):
    rx, ry = bowl(base, rim_y=1300, rx=500, depth=380, color=("#fdfcf9", "#e3dccf"))
    rnd = random.Random(31)
    mound = ellipse_mask(CX, 1220, rx * 0.95, 220)
    for _ in range(40):
        x, y = CX + rnd.uniform(-rx * 0.85, rx * 0.85), 1150 + rnd.uniform(-90, 180)
        if mound.getpixel((int(x), int(y))) < 200:
            continue
        kind = rnd.randrange(4)
        if kind == 0:
            paint(base, rounded_rect_mask(x - 50, y - 40, x + 50, y + 40, 14, rnd.uniform(0, 90)), "#f6c63b")
        elif kind == 1:
            paint(base, ellipse_mask(x, y, 56, 56), "#8fbf3a"); paint(base, ellipse_mask(x, y, 36, 36), "#cfe68a"); speckles(base, ellipse_mask(x, y, 30, 30), "#2a2420", 6, (3, 5), int(x), 1)
        elif kind == 2:
            berry(base, x, y, 48, "#c41f3a")
        else:
            berry(base, x, y, 34, "#3a2d6b")
    mint(base, CX + 60, 1040)


# ---------- packaged retail
def art_coffee_beans_bag(base):
    shadow(base, CX, 1780, 420, 70, 0.3, 30)
    body = poly_mask([(CX - 330, 860), (CX + 330, 860), (CX + 360, 1780), (CX - 360, 1780)])
    paint_gradient(base, body, "#d9b88a", "#b8935e", (CX - 360, 0, CX + 360, S), "h")
    paint(base, rounded_rect_mask(CX - 350, 780, CX + 350, 900, 20), "#c9a272")
    for k in range(4):
        stroke(base, [(CX - 340, 800 + k * 26), (CX + 340, 800 + k * 26)], "#a8824e", 6, 0.6)
    paint(base, rounded_rect_mask(CX - 200, 1150, CX + 200, 1450, 30), "#f4ece0")
    bean = lambda x, y, r, rot: (paint(base, rounded_rect_mask(x - r, y - r * 0.68, x + r, y + r * 0.68, r * 0.68, rot), "#4a2c1d"), stroke(base, [(x - r * 0.6, y + r * 0.15), (x + r * 0.6, y - r * 0.15)], "#2b170e", 8))
    bean(CX, 1300, 70, 20)
    rnd = random.Random(4)
    for _ in range(12):
        bean(CX + rnd.uniform(-600, 600), 1830 + rnd.uniform(-40, 60), 50, rnd.uniform(0, 180))


def art_packaged_snack(base):
    shadow(base, CX, 1760, 460, 70, 0.3, 30)
    for dx, dy, c, rot in ((-230, 1300, "#e8b44d", -8), (230, 1330, "#c9573f", 8)):
        bag = rounded_rect_mask(CX + dx - 230, dy - 380, CX + dx + 230, dy + 420, 60, rot, (CX + dx, dy))
        paint_gradient(base, bag, mix(c, "#ffffff", 0.2), c, (CX + dx - 240, 0, CX + dx + 240, S), "h")
        for yy in (dy - 360, dy + 400):
            for k in range(9):
                stroke(base, [(CX + dx - 210 + k * 52, yy - 20), (CX + dx - 210 + k * 52, yy + 20)], mix(c, "#000000", 0.25), 8, 0.6)
        paint(base, rounded_rect_mask(CX + dx - 130, dy - 120, CX + dx + 130, dy + 140, 30, rot, (CX + dx, dy)), "#fbf7ef")
        paint(base, blur(rounded_rect_mask(CX + dx - 200, dy - 330, CX + dx - 150, dy + 360, 20, rot, (CX + dx, dy)), 12), "#ffffff", 0.45)
    cookie(base, CX - 230, 1310, 100, 1)
    for k, (x, y) in enumerate(((CX + 200, 1300), (CX + 260, 1350), (CX + 220, 1380))):
        paint(base, ellipse_mask(x, y, 46, 30).rotate(k * 40, center=(x, y)), "#e0a24a")


def art_bottled_drink(base):
    for dx, c, cap in ((-210, "#f08a2a", "#f4ece0"), (210, "#6aa84f", "#f4ece0")):
        x = CX + dx
        shadow(base, x, 1770, 190, 40, 0.3, 24)
        body = union(rounded_rect_mask(x - 170, 1100, x + 170, 1770, 60), poly_mask([(x - 170, 1120), (x - 70, 880), (x + 70, 880), (x + 170, 1120)]), rounded_rect_mask(x - 70, 760, x + 70, 900, 10))
        paint(base, body, "#ffffff", 0.35)
        liquid = intersect(body, rounded_rect_mask(x - 160, 960, x + 160, 1760, 50))
        paint_gradient(base, liquid, mix(c, "#ffffff", 0.25), c, (0, 960, S, 1760), "v")
        paint(base, rounded_rect_mask(x - 172, 1280, x + 172, 1520, 6), "#fbf7ef")
        paint(base, rounded_rect_mask(x - 80, 700, x + 80, 790, 18), cap)
        paint(base, blur(rounded_rect_mask(x - 130, 1000, x - 90, 1720, 20), 10), "#ffffff", 0.55)
    lemon(base, CX + 520, 1720, 110, flat=True, color="#f08a2a", pith="#ffd08a")


ARTWORK_M4 = {
    "americano": ("coffee", art_americano),
    "flat-white-cortado": ("coffee", art_flat_white),
    "mocha": ("coffee", art_mocha),
    "cold-brew": ("cold", art_cold_brew),
    "chai-latte": ("tea", art_chai_latte),
    "matcha-latte": ("tea", art_matcha_latte),
    "tea-latte-london-fog": ("tea", art_london_fog),
    "milkshake-blended-drink": ("sweet", art_milkshake),
    "juice": ("cold", art_juice),
    "croissant-breakfast-sandwich": ("breakfast", art_croissant_breakfast_sandwich),
    "breakfast-wrap": ("breakfast", art_breakfast_wrap),
    "eggs-breakfast-plate": ("breakfast", art_eggs_plate),
    "pancakes": ("breakfast", art_pancakes),
    "waffles": ("breakfast", art_waffles),
    "french-toast": ("breakfast", art_french_toast),
    "bagel": ("breakfast", art_bagel),
    "oatmeal-porridge": ("breakfast", art_oatmeal),
    "cinnamon-roll": ("bakery", art_cinnamon_roll),
    "tart": ("bakery", art_tart),
    "pastry-turnover": ("bakery", art_turnover),
    "artisan-cafe-sandwich": ("lunch", art_artisan_sandwich),
    "panini-grilled-sandwich": ("lunch", art_panini),
    "burger": ("lunch", art_burger),
    "hot-dog": ("lunch", art_hot_dog),
    "quiche": ("lunch", art_quiche),
    "pizza-flatbread": ("lunch", art_pizza),
    "fries-potato-wedges": ("lunch", art_fries),
    "savoury-bowl": ("lunch", art_savoury_bowl),
    "broth-soup": ("lunch", art_broth_soup),
    "chowder": ("lunch", art_chowder),
    "chili": ("lunch", art_chili),
    "composed-salad": ("lunch", art_composed_salad),
    "grain-bowl-salad": ("lunch", art_grain_bowl),
    "chocolate-cake-slice": ("sweet", art_chocolate_cake),
    "light-fruit-cake-slice": ("sweet", art_light_cake),
    "cheesecake": ("sweet", art_cheesecake),
    "tiramisu": ("sweet", art_tiramisu),
    "pie-slice": ("sweet", art_pie_slice),
    "ice-cream-gelato": ("sweet", art_ice_cream),
    "dessert-parfait": ("sweet", art_parfait),
    "fruit-cup": ("sweet", art_fruit_cup),
    "coffee-beans-bag": ("coffee", art_coffee_beans_bag),
    "packaged-snack": ("bakery", art_packaged_snack),
    "bottled-canned-drink": ("cold", art_bottled_drink),
}
ARTWORK.update(ARTWORK_M4)


def render(key: str):
    palette, painter = ARTWORK[key]
    base = background(PALETTES[palette])
    painter(base)
    # frame the subject tighter so it reads well in small product cards
    return finish(base.crop(FRAME).resize((S, S), Image.Resampling.LANCZOS))


def main() -> None:
    parser = argparse.ArgumentParser()
    default_out = Path(__file__).resolve().parents[1] / "app" / "platform" / "starter-media"
    parser.add_argument("--out", default=str(default_out))
    parser.add_argument("--only", default="")
    parser.add_argument("--version", type=int, default=1)
    args = parser.parse_args()
    keys = [k for k in args.only.split(",") if k] or list(ARTWORK)
    out = Path(args.out) / "cafe-restaurant"
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.platform.starter_media import STARTER_MEDIA_PHOTO_KEYS
    for key in keys:
        if key in STARTER_MEDIA_PHOTO_KEYS:
            print("skip (ships an AI-generated photo)", key)
            continue
        image = render(key)
        image.save(out / f"{key}-v{args.version}.webp", "WEBP", quality=84, method=6)
        print("wrote", out / f"{key}-v{args.version}.webp")


if __name__ == "__main__":
    main()
